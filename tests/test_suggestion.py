"""Tests for the L2 override-suggestion detection (ADR-0060)."""

from __future__ import annotations

from typing import Any

from custom_components.poise.control.suggestion import (
    SUGGEST_REJECT_DAYS,
    OverrideSuggestion,
    detect_override_pattern,
    resolve_suggestion_conflict,
    season_gate_floor,
    season_hint_t_rm,
    season_mode_hint,
    suggestion_suppressed,
)

_DAY = 86400.0
NOW = 1_700_000_000.0


def _ev(
    days_ago: float, delta: float, phase: str = "comfort", **extra: Any
) -> dict[str, Any]:
    return {
        "ts": NOW - days_ago * _DAY,
        "direction": 1 if delta >= 0 else -1,
        "delta": delta,
        "phase": phase,
        "presence_level": "present",
        **extra,
    }


def test_three_same_direction_comfort_nudges_suggest_base_step() -> None:
    # The ADR example: evenings nudged 3x +1 K -> suggest base +0.5 K.
    stats = [_ev(10.0, 1.0), _ev(5.0, 1.0), _ev(1.0, 1.0)]
    s = detect_override_pattern(stats, now_ts=NOW)
    assert s == OverrideSuggestion(
        kind="comfort_base",
        direction=1,
        step_k=0.5,
        step_min=None,
        evidence=3,
        phase="comfort",
    )
    assert s.key == "comfort_base:+1"


def test_downward_comfort_pattern_suggests_lowering() -> None:
    stats = [_ev(9.0, -0.8), _ev(4.0, -1.2), _ev(2.0, -0.6)]
    s = detect_override_pattern(stats, now_ts=NOW)
    assert s is not None
    assert (s.kind, s.direction, s.step_k) == ("comfort_base", -1, 0.5)


def test_small_or_stale_nudges_do_not_count() -> None:
    # Two qualifying events plus one too-small and one outside 14 days: no
    # pattern (the thresholds are the ADR's deliberately conservative gate).
    stats = [
        _ev(20.0, 1.0),  # stale
        _ev(6.0, 0.4),  # below 0.5 K
        _ev(5.0, 1.0),
        _ev(1.0, 1.0),
    ]
    assert detect_override_pattern(stats, now_ts=NOW) is None


def test_mixed_directions_do_not_cross_count() -> None:
    stats = [_ev(8.0, 1.0), _ev(6.0, -1.0), _ev(4.0, 1.0), _ev(2.0, -1.0)]
    assert detect_override_pattern(stats, now_ts=NOW) is None


def test_setback_upward_pattern_suggests_earlier_window() -> None:
    # Repeated warm-up nudges during setback = the "Vorzieh" reading.
    stats = [
        _ev(7.0, 1.0, phase="setback"),
        _ev(3.0, 0.5, phase="setback"),
        _ev(1.0, 2.0, phase="setback"),
    ]
    s = detect_override_pattern(stats, now_ts=NOW)
    assert s == OverrideSuggestion(
        kind="comfort_earlier",
        direction=1,
        step_k=None,
        step_min=30,
        evidence=3,
        phase="setback",
    )
    assert s.key == "comfort_earlier:+1"


def test_setback_downward_pattern_has_no_adr_mapping() -> None:
    stats = [
        _ev(7.0, -1.0, phase="setback"),
        _ev(3.0, -1.0, phase="setback"),
        _ev(1.0, -1.0, phase="setback"),
    ]
    assert detect_override_pattern(stats, now_ts=NOW) is None


def test_strongest_bucket_wins() -> None:
    # 4x comfort-up beats 3x setback-up.
    stats = [
        _ev(9.0, 1.0),
        _ev(7.0, 1.0),
        _ev(5.0, 1.0),
        _ev(3.0, 1.0),
        _ev(8.0, 1.0, phase="setback"),
        _ev(4.0, 1.0, phase="setback"),
        _ev(2.0, 1.0, phase="setback"),
    ]
    s = detect_override_pattern(stats, now_ts=NOW)
    assert s is not None and (s.kind, s.evidence) == ("comfort_base", 4)


