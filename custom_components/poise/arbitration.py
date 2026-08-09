"""Arbitration choke-point (ADR-0013).

Resolves a *single* control request against the binding comfort corridor and
emits exactly one command per actuator — the "one writer" guarantee. The
precedence solver (``constraints.py``, ADR-0035) is already used; what is
still single is the input — one request per actuator, not a set. Harness /
pure-core-test scope, same as ``pipeline.py``: the live write path arbitrates
in the coordinator tick.
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
    # Fail toward warmth: every lower bound enters at HEALTH and every upper
    # bound at COMFORT, so on an inverted corridor the floor wins. Only the
    # device's physical max outranks both (SAFETY).
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
