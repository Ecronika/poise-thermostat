from __future__ import annotations

import pytest

from custom_components.poise.comfort.mold import (
    mold_min_air_temperature,
    surface_relative_humidity,
    surface_temperature,
)


def test_surface_temperature_factor() -> None:
    # f_Rsi = 0.7, room 20, outside 0 -> surface = 0 + 0.7*20 = 14
    assert surface_temperature(20.0, 0.0, 0.7) == pytest.approx(14.0)


def test_surface_rh_below_limit_in_normal_conditions() -> None:
    rh = surface_relative_humidity(20.0, 50.0, 0.0, 0.7)
    assert rh < 0.80


def test_mold_min_reference() -> None:
    # outside 0 °C, room 20 °C @ 50 % RH, f_Rsi 0.7 -> ~18.0 °C floor
    floor = mold_min_air_temperature(0.0, 50.0, 20.0, 0.7)
    assert floor == pytest.approx(18.03, abs=0.1)


def test_higher_humidity_raises_the_floor() -> None:
    dry = mold_min_air_temperature(0.0, 40.0, 20.0, 0.7)
    humid = mold_min_air_temperature(0.0, 60.0, 20.0, 0.7)
    assert humid > dry


def test_worse_thermal_bridge_raises_the_floor() -> None:
    good = mold_min_air_temperature(0.0, 50.0, 20.0, 0.8)
    poor = mold_min_air_temperature(0.0, 50.0, 20.0, 0.6)
    assert poor > good


def test_mold_min_caps_at_ceiling() -> None:
    # F4: extreme inputs (near-saturated, cold wall) must not blow past the cap.
    val = mold_min_air_temperature(0.0, 99.0, 22.0)
    assert val <= 24.0


def test_mold_min_invalid_f_rsi_no_crash() -> None:
    # F4: f_rsi = 0 would divide by zero; it is floored, result stays finite & capped.
    val = mold_min_air_temperature(0.0, 80.0, 21.0, f_rsi=0.0)
    assert val <= 24.0
    import math

    assert math.isfinite(val)


def test_mold_min_invalid_limit_no_crash() -> None:
    # F4: limit = 0 would divide by zero inside p_v/limit; it is floored.
    val = mold_min_air_temperature(0.0, 80.0, 21.0, limit=0.0)
    import math

    assert math.isfinite(val)
