"""Tests for the ADR-0068 fan-first FSM + stage selection (pure)."""

from __future__ import annotations

from typing import Any

from custom_components.poise.control.fan_first import (
    FAN_DWELL_MIN_S,
    FAN_ECHO_TIMEOUT_S,
    FAN_FIRST_TIMEOUT_S,
    FAST_RISE_K,
    HEAT_LIMIT_C,
    FanFirstState,
    fan_first_decision,
    max_stage_velocity,
    select_fan_stage,
)

T0 = 10_000.0


def test_velocity_clamp_bands_are_the_conservative_poise_clamp() -> None:
    # < 23 °C operative: 0.2 m/s — no elevated stage can qualify (fail closed;
    # the lowest known stage estimate is 0.25 m/s).
    assert max_stage_velocity(22.9) == 0.2
    # >= 25.5 °C: the 0.8 m/s no-local-control ceiling (ASHRAE 55 add. d).
    assert max_stage_velocity(25.5) == 0.8
    assert max_stage_velocity(30.0) == 0.8
    # In between: conservative linear interpolation, monotonic.
    mid = max_stage_velocity(24.25)
    assert 0.2 < mid < 0.8
    assert max_stage_velocity(24.0) < max_stage_velocity(25.0)


def test_select_fan_stage_never_guesses_and_fails_closed() -> None:
    # Highest known stage under the clamp wins.
    assert select_fan_stage(["low", "medium", "high"], 0.5) == "medium"
    assert select_fan_stage(["low", "medium", "high"], 0.8) == "high"
    # Unknown labels are never guessed (the ["1","2","3","Auto"] device).
    assert select_fan_stage(["1", "2", "3", "Auto"], 0.8) is None
    # No known stage under the clamp -> None (fail closed), never a default.
    assert select_fan_stage(["high", "turbo"], 0.3) is None
    assert select_fan_stage([], 0.8) is None
    # Below the elevated threshold nothing qualifies (0.25 > 0.2).
    assert select_fan_stage(["low"], 0.2) is None


def _decide(state: FanFirstState, **over: Any):  # type: ignore[no-untyped-def]
    kw: dict[str, Any] = {
        "now": T0,
        "cool_requested": True,
        "fan_first_allowed": True,
        "fan_only_capable": True,
        "observed_hvac_mode": "idle",
        "observed_hvac_action": "idle",
        "observed_fan_mode": None,
        "advertised_modes": ("low", "medium", "high"),
        "operative_c": 26.0,
        "room_c": 26.0,
        "presence_ok": True,
        "window_open": False,
        "in_comfort_window": True,
        "foreign_fan_change": False,
    }
    kw.update(over)
    return fan_first_decision(state, **kw)


def test_entry_requires_every_guard() -> None:
    idle = FanFirstState()
    assert _decide(idle).command == "fan_only"  # all guards pass -> engage
    for block in (
        {"cool_requested": False},
        {"fan_first_allowed": False},  # manual intent skips fan-first
        {"fan_only_capable": False},
        {"presence_ok": False},
        {"window_open": True},
        {"in_comfort_window": False},  # night/setback: no elevated stages
        {"room_c": HEAT_LIMIT_C},  # Poise heat policy: >= 35 °C direct cool
        {"observed_hvac_action": "cooling"},  # running compressor: stay cool
        {"observed_hvac_action": None},  # unknown run state: fail closed
        {"operative_c": 22.0},  # clamp 0.2 -> no stage qualifies
        {"advertised_modes": ("1", "2", "Auto")},  # nothing known: fail closed
    ):
        d = _decide(idle, **block)
        assert d.command != "fan_only", block
        assert d.state.phase == "idle", block


