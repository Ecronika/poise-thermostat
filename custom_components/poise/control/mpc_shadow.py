"""Shadow MPC for the live path (ADR-0033, Phase-4 Stufe 1).

Runs the harness-validated :class:`MpcController` against the *live* EKF state
each tick, but only to **report** what the predictive controller would command —
it never actuates (shadow-estimator principle, ADR-0026). Gated on ``identified``
so it stays dormant until the EKF has learned the room in the heating season.
Granting it real write authority is a separate, evidence-gated decision
(ADR-0033 §Flip-Kriterien).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Bound, ComfortCorridor, Maturity, ThermalState
from ..estimation.thermal_ekf import ThermalModel
from .gate import mpc_weight
from .mpc import MpcParams
from .mpc_controller import MpcController


@dataclass(frozen=True, slots=True)
class MpcShadow:
    """What the MPC *would* command this tick (diagnostic only)."""

    active: bool
    power: float | None = None
    weight: float | None = None
    setpoint: float | None = None
    regime: str | None = None


def evaluate_shadow(
    *,
    identified: bool,
    t_air: float,
    t_out: float,
    t_rm: float,
    tau_hours: float,
    model: ThermalModel,
    prediction_std: float,
    confidence: float,
    target: float,
    lower: float,
    upper: float,
    params: MpcParams | None = None,
) -> MpcShadow:
    """Evaluate the shadow MPC; inactive (no command) until the EKF identifies.

    ``lower``/``upper`` are the live comfort band edges (dual-setpoint heat/cool),
    ``target`` the heating setpoint. The result is purely advisory.
    """
    if not identified or tau_hours <= 0.0:
        return MpcShadow(active=False)
    state = ThermalState(
        t_air=t_air,
        tau=tau_hours,
        loss_uc=model.alpha,
        beta_h=model.beta_h,
        beta_c=model.beta_c,
        beta_s=model.beta_s,
        beta_o=model.beta_o,
        q_solar=0.0,
        t_rm=t_rm,
        confidence=confidence,
        maturity=Maturity.MATURE,
        t_out=t_out,
        prediction_std=prediction_std,
        identified=True,
    )
    corridor = ComfortCorridor(
        lower=(Bound(lower, "comfort_low"),),
        upper=(Bound(upper, "comfort_high"),),
        target=target,
    )
    req = MpcController(params).evaluate(state, corridor, "shadow")
    return MpcShadow(
        active=True,
        power=req.power,
        weight=round(mpc_weight(prediction_std), 3),
        setpoint=req.target_setpoint,
        regime=req.regime,
    )
