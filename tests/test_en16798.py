from __future__ import annotations

import pytest

from custom_components.poise.comfort.en16798 import (
    Category,
    adaptive_band,
    comfort_temperature,
)


def test_comfort_temperature_reference() -> None:
    # 0.33 * 15 + 18.8 = 23.75
    assert comfort_temperature(15.0) == pytest.approx(23.75)


def test_category_ii_band_reference() -> None:
    band = adaptive_band(15.0, Category.II)
    assert band.comfort == pytest.approx(23.75)
    assert band.lower == pytest.approx(19.75)  # -4 K
    assert band.upper == pytest.approx(26.75)  # +3 K
    assert not band.extrapolated


def test_categories_widen_with_lower_expectation() -> None:
    cat1 = adaptive_band(20.0, Category.I)
    cat3 = adaptive_band(20.0, Category.III)
    assert cat3.upper > cat1.upper
    assert cat3.lower < cat1.lower


def test_below_validity_is_clamped_and_flagged() -> None:
    band = adaptive_band(5.0, Category.II)
    assert band.extrapolated
    assert band.comfort == pytest.approx(comfort_temperature(10.0))


def test_bands_are_asymmetric() -> None:
    band = adaptive_band(18.0, Category.II)
    assert (band.upper - band.comfort) < (band.comfort - band.lower)
