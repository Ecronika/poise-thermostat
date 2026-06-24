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
    # Temperature stops falling / starts rising -> recovers above close band.
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


def test_effective_window_open_combines_signals() -> None:
    from custom_components.poise.control.window_auto import effective_window_open

    # sensor OR slope opens; bypass forces closed regardless.
    assert (
        effective_window_open(sensor_open=True, auto_open=False, bypass=False) is True
    )
    assert (
        effective_window_open(sensor_open=False, auto_open=True, bypass=False) is True
    )
    assert (
        effective_window_open(sensor_open=False, auto_open=False, bypass=False) is False
    )
    assert effective_window_open(sensor_open=True, auto_open=True, bypass=True) is False


def test_adaptive_threshold_scales_with_insulation() -> None:
    from custom_components.poise.control.window_auto import adaptive_open_threshold

    # Same temperature delta: a leaky room (small tau, fast natural cooling)
    # needs a steeper drop to flag a window than a well-insulated one.
    insulated = adaptive_open_threshold(10.0, t_room=21.0, t_out=6.0)
    leaky = adaptive_open_threshold(2.0, t_room=21.0, t_out=6.0)
    assert leaky > insulated


def test_adaptive_threshold_is_clamped() -> None:
    from custom_components.poise.control.window_auto import (
        WindowAutoConfig,
        adaptive_open_threshold,
    )

    cfg = WindowAutoConfig()
    very_insulated = adaptive_open_threshold(200.0, 21.0, 6.0, cfg)
    very_leaky = adaptive_open_threshold(0.5, 21.0, -10.0, cfg)
    assert very_insulated == cfg.open_threshold_min  # floored
    assert very_leaky == cfg.open_threshold_max  # capped


def test_adaptive_threshold_falls_back_when_tau_unknown() -> None:
    from custom_components.poise.control.window_auto import (
        WindowAutoConfig,
        adaptive_open_threshold,
    )

    cfg = WindowAutoConfig()
    assert adaptive_open_threshold(0.0, 21.0, 6.0, cfg) == cfg.open_threshold


def test_stuck_open_recovers_on_flat_slope() -> None:
    # Live-observed summer false positive: opened on a transient drop, then the
    # room goes flat (~0 slope). It must CLOSE (recover) within a few ticks, not
    # hang open until the 30-min max-duration. (window_auto_detected stuck true.)
    st = _feed([-8.0, -8.0, -8.0])  # open
    assert st.open is True
    st = _feed([-0.001, -0.001, -0.001, -0.001], state=st)  # flat, barely negative
    assert st.open is False
