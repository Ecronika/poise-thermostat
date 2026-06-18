"""Controllers (ADR-0001 defines the eventual MPC; Phase 0 ships bang-bang).

The :class:`Controller` protocol is the stable seam: a controller consumes a
:class:`ThermalState` + :class:`ComfortCorridor` and returns a
:class:`ControlRequest` — it never writes to an actuator (ADR-0005/0013).
"""

from __future__ import annotations

from typing import Protocol

from .const import BANGBANG_HYSTERESIS_C
from .contracts import (
    ActuatorPath,
    ComfortCorridor,
    ControlRequest,
    ThermalState,
)


class Controller(Protocol):
    def evaluate(
        self,
        state: ThermalState,
        corridor: ComfortCorridor,
        actuator_id: str,
    ) -> ControlRequest: ...


class BangBangController:
    """Trivial Phase-0 controller for the vertical slice.

    Heats toward the corridor target via the setpoint path with hysteresis.
    Real model-predictive control replaces this in Phase 4 (ADR-0001) behind
    the same protocol, so nothing downstream changes.
    """

    def __init__(self, hysteresis: float = BANGBANG_HYSTERESIS_C) -> None:
        self._hyst = hysteresis

    def evaluate(
        self,
        state: ThermalState,
        corridor: ComfortCorridor,
        actuator_id: str,
    ) -> ControlRequest:
        lower = corridor.binding_lower().value
        if state.t_air < corridor.target - self._hyst:
            setpoint, regime = corridor.target, "heat"
        elif state.t_air > corridor.target + self._hyst:
            setpoint, regime = lower, "idle"
        else:
            setpoint, regime = corridor.target, "hold"
        return ControlRequest(
            actuator_id=actuator_id,
            path=ActuatorPath.SETPOINT,
            target_setpoint=setpoint,
            reason=f"bangbang/{regime}",
            regime=regime,
        )
