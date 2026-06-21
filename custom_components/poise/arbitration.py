"""Arbitration choke-point (ADR-0013).

Phase 0 resolves a *single* control request against the binding comfort
corridor and emits exactly one command per actuator — the "one writer"
guarantee. The full multi-request constraint solver with hard precedence
arrives in Phase 4; the seam (requests in, one command out) is fixed now.
"""

from __future__ import annotations

from .constraints import Constraint, ConstraintKind, resolve_constraints
from .contracts import ActuatorCommand, ComfortCorridor, ControlRequest, Precedence


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
    constraints = [
        *(
            Constraint(b.value, b.cause, ConstraintKind.FLOOR, Precedence.HEALTH)
            for b in corridor.lower
        ),
        *(
            Constraint(b.value, b.cause, ConstraintKind.CAP, Precedence.COMFORT)
            for b in corridor.upper
        ),
        Constraint(device_max, "device_max", ConstraintKind.CAP, Precedence.SAFETY),
    ]
    res = resolve_constraints(desired, constraints)
    return ActuatorCommand(
        actuator_id=request.actuator_id,
        path=request.path,
        value=round(res.value, 1),
        hvac_mode=hvac_mode,
        reason=request.reason,
        clamped_by=res.binding.cause if res.binding else None,
    )
