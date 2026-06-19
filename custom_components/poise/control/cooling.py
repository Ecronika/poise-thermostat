"""Dual-setpoint cooling decision with outdoor gating (RoomMind method, ADR-0016).

Separate heat/cool targets with a natural dead-band; hard outdoor lockouts
prevent heating when it is mild outside and cooling when it is cold.
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
    cool_min_outdoor: float = 16.0,
    heat_max_outdoor: float = 22.0,
) -> str:
    """Return "heat", "cool" or "idle"."""
    can_heat = climate_mode in ("auto", "heat_only") and outdoor <= heat_max_outdoor
    can_cool = climate_mode in ("auto", "cool_only") and outdoor >= cool_min_outdoor
    if can_heat and room < setpoint.heat:
        return "heat"
    if can_cool and room > setpoint.cool:
        return "cool"
    return "idle"
