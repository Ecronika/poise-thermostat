from __future__ import annotations

import pytest

from custom_components.poise.comfort.operative import (
    air_weight,
    operative_temperature,
    operative_to_air,
)


def test_air_weight_steps_with_velocity() -> None:
    assert air_weight(0.1) == 0.5
    assert air_weight(0.3) == 0.6
    assert air_weight(0.8) == 0.7


def test_operative_is_midpoint_at_low_velocity() -> None:
    assert operative_temperature(22.0, 18.0) == pytest.approx(20.0)


def test_operative_to_air_inverts_operative() -> None:
    # want operative 21 with cold walls (MRT 19) -> warmer air needed
    air = operative_to_air(21.0, t_mrt=19.0)
    assert air == pytest.approx(23.0)
    assert operative_temperature(air, 19.0) == pytest.approx(21.0)


def test_operative_to_air_degrades_without_mrt() -> None:
    assert operative_to_air(21.0, t_mrt=None) == 21.0
