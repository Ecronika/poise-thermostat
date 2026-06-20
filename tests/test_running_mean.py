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


def test_tracker_cold_start_seeds_from_first_outdoor() -> None:
    from custom_components.poise.estimation.running_mean import RunningMeanTracker

    t = RunningMeanTracker()
    assert t.current is None
    t.observe(18.0, day=100)
    assert t.current == 18.0  # seeded


def test_tracker_same_day_does_not_advance() -> None:
    from custom_components.poise.estimation.running_mean import RunningMeanTracker

    t = RunningMeanTracker()
    t.observe(18.0, day=100)
    t.observe(22.0, day=100)  # still day 100 -> t_rm stays the seed
    assert t.current == 18.0
    assert t.day_count == 2


def test_tracker_rollover_applies_en16798_recursion() -> None:
    from custom_components.poise.estimation.running_mean import RunningMeanTracker

    # seed t_rm = 10; accumulate a day whose mean is 20; roll to next day.
    t = RunningMeanTracker(t_rm=10.0, day=100, day_sum=20.0, day_count=1)
    t.observe(5.0, day=101)  # finalizes day 100 (mean 20) then starts day 101
    assert t.current == pytest.approx(0.2 * 20.0 + 0.8 * 10.0)  # 12.0
    assert t.recent_days[0] == pytest.approx(20.0)


def test_tracker_recent_days_capped_at_seven() -> None:
    from custom_components.poise.estimation.running_mean import RunningMeanTracker

    t = RunningMeanTracker()
    for d in range(1, 12):  # 11 days
        t.observe(float(d), day=d)
    assert len(t.recent_days) <= 7


def test_tracker_persistence_roundtrip() -> None:
    from custom_components.poise.estimation.running_mean import RunningMeanTracker

    t = RunningMeanTracker()
    for d, temp in [(1, 10.0), (2, 12.0), (3, 14.0)]:
        t.observe(temp, day=d)
    restored = RunningMeanTracker.from_dict(t.to_dict())
    assert restored.current == pytest.approx(t.current)
    assert restored.recent_days == t.recent_days
    assert restored.day == t.day
