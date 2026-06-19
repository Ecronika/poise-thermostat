from __future__ import annotations

from custom_components.poise.control.cooling import DualSetpoint, decide_mode

_SP = DualSetpoint(heat=21.0, cool=25.0)


def test_heats_when_cold_inside_and_not_mild_outside() -> None:
    assert decide_mode(19.0, _SP, outdoor=5.0) == "heat"


def test_cools_when_warm_inside_and_warm_outside() -> None:
    assert decide_mode(27.0, _SP, outdoor=28.0) == "cool"


def test_deadband_between_setpoints_is_idle() -> None:
    assert decide_mode(23.0, _SP, outdoor=18.0) == "idle"


def test_outdoor_lockouts() -> None:
    # too mild to heat
    assert decide_mode(19.0, _SP, outdoor=25.0) == "idle"
    # too cold to cool
    assert decide_mode(27.0, _SP, outdoor=10.0) == "idle"


def test_mode_restrictions() -> None:
    assert decide_mode(27.0, _SP, outdoor=28.0, climate_mode="heat_only") == "idle"
    assert decide_mode(19.0, _SP, outdoor=5.0, climate_mode="cool_only") == "idle"
