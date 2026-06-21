"""Norm-based hard temperature envelope (charter G1/G18; ASR A3.5).

The unconditional air-temperature limits that comfort and efficiency may never
violate (precedence health/safety > comfort > efficiency, K4/K7). Comfort,
virtual-MRT and efficiency math all feed through this final clamp:

- floor: frost / mould-protection minimum (passed in by the caller — the hard
  health floor that the setback/efficiency path can never undercut).
- cap:   ASR A3.5 overheating threshold — living/workplace air temperature
  should not exceed 26 °C; the controller never *commands a heating setpoint*
  above it. (High outdoor temperatures are a cooling concern handled by the EN
  cooling band, not by heating, so the cap is not applied when actively cooling.)
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constraints import Constraint, ConstraintKind, resolve_constraints
from ..contracts import Precedence

ASR_MAX_ROOM_C: float = 26.0  # ASR A3.5 room-air overheating threshold [°C]


@dataclass(frozen=True, slots=True)
class NormClamp:
    value: float
    binding: str | None  # "norm_floor" | "norm_cap" | None


def clamp_to_norm(
    setpoint: float, *, floor: float, cap: float = ASR_MAX_ROOM_C
) -> NormClamp:
    """Clamp ``setpoint`` into the unconditional ``[floor, cap]`` norm envelope.

    The floor takes precedence over the cap (health/safety first) if they invert.
    """
    res = resolve_constraints(
        setpoint,
        [
            Constraint(floor, "norm_floor", ConstraintKind.FLOOR, Precedence.HEALTH),
            Constraint(cap, "norm_cap", ConstraintKind.CAP, Precedence.COMFORT),
        ],
    )
    return NormClamp(res.value, res.binding.cause if res.binding else None)
