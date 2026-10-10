from __future__ import annotations

import pytest

from custom_components.poise.comfort.operative import (
    OFFSET_CLAMP_K,
    RadiantModel,
    air_weight,
    measured_offset_model,
    operative_temperature,
    operative_to_air,
    operative_to_air_model,
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


# --- ADR-0017 N1: the closed-form transform against a radiant model ----------


def test_model_transform_hits_the_operative_target_self_consistently() -> None:
    from custom_components.poise.comfort.virtual_mrt import (
        virtual_mrt,
        virtual_mrt_model,
    )

    model = virtual_mrt_model(-5.0, 0.3)
    air = operative_to_air_model(21.0, model)
    # at the air setpoint, the virtual MRT it implies gives exactly the target
    assert operative_temperature(air, virtual_mrt(air, -5.0, 0.3)) == pytest.approx(
        21.0
    )


def test_model_transform_matches_the_pointwise_one_in_steady_state() -> None:
    """When the room already sits at the solved setpoint, old and new agree —
    N1 changes transients and noise, not the steady state."""
    from custom_components.poise.comfort.virtual_mrt import (
        virtual_mrt,
        virtual_mrt_model,
    )

    air = operative_to_air_model(20.55, virtual_mrt_model(-5.0))
    assert air == pytest.approx(21.6146, abs=1e-3)
    assert operative_to_air(20.55, virtual_mrt(air, -5.0)) == pytest.approx(air)


def test_measured_offset_is_clamped_and_carried_as_offset() -> None:
    assert measured_offset_model(19.0, 21.0) == RadiantModel(slope=1.0, intercept=-2.0)
    # a globe outlier is clamped to +-3 K (ADR-0017 §4)
    assert measured_offset_model(10.0, 21.0).intercept == -OFFSET_CLAMP_K
    assert measured_offset_model(30.0, 21.0).intercept == OFFSET_CLAMP_K
    # L = op - (1-a)·offset at a = 0.5
    assert operative_to_air_model(21.0, measured_offset_model(19.0, 21.0)) == (
        pytest.approx(22.0)
    )


def test_identity_model_is_the_identity() -> None:
    assert operative_to_air_model(21.0, RadiantModel(slope=1.0, intercept=0.0)) == (
        pytest.approx(21.0)
    )