def test_malformed_events_are_skipped() -> None:
    stats: list[dict[str, Any]] = [
        {"ts": "not-a-number", "direction": 1, "delta": 1.0, "phase": "comfort"},
        {"direction": 1, "delta": 1.0, "phase": "comfort"},  # no ts
        _ev(5.0, 1.0, phase="weird"),  # unknown phase
        _ev(3.0, 1.0),
        _ev(1.0, 1.0),
    ]
    assert detect_override_pattern(stats, now_ts=NOW) is None  # only 2 count


def test_suppression_is_per_pattern_key_for_30_days() -> None:
    key = "comfort_base:+1"
    recent = NOW - 5 * _DAY
    assert suggestion_suppressed(key, key, recent, NOW) is True
    # A different pattern is not suppressed by that rejection.
    assert suggestion_suppressed("comfort_base:-1", key, recent, NOW) is False
    # The window expires.
    old = NOW - (SUGGEST_REJECT_DAYS + 1) * _DAY
    assert suggestion_suppressed(key, key, old, NOW) is False
    # No rejection recorded.
    assert suggestion_suppressed(key, None, None, NOW) is False


# --- ADR-0060 §3 season gate: mismatch-era events never count ----------------


def test_since_ts_floor_excludes_mismatch_era_events() -> None:
    # Events recorded while the zone was season-wrong are mode signals, not
    # comfort evidence (the confirmed Badezimmer valve-test false positive).
    stats = [_ev(10.0, 1.0), _ev(8.0, 1.0), _ev(6.0, 1.0)]
    assert detect_override_pattern(stats, now_ts=NOW, since_ts=NOW - 6.0 * _DAY) is None
    # Without a floor the baseline behavior is unchanged.
    assert detect_override_pattern(stats, now_ts=NOW) is not None


def test_since_ts_floor_is_per_event_not_all_or_nothing() -> None:
    stats = [
        _ev(12.0, 1.0),
        _ev(11.0, 1.0),
        _ev(5.0, 1.0),
        _ev(3.0, 1.0),
        _ev(1.0, 1.0),
    ]
    # Two mismatch-era + three fresh events: only the fresh ones qualify.
    s = detect_override_pattern(stats, now_ts=NOW, since_ts=NOW - 10.0 * _DAY)
    assert s is not None and s.evidence == 3
    # Boundary: an event exactly AT the floor is excluded (<=) — the stamp is
    # written in the very tick that saw the hint active.
    assert detect_override_pattern(stats, now_ts=NOW, since_ts=NOW - 5.0 * _DAY) is None


def test_season_gate_floor_rule() -> None:
    # Active hint: everything up to now is mismatch-era.
    assert season_gate_floor(hint_active=True, last_active_ts=None, now_ts=NOW) == NOW
    assert (
        season_gate_floor(hint_active=True, last_active_ts=NOW - _DAY, now_ts=NOW)
        == NOW
    )
    # Cleared hint: the persisted stamp keeps flooring — mode switch, restart
    # and sensor flicker all clear the HINT without clearing the contamination.
    assert (
        season_gate_floor(hint_active=False, last_active_ts=NOW - _DAY, now_ts=NOW)
        == NOW - _DAY
    )
    # Never season-wrong: no gate.
    assert season_gate_floor(hint_active=False, last_active_ts=None, now_ts=NOW) is None


def test_season_hint_t_rm_guards_fabricated_fallback() -> None:
    # No real T_rm source: the hint is unknowable, not "cleared" — a cool_only
    # zone without outdoor data must not inherit a permanent fabricated hint
    # from the pipeline's outdoor fallback constant (5 °C <= lockout).
    assert season_hint_t_rm(5.0, None) is None
    assert season_hint_t_rm(24.7, "sensor") == 24.7
    assert season_hint_t_rm(21.9, "internal") == 21.9
    assert season_hint_t_rm(18.0, "outdoor") == 18.0


# --- ADR-0060 §2: advisory season-mode hint ---------------------------------


def test_heat_only_in_cooling_season_raises_hint() -> None:
    # T_rm at/above the heating lockout: heating is gated anyway, the fixed
    # heat_only mode is season-wrong. T_rm's multi-day memory IS the
    # "persistently" condition — no extra dwell timer.
    assert (
        season_mode_hint(
            climate_mode="heat_only",
            t_rm=22.0,
            heat_max_outdoor=22.0,
            cool_min_outdoor=16.0,
            prev_hint=None,
        )
        == "heat_only_in_cooling"
    )


