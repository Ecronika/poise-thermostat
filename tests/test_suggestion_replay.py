"""Tests for the ADR-0060-§3 tuning-round instrument (suggestion replay)."""

from __future__ import annotations

from typing import Any

from tests.harness.suggestion_replay import (
    SuggestionEvent,
    load_statistics_from_diagnostics,
    replay_suggestion_timeline,
    season_floor_from_diagnostics,
)

_DAY = 86400.0
T0 = 1_700_000_000.0


def _ov(days: float, delta: float, phase: str = "comfort") -> dict[str, Any]:
    return {
        "ts": T0 + days * _DAY,
        "direction": 1 if delta >= 0 else -1,
        "delta": delta,
        "phase": phase,
        "presence_level": "present",
    }


def _fb(days: float, direction: str) -> dict[str, Any]:
    return {"ts": T0 + days * _DAY, "direction": direction}


def test_empty_statistics_replay_to_nothing() -> None:
    assert replay_suggestion_timeline([], []) == []


def test_adr_example_rises_exactly_once_while_it_persists() -> None:
    # 3x +1 K on days 0/3/6: the pattern completes with the third nudge and
    # stays detected for days — ONE rise edge, not one event per replay step.
    events = replay_suggestion_timeline([_ov(0, 1.0), _ov(3, 1.0), _ov(6, 1.0)], [])
    assert len(events) == 1
    e = events[0]
    assert (e.family, e.key, e.evidence) == ("override", "comfort_base:+1", 3)
    # The rise lands when the third qualifying nudge enters the window.
    assert abs(e.at_ts - (T0 + 6 * _DAY)) <= 3600.0


def test_single_and_mixed_nudges_never_rise() -> None:
    # The Nest failure classes from the ADR: single/mixed nudges stay silent.
    events = replay_suggestion_timeline(
        [_ov(0, 1.0), _ov(5, -1.0), _ov(9, 1.0), _ov(12, -1.0)], []
    )
    assert events == []


def test_pattern_decay_and_requalify_are_two_episodes() -> None:
    # A second burst AFTER the 14-day window fully drained the first one is a
    # genuine second suggestion episode -> two rise edges.
    stats = [
        _ov(0, 1.0),
        _ov(1, 1.0),
        _ov(2, 1.0),
        _ov(40, 1.0),
        _ov(41, 1.0),
        _ov(42, 1.0),
    ]
    events = replay_suggestion_timeline(stats, [])
    assert [e.key for e in events] == ["comfort_base:+1", "comfort_base:+1"]
    assert events[1].at_ts - events[0].at_ts >= 30 * _DAY


def test_conflict_override_family_wins_a_fresh_tie() -> None:
    # Both families qualify in the same hour: the override reading wins the
    # tie and holds the slot (#4). Only once its 14-day window drained does
    # the slot free up — the still-qualified clo reading then rises. That is
    # the faithful production semantics, mirrored by the instrument.
    ov = [_ov(0, 1.0), _ov(1, 1.0), _ov(2, 1.0)]
    fb = [
        _fb(0, "cold"),
        _fb(0.5, "cold"),
        _fb(1, "cold"),
        _fb(1.5, "cold"),
        _fb(2, "cold"),
    ]
    events = replay_suggestion_timeline(ov, fb)
    assert [e.family for e in events] == ["override", "clo"]
    assert events[1].at_ts - events[0].at_ts >= 11 * _DAY  # after L2 drained


def test_clo_family_rises_alone_and_carries_direction() -> None:
    fb = [_fb(d, "warm") for d in (0, 2, 4, 6, 8)]
    events = replay_suggestion_timeline([], fb)
    assert len(events) == 1
    assert (events[0].family, events[0].key) == ("clo", "clo_offset:+1")


def test_replay_since_ts_floor_suppresses_mismatch_era_edges() -> None:
    # The Badezimmer shape: a qualifying up-pattern recorded entirely while
    # the zone was season-wrong. With the dump's gate floor the replay stays
    # silent — matching the production emission semantics.
    stats = [_ov(0, 1.0), _ov(3, 1.0), _ov(6, 1.0)]
    assert replay_suggestion_timeline(stats, [], since_ts=T0 + 6 * _DAY) == []
    # Events strictly younger than the floor still rise (one edge).
    stats2 = stats + [_ov(20, 1.0), _ov(21, 1.0), _ov(22, 1.0)]
    events = replay_suggestion_timeline(stats2, [], since_ts=T0 + 6 * _DAY)
    assert [e.key for e in events] == ["comfort_base:+1"]
    assert events[0].at_ts >= T0 + 22 * _DAY - 3600.0


def test_season_floor_loader_reads_stamp_from_both_shapes() -> None:
    raw = {"override_stats": [], "season_hint_last_active_ts": 123.0}
    assert season_floor_from_diagnostics(raw) == 123.0
    enveloped = {
        "home_assistant": {"version": "2026.7.3"},
        "data": {"override_stats": [], "season_hint_last_active_ts": 456.0},
    }
    assert season_floor_from_diagnostics(enveloped) == 456.0
    # Pre-gate dumps carry no stamp; garbage decodes to None (never raises).
    assert season_floor_from_diagnostics({"override_stats": []}) is None
    assert season_floor_from_diagnostics({"season_hint_last_active_ts": "x"}) is None


def test_diagnostics_loader_reads_both_sections() -> None:
    payload = {
        "config": {"name": "x"},
        "data": {"pmv": 0.1},
        "override_stats": [_ov(0, 1.0)],
        "feedback_stats": [_fb(0, "cold")],
    }
    ov, fb = load_statistics_from_diagnostics(payload)
    assert ov == [_ov(0, 1.0)]
    assert fb == [_fb(0, "cold")]
    # Tolerant of dumps from before F1 (no feedback section).
    ov2, fb2 = load_statistics_from_diagnostics({"override_stats": [_ov(0, 1.0)]})
    assert ov2 and fb2 == []
    # The REAL download wraps the integration payload in HA's envelope
    # (home_assistant / integration_manifest / data) — the statistics then
    # live one level down, under payload["data"].
    enveloped = {
        "home_assistant": {"version": "2026.7.3"},
        "integration_manifest": {"domain": "poise"},
        "data": {
            "config": {},
            "data": {},
            "override_stats": [_ov(0, 1.0)],
            "feedback_stats": [_fb(0, "cold")],
        },
    }
    ov3, fb3 = load_statistics_from_diagnostics(enveloped)
    assert ov3 == [_ov(0, 1.0)]
    assert fb3 == [_fb(0, "cold")]


def test_event_is_a_frozen_value_object() -> None:
    e = SuggestionEvent(at_ts=T0, family="override", key="comfort_base:+1", evidence=3)
    assert e == SuggestionEvent(
        at_ts=T0, family="override", key="comfort_base:+1", evidence=3
    )
