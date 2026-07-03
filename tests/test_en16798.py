from __future__ import annotations

import pytest

from custom_components.poise.comfort.en16798 import (
    COOLING_LOWER,
    COOLING_UPPER,
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


def test_lower_limit_extrapolated_below_15() -> None:
    # EN 16798-1: the lower operative limit line is only defined for T_rm >= 15.
    assert not adaptive_band(15.0, Category.II).extrapolated_lower  # boundary
    b14 = adaptive_band(14.0, Category.II)
    assert b14.extrapolated_lower and not b14.extrapolated  # 14 still in [10, 30]
    assert not adaptive_band(20.0, Category.II).extrapolated_lower


def test_deep_cold_flags_both_limits() -> None:
    b = adaptive_band(5.0, Category.II)
    assert b.extrapolated and b.extrapolated_lower


def test_cooling_band_category_i_matches_norm() -> None:
    # EN 16798-1 mechanically-cooled design range: Cat I 23.5-25.5.
    assert COOLING_LOWER[Category.I] == 23.5
    assert COOLING_UPPER[Category.I] == 25.5
    # Cat II / III were already norm-correct -- guard against regressions.
    assert (COOLING_LOWER[Category.II], COOLING_UPPER[Category.II]) == (23.0, 26.0)
    assert (COOLING_LOWER[Category.III], COOLING_UPPER[Category.III]) == (22.0, 27.0)
