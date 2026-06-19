"""Dual-setpoint cooling decision with capability + outdoor gating (RoomMind, ADR-0023).

Separate heat/cool targets with a neutral dead-band; hard outdoor lockouts and
device-capability gating prevent heating when it is mild outside, cooling when
it is cold, or acting in a direction the device cannot do.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DualSetpoint:
    heat: float
    cool: float


def decide_mode(
    room: float,
    setpoint: DualSetpoint,
    *,
    outdoor: float,
    climate_mode: str = "auto",
    can_heat: bool = True,
    can_cool: bool = True,
    cool_min_outdoor: float = 16.0,
    heat_max_outdoor: float = 22.0,
) -> str:
    """Return "heat", "cool" or "idle" (the dead-band / gated case)."""
    heat_ok = (
        can_heat
        and climate_mode in ("auto", "heat_only")
        and outdoor <= heat_max_outdoor
    )
    cool_ok = (
        can_cool
        and climate_mode in ("auto", "cool_only")
        and outdoor >= cool_min_outdoor
    )
    if heat_ok and room < setpoint.heat:
        return "heat"
    if cool_ok and room > setpoint.cool:
        return "cool"
    return "idle"
