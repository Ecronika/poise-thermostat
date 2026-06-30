"""ADR-0050 humidity management decision (pure)."""

from __future__ import annotations

from custom_components.poise.comfort.humidity import humidity_decide


def test_no_sensor_graceful() -> None:
    d = humidity_decide(rh=None, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "idle"
    assert d.dry_active is False


def test_dry_guard_blocks_below_rh_low() -> None:
    d = humidity_decide(rh=35.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "dry_guard"
    assert d.dry_active is False


def test_cool_first_when_too_warm() -> None:
    d = humidity_decide(rh=70.0, too_warm=True, in_deadband=False, can_dry=True)
    assert d.action == "cool"
    assert d.dry_active is False


def test_enter_dry_in_band_above_high() -> None:
    d = humidity_decide(rh=62.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "dry"
    assert d.dry_active is True


def test_no_entry_just_below_high() -> None:
    d = humidity_decide(rh=58.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "idle"
    assert d.dry_active is False


def test_hysteresis_holds_between_exit_and_entry() -> None:
    # already drying, RH 57 (>= 55 exit) -> stay dry
    d = humidity_decide(
        rh=57.0, too_warm=False, in_deadband=True, can_dry=True, prev_dry_active=True
    )
    assert d.action == "dry"
    assert d.dry_active is True


def test_hysteresis_exits_below_exit_threshold() -> None:
    d = humidity_decide(
        rh=54.0, too_warm=False, in_deadband=True, can_dry=True, prev_dry_active=True
    )
    assert d.action == "idle"
    assert d.dry_active is False


def test_fan_only_never_dehumidifies() -> None:
    d = humidity_decide(
        rh=65.0, too_warm=False, in_deadband=True, can_dry=False, can_fan_only=True
    )
    assert d.action == "idle"
    assert "fan_only" in d.reason


def test_capability_gap_no_dry() -> None:
    d = humidity_decide(rh=65.0, too_warm=False, in_deadband=True, can_dry=False)
    assert d.action == "idle"
    assert "cannot dry" in d.reason


def test_within_band_idle() -> None:
    d = humidity_decide(rh=50.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "idle"
    assert d.dry_active is False
