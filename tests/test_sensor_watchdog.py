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
