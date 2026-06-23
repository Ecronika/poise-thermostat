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


def test_dewpoint_zero_humidity_no_crash() -> None:
    # F2: 0 % RH must not raise math domain error; RH is floored before log.
    val = dewpoint(20.0, 0.0)
    assert val == pytest.approx(dewpoint(20.0, 1.0))  # clamped to the 1 % floor


def test_vapour_pressure_floors_humidity() -> None:
    # F2: 0 % and 1 % collapse to the same floored value (no zero pressure).
    assert vapour_pressure(20.0, 0.0) == vapour_pressure(20.0, 1.0)
    assert vapour_pressure(20.0, 0.0) > 0.0


def test_temperature_at_saturation_zero_pressure_no_crash() -> None:
    # F2: p_sat floored so log(0) cannot fire.
    assert temperature_at_saturation(0.0) < -100.0
