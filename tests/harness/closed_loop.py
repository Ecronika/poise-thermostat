"""Closed-loop validation of the predictive core (ADR-0011/0032).

Drives the *production* EKF, MPC optimizer and optimal-start against the shared
RC plant as a full learn → identify → predict → control loop — the loop that the
coordinator only runs in winter. The plant's true parameters are known, so the
harness can assert the EKF learns them and the predictive control behaves,
without waiting for a real heating season.

Plant truth: alpha = 0.15/h (tau ≈ 6.67 h); full_power_rise 20 °C ⇒ effective
beta_h = full_power_rise·alpha = 3.0 (T_eq_on = t_out + 20).
"""

from __future__ import annotations

from dataclasses import dataclass

from custom_components.poise.contracts import Maturity, ThermalState
from custom_components.poise.control.mpc import MpcParams, optimize_power
from custom_components.poise.estimation.thermal_ekf import ThermalEKF, ThermalModel

from .plant import RCPlant


@dataclass(slots=True)
class IdResult:
    ekf: ThermalEKF
    identified_step: int | None
    final_air: float


def run_identification(
    plant: RCPlant,
    *,
    t_out: float = 2.0,
    on_steps: int = 120,
    off_steps: int = 180,
    cycles: int = 4,
    dt: float = 60.0,
    start_air: float = 18.0,
) -> IdResult:
    """Excite both modes with a heating square wave; feed the EKF each tick."""
    ekf = ThermalEKF()
    air = start_air
    identified_step: int | None = None
    step = 0
    dt_h = dt / 3600.0
    for _ in range(cycles):
        for power in (1.0, 0.0):
            n = on_steps if power == 1.0 else off_steps
            for _ in range(n):
                ekf.predict(dt_h, t_out=t_out, u_h=power)
                ekf.update(air)
                if identified_step is None and ekf.identified:
                    identified_step = step
                air = plant.step(air, power, t_out, dt)
                step += 1
    return IdResult(ekf, identified_step, air)


def ekf_to_state(
    ekf: ThermalEKF, t_air: float, t_out: float, t_rm: float
) -> ThermalState:
    """Build the ThermalState contract from the learned filter (Phase-2 fill)."""
    m = ekf.get_model()
    return ThermalState(
        t_air=t_air,
        tau=ekf.tau_hours,
        loss_uc=m.alpha,
        beta_h=m.beta_h,
        beta_c=m.beta_c,
        beta_s=m.beta_s,
        beta_o=m.beta_o,
        q_solar=0.0,
        t_rm=t_rm,
        confidence=ekf.confidence,
        maturity=Maturity.MATURE if ekf.identified else Maturity.LEARNING,
        t_out=t_out,
        prediction_std=ekf.temperature_std,
        identified=ekf.identified,
    )


def run_mpc_optimizer(
    plant: RCPlant,
    model: ThermalModel,
    *,
    t_out: float = 2.0,
    target: float = 21.0,
    lower: float = 20.0,
    upper: float = 24.0,
    dt: float = 300.0,
    steps: int = 144,
    start_air: float = 18.0,
    params: MpcParams | None = None,
) -> list[tuple[float, float]]:
    """Run the MPC power optimizer in closed loop; return [(air, power), ...]."""
    params = params or MpcParams()
    air = start_air
    trace: list[tuple[float, float]] = []
    for _ in range(steps):
        power = optimize_power(model, air, target, lower, upper, t_out, params)
        air = plant.step(air, power, t_out, dt)
        trace.append((air, power))
    return trace
