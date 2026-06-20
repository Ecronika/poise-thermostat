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
