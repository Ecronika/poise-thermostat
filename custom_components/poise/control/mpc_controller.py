"""MPC controller — drop-in for the Controller protocol (ADR-0001/0009).

Builds a ThermalModel from the estimated state, optimizes the heating power,
and blends it with the bang-bang reference by the confidence weight. Falls back
to bang-bang when the model is immature/invalid (hard data-gate). Returns a
ControlRequest; the actuator path (TPI duty vs setpoint) is resolved later.
"""

from __future__ import annotations

from ..contracts import (
    ActuatorPath,
    ComfortCorridor,
    ControlRequest,
    Maturity,
    ThermalState,
)
from ..estimation.thermal_ekf import ThermalModel
from .gate import blend, mpc_weight
from .mpc import MpcParams, optimize_power


class MpcController:
    """Confidence-gated MPC behind the same protocol as BangBangController."""

    def __init__(self, params: MpcParams | None = None) -> None:
        self._params = params or MpcParams()

    def _model(self, state: ThermalState) -> ThermalModel | None:
        if state.tau <= 0.0:
            return None
        return ThermalModel(
            alpha=1.0 / state.tau,
            beta_h=state.beta_h,
            beta_c=state.beta_c,
            beta_s=state.beta_s,
            beta_o=state.beta_o,
        )

    def evaluate(
        self, state: ThermalState, corridor: ComfortCorridor, actuator_id: str
    ) -> ControlRequest:
        target = corridor.target
        lower = corridor.binding_lower().value
        upper = corridor.binding_upper().value
        t0 = state.t_air

        u_bang = 1.0 if t0 < target else 0.0
        u_mpc = u_bang
        weight = 0.0

        model = self._model(state)
        mature = (
            state.maturity >= Maturity.LEARNING and state.prediction_std is not None
        )
        if model is not None and mature:
            t_out = state.t_out if state.t_out is not None else state.t_rm
            u_mpc = optimize_power(model, t0, target, lower, upper, t_out, self._params)
            assert state.prediction_std is not None  # narrowed by `mature`
            weight = mpc_weight(state.prediction_std)

        power = blend(u_mpc, u_bang, weight)
        regime = "heat" if power > 0.05 else "idle"
        setpoint = target if power > 0.5 else lower
        return ControlRequest(
            actuator_id=actuator_id,
            path=ActuatorPath.SETPOINT,
            target_setpoint=setpoint,
            power=round(power, 3),
            reason=f"mpc/w={weight:.2f}",
            regime=regime,
        )
