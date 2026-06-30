"""ADR-0044 §2: model-based expected_minutes for the speed score (pure)."""

from __future__ import annotations

from custom_components.poise.control.optimal_start import heatup_minutes
from custom_components.poise.control.scoring_expectation import (
    model_expected_minutes,
)
from custom_components.poise.estimation.thermal_ekf import ThermalModel

# alpha 1/h, beta_h 15 -> t_eq = t_out + 15; reaches a 21 °C target from 18 °C.
_M = ThermalModel(alpha=1.0, beta_h=15.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def test_uses_physics_estimate_when_identified() -> None:
    # identified model + cold room -> the model-based heat-up time, NOT the
    # schedule fallback. This is exactly the §2 quantity the glue must feed.
    got = model_expected_minutes(
        _M, room=18.0, target=21.0, t_out=10.0, q_solar=0.0, fallback=0.0
    )
    ref = heatup_minutes(_M, room=18.0, target=21.0, t_out=10.0, q_solar=0.0)
    assert ref is not None
    assert got == ref
    assert got > 5.0  # ~33.6 min -> NOT pinned to the neutral-speed floor


def test_falls_back_when_model_absent() -> None:
    # unidentified EKF -> caller passes None -> the fallback (schedule clock)
    got = model_expected_minutes(
        None, room=18.0, target=21.0, t_out=10.0, q_solar=0.0, fallback=42.0
    )
    assert got == 42.0


def test_falls_back_when_target_unreachable() -> None:
    weak = ThermalModel(alpha=1.0, beta_h=5.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)
    # t_eq = 10 + 5 = 15 < target -> heatup None -> fallback
    got = model_expected_minutes(
        weak, room=18.0, target=21.0, t_out=10.0, q_solar=0.0, fallback=7.0
    )
    assert got == 7.0


def test_falls_back_when_already_at_target() -> None:
    # room >= target -> heatup 0.0 -> fallback (do not score against a zero)
    got = model_expected_minutes(
        _M, room=22.0, target=21.0, t_out=10.0, q_solar=0.0, fallback=12.0
    )
    assert got == 12.0
