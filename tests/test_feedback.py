"""Tests for the comfort-feedback statistic (ADR-0067 F1 — observe only)."""

from __future__ import annotations

from custom_components.poise.control.feedback import (
    FEEDBACK_CAP,
    CloSuggestion,
    clo_suggestion_reason,
    detect_feedback_pattern,
    feedback_mask_reason,
    record_feedback,
)

_OK = {
    "window_open": False,
    "override_active": False,
    "is_comfort": True,
    "occupied": True,
    "frozen": False,
    "pmv_valid": True,
    "pmv": 0.3,
    "t_rm": 20.0,
    "t_forecast_day": 24.0,
}


def _reason(**overrides: object) -> str | None:
    return feedback_mask_reason(**{**_OK, **overrides})  # type: ignore[arg-type]


def test_clean_feedback_is_not_masked() -> None:
    assert _reason() is None


def test_every_adr_mask_has_its_reason() -> None:
    # ADR-0067 §F1 mask list, one case each.
    assert _reason(window_open=True) == "window_open"
    assert _reason(override_active=True) == "override_active"
    assert _reason(is_comfort=False) == "setback_or_absent"
    assert _reason(occupied=False) == "setback_or_absent"
    assert _reason(frozen=True) == "sensor_frozen"
    assert _reason(pmv_valid=False) == "pmv_not_valid"  # bedroom profile (V3)
    assert _reason(t_forecast_day=32.0) == "extreme_day"  # |20-32| > 8 K
    assert _reason(pmv=None) == "no_pmv"
    assert _reason(pmv=1.4) == "pmv_out_of_range"
    assert _reason(pmv=-1.4) == "pmv_out_of_range"


def test_mask_precedence_is_first_match_in_adr_order() -> None:
    # window beats everything; the pmv checks come last.
    assert _reason(window_open=True, pmv=None, pmv_valid=False) == "window_open"
    assert _reason(pmv_valid=False, pmv=None) == "pmv_not_valid"


def test_extreme_day_boundary_and_degradation() -> None:
    # Exactly 8 K is still allowed; beyond masks — in BOTH directions.
    assert _reason(t_forecast_day=28.0) is None  # |20-28| = 8
    assert _reason(t_forecast_day=28.1) == "extreme_day"
    assert _reason(t_forecast_day=11.9) == "extreme_day"  # cold snap
    # Without forecast (or without t_rm) the mask degrades to inactive.
    assert _reason(t_forecast_day=None) is None
    assert _reason(t_rm=None) is None


def test_pmv_edge_is_inclusive() -> None:
    assert _reason(pmv=1.0) is None
    assert _reason(pmv=-1.0) is None


def test_record_feedback_shape_and_cap() -> None:
    stats: list[dict[str, object]] = []
    for i in range(FEEDBACK_CAP + 10):
        record_feedback(
            stats,
            direction="cold",
            now_ts=1000.0 + i,
            pmv=0.1,
            ppd=5.5,
            clo_used=0.52,
            met_used=1.2,
            clo_source="rm",
            phase="comfort",
            presence_level="present",
        )
    assert len(stats) == FEEDBACK_CAP  # capped, newest kept
    assert stats[-1]["ts"] == 1000.0 + FEEDBACK_CAP + 9
    assert stats[0]["ts"] == 1000.0 + 10  # oldest dropped
    assert stats[-1] == {
        "ts": 1000.0 + FEEDBACK_CAP + 9,
        "direction": "cold",
        "pmv": 0.1,
        "ppd": 5.5,
        "clo_used": 0.52,
        "met_used": 1.2,
        "clo_source": "rm",
        "phase": "comfort",
        "presence_level": "present",
    }


# --- ADR-0067 F2: clo-offset suggestion from the feedback statistic ---------


def _fb(days_ago: float, direction: str) -> dict[str, object]:
    return {"ts": 1_700_000_000.0 - days_ago * 86400.0, "direction": direction}


NOW = 1_700_000_000.0


def test_five_cold_feedbacks_suggest_lowering_clo() -> None:
    # "5x too cold at computed-neutral PMV -> lower the clothing assumption
    # by 0.1 clo" (less clo assumed -> warmer target).
    stats = [_fb(d, "cold") for d in (25.0, 20.0, 12.0, 5.0, 1.0)]
    s = detect_feedback_pattern(stats, now_ts=NOW)
    assert s == CloSuggestion(direction=-1, evidence=5)
    assert s.key == "clo_offset:-1"


def test_five_warm_feedbacks_suggest_raising_clo() -> None:
    stats = [_fb(d, "warm") for d in (22.0, 15.0, 9.0, 4.0, 2.0)]
    s = detect_feedback_pattern(stats, now_ts=NOW)
    assert s is not None and (s.direction, s.evidence) == (1, 5)


def test_too_few_or_stale_feedbacks_stay_silent() -> None:
    stats = [_fb(d, "cold") for d in (35.0, 20.0, 12.0, 5.0, 1.0)]  # one stale
    assert detect_feedback_pattern(stats, now_ts=NOW) is None


def test_stronger_direction_wins_and_malformed_skipped() -> None:
    stats = [_fb(d, "warm") for d in (28.0, 21.0, 14.0, 7.0, 3.0)]
    stats += [_fb(d, "cold") for d in (26.0, 19.0, 13.0, 6.0, 2.0, 1.0)]  # 6 > 5
    stats.append({"direction": "sideways", "ts": NOW})  # unknown direction
    stats.append({"direction": "cold"})  # no ts
    s = detect_feedback_pattern(stats, now_ts=NOW)
    assert s is not None and (s.direction, s.evidence) == (-1, 6)


def test_clo_suggestion_reason_precedence() -> None:
    s = CloSuggestion(direction=-1, evidence=5)
    kw = {"rejected_key": None, "rejected_at": None, "now_ts": NOW}
    # No pattern at all.
    assert (
        clo_suggestion_reason(None, l2_pending=False, override_direction=None, **kw)
        == "no_pattern"
    )
    # An open L2 comfort-base reading blocks the clo reading (ADR-0067 §4).
    assert (
        clo_suggestion_reason(s, l2_pending=True, override_direction=1, **kw)
        == "l2_pending"
    )
    # Feedback "too cold" but overrides nudging DOWN: contradictory signals.
    assert (
        clo_suggestion_reason(s, l2_pending=False, override_direction=-1, **kw)
        == "inconsistent_signals"
    )
    # A matching override pattern (up) is consistent -> emittable.
    assert clo_suggestion_reason(s, l2_pending=False, override_direction=1, **kw) == ""
    # A recent rejection of exactly this key suppresses for 30 days.
    assert (
        clo_suggestion_reason(
            s,
            l2_pending=False,
            override_direction=None,
            rejected_key="clo_offset:-1",
            rejected_at=NOW - 5 * 86400.0,
            now_ts=NOW,
        )
        == "rejected"
    )
