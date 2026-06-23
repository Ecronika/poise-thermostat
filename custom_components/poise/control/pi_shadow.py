"""Shadow PI-compensated setpoint for the live path (ADR-0037, shadow stage).

For a setpoint-only TRV (no writable valve) Poise can push a PI-compensated
setpoint so the device cancels its own steady-state droop. This computes what
that compensated setpoint *would* be and reports it as a diagnostic — it never
changes the written setpoint (shadow-estimator principle, ADR-0026/0033).
Active when the device has no writable valve (the setpoint path applies).
"""

from __future__ import annotations

from dataclasses import dataclass

from .pi import _NOMINAL_DT_H, PiCompensator


@dataclass(frozen=True, slots=True)
class PiShadow:
    """The PI-compensated setpoint Poise would write (diagnostic only)."""

    active: bool
    setpoint: float | None = None
    offset: float | None = None


def evaluate_pi_shadow(
    compensator: PiCompensator,
    *,
    applies: bool,
    target: float,
    room: float,
    external: float,
    dt_h: float = _NOMINAL_DT_H,
) -> PiShadow:
    """Compute the shadow compensated setpoint; inactive on valve devices."""
    if not applies:
        return PiShadow(active=False)
    sp = compensator.compensate(target, room, external, dt_h)
    return PiShadow(active=True, setpoint=round(sp, 2), offset=round(sp - target, 2))
