from __future__ import annotations

import pytest

from custom_components.poise.comfort.mold import (
    max_safe_rh,
    surface_relative_humidity,
    surface_temperature,
)

# ADR-0071: this module is now PURE surface psychrometry. The mould VERDICT
# (``mold_min_air_temperature``/``_detail``, ``SURFACE_RH_LIMIT``, the 24 °C
# ceiling) moved to ``comfort/mould_risk.py`` together with the method it
# implemented, and is covered by ``tests/test_mould_risk.py``. What is left
# here is what ``mould_risk`` and the ADR-0066 humidity axis both build on.


def test_surface_temperature_factor() -> None:
    # f_Rsi = 0.7, room 20, outside 0 -> surface = 0 + 0.7*20 = 14
    assert surface_temperature(20.0, 0.0, 0.7) == pytest.approx(14.0)


def test_surface_rh_rises_with_room_humidity() -> None:
    dry = surface_relative_humidity(20.0, 40.0, 0.0, 0.7)
    humid = surface_relative_humidity(20.0, 60.0, 0.0, 0.7)
    assert humid > dry


def test_surface_rh_below_limit_in_normal_conditions() -> None:
    rh = surface_relative_humidity(20.0, 50.0, 0.0, 0.7)
    assert rh < 0.80


def test_worse_thermal_bridge_raises_the_surface_humidity() -> None:
    # the whole point of f_Rsi: the same room air is riskier on a colder wall.
    good = surface_relative_humidity(20.0, 50.0, 0.0, 0.8)
    poor = surface_relative_humidity(20.0, 50.0, 0.0, 0.6)
    assert poor > good


def test_max_safe_rh_is_the_exact_inverse_of_the_surface_humidity() -> None:
    # the published ceiling, fed back in as the room RH, must reproduce the
    # limit it was solved for.
    rh_max = max_safe_rh(20.0, -5.0, limit=0.80)
    assert surface_relative_humidity(20.0, rh_max, -5.0) == pytest.approx(
        0.80, abs=1e-9
    )


def test_max_safe_rh_follows_the_live_critical_limit() -> None:
    # ADR-0071: the live caller passes ``MouldRisk.critical_rh / 100``, which
    # on a cold surface sits ABOVE 80 % -> the ceiling relaxes accordingly.
    assert max_safe_rh(20.0, -5.0, limit=0.88) > max_safe_rh(20.0, -5.0, limit=0.80)


def test_max_safe_rh_invalid_inputs_stay_finite_and_clamped() -> None:
    # F4 survivors: f_rsi = 0 and limit = 0 would both divide by zero.
    assert 0.0 <= max_safe_rh(20.0, 0.0, f_rsi=0.0) <= 100.0
    assert 0.0 <= max_safe_rh(20.0, 0.0, limit=0.0) <= 100.0
