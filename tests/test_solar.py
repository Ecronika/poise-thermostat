from __future__ import annotations

import pytest

from custom_components.poise.estimation.solar import (
    clear_sky_normalized,
    normalize_irradiance,
)


def test_clear_sky_zenith_is_one() -> None:
    assert clear_sky_normalized(90.0) == pytest.approx(1.0)


def test_clear_sky_thirty_degrees_is_half() -> None:
    assert clear_sky_normalized(30.0) == pytest.approx(0.5)


def test_clear_sky_below_horizon_is_zero() -> None:
    assert clear_sky_normalized(0.0) == 0.0
    assert clear_sky_normalized(-5.0) == 0.0


def test_clear_sky_monotonic_in_elevation() -> None:
    assert (
        clear_sky_normalized(10.0)
        < clear_sky_normalized(45.0)
        < clear_sky_normalized(80.0)
    )


def test_normalize_irradiance_reference_is_one() -> None:
    assert normalize_irradiance(1000.0) == pytest.approx(1.0)


def test_normalize_irradiance_half() -> None:
    assert normalize_irradiance(500.0) == pytest.approx(0.5)


def test_normalize_irradiance_clamps_and_guards() -> None:
    assert normalize_irradiance(1500.0) == 1.0  # clamp
    assert normalize_irradiance(0.0) == 0.0
    assert normalize_irradiance(-10.0) == 0.0
    assert normalize_irradiance(800.0, reference=0.0) == 0.0  # bad reference