def test_cool_only_in_heating_season_raises_hint() -> None:
    assert (
        season_mode_hint(
            climate_mode="cool_only",
            t_rm=16.0,
            heat_max_outdoor=22.0,
            cool_min_outdoor=16.0,
            prev_hint=None,
        )
        == "cool_only_in_heating"
    )


def test_hint_has_hysteresis_against_threshold_flapping() -> None:
    kw = {
        "climate_mode": "heat_only",
        "heat_max_outdoor": 22.0,
        "cool_min_outdoor": 16.0,
    }
    # Below the raise threshold nothing raises...
    assert season_mode_hint(t_rm=21.5, prev_hint=None, **kw) is None
    # ...but a raised hint holds until 1 K below it...
    assert (
        season_mode_hint(t_rm=21.5, prev_hint="heat_only_in_cooling", **kw)
        == "heat_only_in_cooling"
    )
    # ...and clears beyond the hysteresis band.
    assert season_mode_hint(t_rm=20.9, prev_hint="heat_only_in_cooling", **kw) is None
    # Mirror for the cooling side.
    kw2 = {
        "climate_mode": "cool_only",
        "heat_max_outdoor": 22.0,
        "cool_min_outdoor": 16.0,
    }
    assert (
        season_mode_hint(t_rm=16.8, prev_hint="cool_only_in_heating", **kw2)
        == "cool_only_in_heating"
    )
    assert season_mode_hint(t_rm=17.1, prev_hint="cool_only_in_heating", **kw2) is None


def test_hint_silent_on_auto_missing_trm_or_mode_switch() -> None:
    # auto is never season-wrong; no T_rm degrades to silent; a stale prev
    # hint for another mode does not stick.
    assert (
        season_mode_hint(
            climate_mode="auto",
            t_rm=30.0,
            heat_max_outdoor=22.0,
            cool_min_outdoor=16.0,
            prev_hint="heat_only_in_cooling",
        )
        is None
    )
    assert (
        season_mode_hint(
            climate_mode="heat_only",
            t_rm=None,
            heat_max_outdoor=22.0,
            cool_min_outdoor=16.0,
            prev_hint="heat_only_in_cooling",
        )
        is None
    )
    assert (
        season_mode_hint(
            climate_mode="cool_only",
            t_rm=21.5,
            heat_max_outdoor=22.0,
            cool_min_outdoor=16.0,
            prev_hint="heat_only_in_cooling",  # wrong kind for this mode
        )
        is None
    )


# --- ADR-0067 §4: conflict resolution between the two suggestion families ---


def test_conflict_resolution_never_emits_two_families() -> None:
    # Nothing pending.
    assert resolve_suggestion_conflict(
        l2_pending=False, clo_pending=False, open_family=None
    ) == (False, False, None)
    # Single family emits and claims the slot.
    assert resolve_suggestion_conflict(
        l2_pending=True, clo_pending=False, open_family=None
    ) == (True, False, "override")
    assert resolve_suggestion_conflict(
        l2_pending=False, clo_pending=True, open_family=None
    ) == (False, True, "clo")
    # Fresh tie: the override reading wins (the stronger evidence).
    assert resolve_suggestion_conflict(
        l2_pending=True, clo_pending=True, open_family=None
    ) == (True, False, "override")
    # "und umgekehrt": an already-open clo suggestion is NOT displaced by a
    # later L2 pattern...
    assert resolve_suggestion_conflict(
        l2_pending=True, clo_pending=True, open_family="clo"
    ) == (False, True, "clo")
    # ...and an open override suggestion keeps its slot symmetrically.
    assert resolve_suggestion_conflict(
        l2_pending=True, clo_pending=True, open_family="override"
    ) == (True, False, "override")
    # A vanished pattern releases the slot to the other family.
    assert resolve_suggestion_conflict(
        l2_pending=True, clo_pending=False, open_family="clo"
    ) == (True, False, "override")
