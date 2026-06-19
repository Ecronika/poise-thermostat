from __future__ import annotations

from custom_components.poise.control.tpi import (
    COEF_INT_BOUNDS,
    TpiLearner,
    seed_from_model,
    tpi_duty,
)


def test_duty_is_clamped_to_unit_interval() -> None:
    assert tpi_duty(0.6, 0.01, 21.0, 15.0, -5.0) == 1.0  # large error saturates
    assert tpi_duty(0.6, 0.01, 21.0, 25.0, 20.0) == 0.0  # room above target


def test_duty_increases_with_deficit() -> None:
    # small gain so neither case saturates at 1.0
    cold = tpi_duty(0.1, 0.01, 21.0, 18.0, 10.0)
    colder = tpi_duty(0.1, 0.01, 21.0, 16.0, 10.0)
    assert 0.0 < cold < colder < 1.0


def test_seed_is_within_bounds_and_dimensional() -> None:
    coef_int, coef_ext = seed_from_model(alpha=0.15, beta_h=3.0)
    assert COEF_INT_BOUNDS[0] <= coef_int <= COEF_INT_BOUNDS[1]
    assert 0.002 <= coef_ext <= 0.06


def test_learner_raises_coef_when_room_underheats() -> None:
    learner = TpiLearner(0.4, 0.01)
    before = learner.coef_int
    # expected more rise than observed -> coefficient should grow
    for _ in range(20):
        learner.update(expected_rise=1.0, actual_rise=0.5)
    assert learner.coef_int > before
    assert learner.coef_int <= COEF_INT_BOUNDS[1]


def test_learner_ignores_non_observable_samples() -> None:
    learner = TpiLearner(0.4, 0.01)
    before = learner.coef_int
    learner.update(expected_rise=1.0, actual_rise=0.0)
    learner.update(expected_rise=0.0, actual_rise=1.0)
    assert learner.coef_int == before
