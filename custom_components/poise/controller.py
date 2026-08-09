"""Controllers behind the stable :class:`Controller` protocol.

A controller consumes a :class:`ThermalState` + :class:`ComfortCorridor` and
returns a :class:`ControlRequest` — it never writes to an actuator
(ADR-0005/0013).

Like ``pipeline.py``, this module is harness/test-only: the live path runs
the coordinator's own tick, never ``Controller.evaluate`` (ADR-0011).
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
    """Trivial reference controller for the harness vertical slice.

    Heats toward the corridor target via the setpoint path with hysteresis.
    ``control/mpc_controller.MpcController`` implements the same protocol; it
    blends against a bang-bang reference rather than replacing it
    (ADR-0001/0009).
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