def test_sequence_is_echo_gated_step_by_step() -> None:
    # Engage: request fan_only, await the OBSERVED mode before any stage.
    d = _decide(FanFirstState())
    assert (d.command, d.state.phase) == ("fan_only", "await_fan_only")
    # Still cooling-mode observed -> no stage command, keep waiting.
    d2 = _decide(d.state, now=T0 + 60.0)
    assert d2.command == "none"
    # fan_only observed -> NOW the stage command goes out.
    d3 = _decide(d.state, now=T0 + 90.0, observed_hvac_mode="fan_only")
    assert (d3.command, d3.state.phase) == ("stage", "await_stage")
    assert d3.state.stage == "high"  # 26 °C operative -> 0.8 clamp
    # Stage echo observed -> dwell begins (only now).
    d4 = _decide(
        d3.state,
        now=T0 + 150.0,
        observed_hvac_mode="fan_only",
        observed_fan_mode="high",
    )
    assert d4.state.phase == "dwell"
    assert d4.command == "none"


def test_fan_only_echo_timeout_yields_to_cool() -> None:
    d = _decide(FanFirstState())
    late = _decide(d.state, now=T0 + FAN_ECHO_TIMEOUT_S + 1.0)
    assert (late.command, late.state.phase) == ("cool", "yielded")


def test_stage_echo_timeout_yields_to_cool() -> None:
    d = _decide(FanFirstState())
    d3 = _decide(d.state, now=T0 + 60.0, observed_hvac_mode="fan_only")
    late = _decide(
        d3.state,
        now=T0 + 60.0 + FAN_ECHO_TIMEOUT_S + 1.0,
        observed_hvac_mode="fan_only",
        observed_fan_mode=None,
    )
    assert (late.command, late.state.phase) == ("cool", "yielded")


def _dwelling() -> FanFirstState:
    d = _decide(FanFirstState())
    d3 = _decide(d.state, now=T0 + 60.0, observed_hvac_mode="fan_only")
    d4 = _decide(
        d3.state,
        now=T0 + 120.0,
        observed_hvac_mode="fan_only",
        observed_fan_mode="high",
    )
    assert d4.state.phase == "dwell"
    return d4.state


def test_dwell_holds_then_times_out_to_cool() -> None:
    dwelling = _dwelling()
    held = _decide(
        dwelling,
        now=T0 + 120.0 + FAN_DWELL_MIN_S - 1.0,
        observed_hvac_mode="fan_only",
        observed_fan_mode="high",
    )
    assert held.command == "none"  # minimum dwell: the stage gets its chance
    expired = _decide(
        dwelling,
        now=T0 + FAN_FIRST_TIMEOUT_S + 1.0,
        observed_hvac_mode="fan_only",
        observed_fan_mode="high",
    )
    assert (expired.command, expired.state.phase) == ("cool", "yielded")


def test_fast_rise_bypasses_the_minimum_dwell() -> None:
    dwelling = _dwelling()
    rising = _decide(
        dwelling,
        now=T0 + 180.0,
        observed_hvac_mode="fan_only",
        observed_fan_mode="high",
        room_c=26.0 + FAST_RISE_K + 0.1,
    )
    assert (rising.command, rising.state.phase) == ("cool", "yielded")


def test_demand_end_releases_and_blocks_reentry_flap() -> None:
    dwelling = _dwelling()
    done = _decide(
        dwelling,
        now=T0 + 300.0,
        cool_requested=False,
        observed_hvac_mode="fan_only",
        observed_fan_mode="high",
    )
    assert (done.command, done.state.phase) == ("release", "idle")
    # Immediately after a release/yield, re-entry is blocked (anti-flap).
    again = _decide(done.state, now=T0 + 301.0)
    assert again.command != "fan_only"


def test_foreign_fan_change_exits_without_a_write_duel() -> None:
    dwelling = _dwelling()
    foreign = _decide(
        dwelling,
        now=T0 + 200.0,
        observed_hvac_mode="fan_only",
        observed_fan_mode="turbo",
        foreign_fan_change=True,
    )
    assert (foreign.command, foreign.state.phase) == ("release", "idle")
    assert foreign.reason == "foreign_fan_change"


def test_yielded_returns_to_idle_when_demand_ends() -> None:
    d = _decide(FanFirstState())
    yielded = _decide(d.state, now=T0 + FAN_ECHO_TIMEOUT_S + 1.0)
    assert yielded.state.phase == "yielded"
    back = _decide(yielded.state, now=T0 + 2000.0, cool_requested=False)
    assert back.state.phase == "idle"
