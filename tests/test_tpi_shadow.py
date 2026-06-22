"""Tests for the live shadow TPI valve duty (ADR-0036). Pure, no HA."""

from __future__ import annotations

from custom_components.poise.control.tpi_shadow import evaluate_tpi_shadow
from custom_components.poise.estimation.thermal_ekf import ThermalModel

_M = ThermalModel(alpha=0.15, beta_h=3.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def test_inactive_without_writable_valve() -> None:
    s = evaluate_tpi_shadow(
        valve_available=False, model=_M, target=21.0, room=18.0, t_out=8.0
    )
    assert s.active is False and s.duty is None and s.valve_percent is None


def test_cold_room_high_duty() -> None:
    s = evaluate_tpi_shadow(
        valve_available=True, model=_M, target=21.0, room=18.0, t_out=8.0
    )
    assert s.active is True
    assert s.duty == 1.0 and s.valve_percent == 100  # cold -> full open


def test_warm_room_zero_duty() -> None:
    s = evaluate_tpi_shadow(
        valve_available=True, model=_M, target=21.0, room=25.0, t_out=8.0
    )
    assert s.active is True
    assert s.duty == 0.0 and s.valve_percent == 0  # warmer than target -> closed


def test_at_target_holds_steady_state_duty() -> None:
    # room == target, t_out 8, target 21 -> feedforward duty ~0.65 (8 + 20*d = 21)
    s = evaluate_tpi_shadow(
        valve_available=True, model=_M, target=21.0, room=21.0, t_out=8.0
    )
    assert 0.5 < (s.duty or 0.0) < 0.8
    assert s.coef_int is not None and s.coef_ext is not None
