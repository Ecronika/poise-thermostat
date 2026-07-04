from __future__ import annotations

from custom_components.poise.control.tick_budget import (
    DEFAULT_TICK_BUDGET_MS,
    TickBudget,
)


def test_first_observation_seeds_ewma_and_max() -> None:
    b = TickBudget()
    b.observe(4.0)
    assert b.last_ms == 4.0
    assert b.ewma_ms == 4.0  # seeded, not blended toward 0
    assert b.max_ms == 4.0
    assert b.n == 1
    assert b.over_budget is False


def test_ewma_smooths_and_max_is_session_peak() -> None:
    b = TickBudget(ewma_alpha=0.5)
    b.observe(2.0)
    b.observe(10.0)  # ewma -> 6.0, max -> 10.0
    assert b.ewma_ms == 6.0
    assert b.max_ms == 10.0
    b.observe(2.0)  # ewma -> 4.0, max stays 10.0
    assert b.ewma_ms == 4.0
    assert b.max_ms == 10.0


def test_over_budget_flag_and_count() -> None:
    b = TickBudget(budget_ms=50.0)
    b.observe(10.0)
    assert b.over_budget is False and b.over_count == 0
    b.observe(80.0)  # over budget
    assert b.over_budget is True and b.over_count == 1
    b.observe(20.0)  # back under -> flag clears, count sticks
    assert b.over_budget is False and b.over_count == 1


def test_negative_duration_is_clamped_to_zero() -> None:
    b = TickBudget()
    b.observe(-3.0)  # a clock glitch must not produce a negative sample
    assert b.last_ms == 0.0 and b.max_ms == 0.0


def test_default_budget_constant_is_exposed() -> None:
    assert TickBudget().budget_ms == DEFAULT_TICK_BUDGET_MS
