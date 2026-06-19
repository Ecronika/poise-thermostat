from __future__ import annotations

import pytest

from custom_components.poise.estimation.running_mean import (
    running_mean_from_days,
    running_mean_recursive,
)


def test_recursive_update_matches_en16798() -> None:
    # prev T_rm = 10, yesterday's mean = 20, alpha = 0.8 -> 0.2*20 + 0.8*10
    assert running_mean_recursive(10.0, 20.0) == pytest.approx(12.0)


def test_recursive_is_stationary_for_constant_weather() -> None:
    assert running_mean_recursive(15.0, 15.0) == pytest.approx(15.0)


def test_seven_day_weighted_reference() -> None:
    days = [15.0, 14.0, 13.0, 12.0, 11.0, 10.0, 9.0]
    # (15 + .8*14 + .6*13 + .5*12 + .4*11 + .3*10 + .2*9) / 3.8
    assert running_mean_from_days(days) == pytest.approx(12.9474, abs=1e-3)


def test_seven_day_constant_equals_value() -> None:
    assert running_mean_from_days([10.0] * 7) == pytest.approx(10.0)


def test_empty_series_raises() -> None:
    with pytest.raises(ValueError):
        running_mean_from_days([])
