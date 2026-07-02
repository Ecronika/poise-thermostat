"""Tests for the ASHRAE 55 elevated-air-speed cooling effect (roadmap M3)."""

from __future__ import annotations

from custom_components.poise.comfort.fan_cooling import (
    cooling_effect,
    fan_cool_setpoint,
)


def test_cooling_effect_anchors_and_bounds() -> None:
    assert cooling_effect(0.1) == 0.0  # still air
    assert cooling_effect(0.2) == 0.0  # elevated-air-speed threshold
    assert cooling_effect(0.6) == 1.2  # ASHRAE 55 graphic-method anchors
    assert cooling_effect(0.9) == 1.8
    assert cooling_effect(1.2) == 2.2
    assert cooling_effect(2.0) == 2.2  # capped above 1.2 m/s
    assert abs(cooling_effect(0.4) - 0.6) < 1e-9  # midpoint of (0.2,0)-(0.6,1.2)


def test_cooling_effect_monotone_and_concave() -> None:
    assert cooling_effect(0.36) < cooling_effect(0.8) < cooling_effect(1.05)
    # diminishing returns: the low-speed slope exceeds the high-speed slope
    low = cooling_effect(0.4) - cooling_effect(0.2)
    high = cooling_effect(1.2) - cooling_effect(1.0)
    assert low > high


def test_fan_cool_setpoint_no_raise_when_off_or_still() -> None:
    assert fan_cool_setpoint(
        cool_sp=24.0, air_speed=0.6, fan_running=False, upper_cap=26.0
    ) == (24.0, 0.0)
    assert fan_cool_setpoint(
        cool_sp=24.0, air_speed=0.1, fan_running=True, upper_cap=26.0
    ) == (24.0, 0.0)


def test_fan_cool_setpoint_raises_and_clamps() -> None:
    # 0.6 m/s -> +1.2 K, under the cap
    assert fan_cool_setpoint(
        cool_sp=24.0, air_speed=0.6, fan_running=True, upper_cap=26.0
    ) == (25.2, 1.2)
    # clamped to the ASR/EN upper cap
    assert fan_cool_setpoint(
        cool_sp=25.5, air_speed=1.2, fan_running=True, upper_cap=26.0
    ) == (26.0, 0.5)
    # a cap below cool_sp never lowers the setpoint
    assert fan_cool_setpoint(
        cool_sp=24.0, air_speed=0.6, fan_running=True, upper_cap=23.0
    ) == (24.0, 0.0)
