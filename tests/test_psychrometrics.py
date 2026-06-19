from __future__ import annotations

import pytest

from custom_components.poise.estimation.psychrometrics import (
    dewpoint,
    saturation_pressure,
    temperature_at_saturation,
    vapour_pressure,
)


def test_saturation_pressure_at_zero() -> None:
    assert saturation_pressure(0.0) == pytest.approx(610.94, abs=1e-2)


def test_dewpoint_reference_20c_50pct() -> None:
    assert dewpoint(20.0, 50.0) == pytest.approx(9.26, abs=0.05)


def test_dewpoint_equals_air_temp_at_saturation() -> None:
    assert dewpoint(18.0, 100.0) == pytest.approx(18.0, abs=1e-6)


def test_inverse_roundtrip() -> None:
    p = saturation_pressure(15.0)
    assert temperature_at_saturation(p) == pytest.approx(15.0, abs=1e-6)


def test_vapour_pressure_scales_with_humidity() -> None:
    assert vapour_pressure(20.0, 50.0) == pytest.approx(0.5 * saturation_pressure(20.0))
