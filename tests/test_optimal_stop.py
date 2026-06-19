from __future__ import annotations

from custom_components.poise.control.optimal_stop import residual_fraction


def test_fresh_long_heating_has_high_residual() -> None:
    assert residual_fraction(0.0, heating_duration_h=2.0) > 0.9


def test_residual_decays_with_elapsed_time() -> None:
    early = residual_fraction(0.1, heating_duration_h=1.0)
    late = residual_fraction(1.0, heating_duration_h=1.0)
    assert late < early


def test_longer_heating_charges_more() -> None:
    short = residual_fraction(0.1, heating_duration_h=0.2)
    long = residual_fraction(0.1, heating_duration_h=2.0)
    assert long > short


def test_guards_return_zero() -> None:
    assert residual_fraction(-1.0, 1.0) == 0.0
    assert residual_fraction(1.0, 0.0) == 0.0


def test_bounded_unit_interval() -> None:
    assert 0.0 <= residual_fraction(0.0, 100.0) <= 1.0
