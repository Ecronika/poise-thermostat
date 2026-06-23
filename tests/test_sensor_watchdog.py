from __future__ import annotations

from custom_components.poise.safety.sensor_watchdog import is_frozen


def test_fresh_change_is_not_frozen() -> None:
    assert is_frozen(60.0, 1800.0) is False


def test_old_change_is_frozen() -> None:
    assert is_frozen(1800.0, 1800.0) is True
    assert is_frozen(3600.0, 1800.0) is True


def test_unknown_age_is_not_frozen() -> None:
    assert is_frozen(None, 1800.0) is False


def test_nonpositive_threshold_disables() -> None:
    assert is_frozen(99999.0, 0.0) is False


def test_heat_source_detector() -> None:
    from custom_components.poise.safety.sensor_watchdog import sensor_at_heat_source

    # identified + implausibly short tau -> flagged
    assert sensor_at_heat_source(0.5, identified=True, min_plausible_tau_h=1.0) is True
    # plausible room time constant -> fine
    assert sensor_at_heat_source(6.0, identified=True, min_plausible_tau_h=1.0) is False
    # not identified -> never judge (avoid false positives during learning)
    assert (
        sensor_at_heat_source(0.4, identified=False, min_plausible_tau_h=1.0) is False
    )
    # boundary: exactly at threshold is not flagged
    assert sensor_at_heat_source(1.0, identified=True, min_plausible_tau_h=1.0) is False


def test_valve_stuck_detection() -> None:
    from custom_components.poise.safety.sensor_watchdog import valve_stuck

    assert valve_stuck(325.0) is False  # healthy TRVZB closing-step count
    assert valve_stuck(0.0) is True  # not calibrated / jammed
    assert valve_stuck(5.0, min_steps=10.0) is True
    assert valve_stuck(None) is False  # no telemetry -> not stuck


def test_sensor_age_seconds_from_last_changed() -> None:
    from datetime import datetime, timedelta

    from custom_components.poise.safety.sensor_watchdog import sensor_age_seconds

    now = datetime(2026, 1, 1, 12, 0, 0)
    changed = now - timedelta(hours=3)
    assert sensor_age_seconds(now, changed) == 3 * 3600.0


def test_should_learn_gates_on_window_and_frozen() -> None:
    # M13/F1: learning runs only with a trustworthy signal; window OR frozen pauses it.
    from custom_components.poise.safety.sensor_watchdog import should_learn

    assert should_learn(window_open=False, frozen=False) is True
    assert should_learn(window_open=True, frozen=False) is False
    assert should_learn(window_open=False, frozen=True) is False  # frozen -> no learn
    assert should_learn(window_open=True, frozen=True) is False
