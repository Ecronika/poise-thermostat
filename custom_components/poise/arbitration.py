"""Arbitration choke-point (ADR-0013).

Phase 0 resolves a *single* control request against the binding comfort
corridor and emits exactly one command per actuator — the "one writer"
guarantee. The full multi-request constraint solver with hard precedence
arrives in Phase 4; the seam (requests in, one command out) is fixed now.
"""

from __future__ import annotations

from .contracts import ActuatorCommand, ComfortCorridor, ControlRequest


def resolve(
    corridor: ComfortCorridor,
    request: ControlRequest,
    *,
    device_max: float,
    hvac_mode: str = "heat",
) -> ActuatorCommand:
    """Clamp the requested setpoint into the binding corridor; one command out."""
    desired = (
        request.target_setpoint
        if request.target_setpoint is not None
        else corridor.target
    )
    value, clamped_by = corridor.clamp(desired)
    if value > device_max:
        value, clamped_by = device_max, "device_max"
    return ActuatorCommand(
        actuator_id=request.actuator_id,
        path=request.path,
        value=round(value, 1),
        hvac_mode=hvac_mode,
        reason=request.reason,
        clamped_by=clamped_by,
    )
