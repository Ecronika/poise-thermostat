"""Tests for the sensorless slope-based open-window detector (ADR-0041)."""

from __future__ import annotations

from custom_components.poise.control.window_auto import (
    WindowAutoConfig,
    WindowAutoState,
    step_window_auto,
)

CFG = WindowAutoConfig()  # open 3.0, close 0.0, max 30 min, min 3 points


def _feed(slopes, dt_min=1.0, state=None, cfg=CFG):
    state = state or WindowAutoState()
    for s in slopes:
        state = step_window_auto(state, s, dt_min, cfg)
    return state


def test_no_verdict_before_min_points() -> None:
    # Two steep drops only — below min_points (3): must not open yet.
    st = _feed([-10.0, -10.0])
    assert st.n_points == 2
    assert st.open is False


def test_opens_on_sustained_sharp_drop() -> None:
    st = _feed([-8.0, -8.0, -8.0])  # third sample reaches min_points
    assert st.open is True
    assert st.ema_slope < -CFG.open_threshold


def test_slow_drift_does_not_open() -> None:
    # Heating-off drift of -1 degC/h is well above the -3 open threshold.
    st = _feed([-1.0, -1.0, -1.0, -1.0, -1.0])
    assert st.open is False


def test_closes_when_slope_recovers() -> None:
    st = _feed([-8.0, -8.0, -8.0])
    assert st.open is True
    # Temperature stops falling / starts rising -> slope >= close_threshold.
    st = _feed([2.0, 2.0], state=st)
    assert st.open is False
    assert st.minutes_open == 0.0


def test_aberrant_slope_is_ignored() -> None:
    # |slope| > max_slope (120) must not pollute the EMA or advance n_points.
    st = WindowAutoState()
    st2 = step_window_auto(st, 999.0, 1.0, CFG)
    assert st2.n_points == 0
    assert st2.ema_slope == 0.0
    assert st2.open is False


def test_max_duration_auto_reset() -> None:
    st = _feed([-8.0, -8.0, -8.0])  # open, minutes_open reset to 0
    assert st.open is True
    # Keep dropping in 15-min steps: 15, then 30 -> force close despite drop.
    st = step_window_auto(st, -8.0, 15.0, CFG)
    assert st.open is True and st.minutes_open == 15.0
    st = step_window_auto(st, -8.0, 15.0, CFG)
    assert st.open is False  # anti-stick fired at max_duration_min
    assert st.minutes_open == 0.0


def test_missing_slope_still_times_out() -> None:
    st = _feed([-8.0, -8.0, -8.0])
    assert st.open is True
    # No new measurement (None) for longer than max_duration -> force close.
    st = step_window_auto(st, None, 40.0, CFG)
    assert st.open is False


def test_state_roundtrip() -> None:
    st = _feed([-8.0, -8.0, -8.0])
    again = WindowAutoState.from_dict(st.to_dict())
    assert again == st
