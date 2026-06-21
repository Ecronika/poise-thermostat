"""Tests for the live shadow MPC (ADR-0033). Pure, no Home Assistant."""

from __future__ import annotations

from custom_components.poise.control.mpc_shadow import evaluate_shadow
from custom_components.poise.estimation.thermal_ekf import ThermalModel

_MODEL = ThermalModel(alpha=0.15, beta_h=3.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def _shadow(identified: bool, t_air: float, std: float = 0.2):
    return evaluate_shadow(
        identified=identified,
        t_air=t_air,
        t_out=5.0,
        t_rm=10.0,
        tau_hours=1.0 / 0.15,
        model=_MODEL,
        prediction_std=std,
        confidence=0.9,
        target=21.0,
        lower=21.0,
        upper=24.0,
    )


def test_inactive_until_identified() -> None:
    s = _shadow(identified=False, t_air=18.0)
    assert s.active is False
    assert s.power is None and s.weight is None and s.setpoint is None


def test_inactive_when_tau_invalid() -> None:
    s = evaluate_shadow(
        identified=True,
        t_air=18.0,
        t_out=5.0,
        t_rm=10.0,
        tau_hours=0.0,
        model=_MODEL,
        prediction_std=0.2,
        confidence=0.9,
        target=21.0,
        lower=21.0,
        upper=24.0,
    )
    assert s.active is False


def test_active_cold_room_commands_heat() -> None:
    s = _shadow(identified=True, t_air=18.0)
    assert s.active is True
    assert s.power is not None and s.power > 0.5
    assert s.regime == "heat"
    assert s.weight == 1.0  # std at noise floor -> full MPC weight


def test_active_warm_room_idles() -> None:
    s = _shadow(identified=True, t_air=25.0)
    assert s.active is True
    assert s.power == 0.0
    assert s.regime == "idle"


def test_weight_falls_with_noise() -> None:
    confident = _shadow(identified=True, t_air=18.0, std=0.2)
    noisy = _shadow(identified=True, t_air=18.0, std=0.45)
    assert confident.weight is not None and noisy.weight is not None
    assert noisy.weight < confident.weight
