"""Precedence-explicit constraint solver (ADR-0013 / ADR-0035).

The single source of truth for composing hard setpoint bounds. Each constraint
is a FLOOR or a CAP and carries a :class:`Precedence` (the charter conflict
order). Floors compose to their maximum, caps to their minimum. When they invert
(binding floor above binding cap) the higher-precedence constraint wins — e.g. a
device's physical max (SAFETY) beats the ASR comfort cap, and a health frost/
mould floor (HEALTH) beats that comfort cap. The binding constraint and its
precedence are reported so the live path can surface *why* a value was clamped.

Pure stdlib, fully unit-tested; HA-free so it runs in the harness (ADR-0011).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .contracts import Precedence


class ConstraintKind(Enum):
    FLOOR = "floor"  # value may not go *below* this
    CAP = "cap"  # value may not go *above* this


@dataclass(frozen=True, slots=True)
class Constraint:
    """One hard bound plus the cause and precedence that impose it."""

    value: float
    cause: str
    kind: ConstraintKind
    precedence: Precedence = Precedence.COMFORT


@dataclass(frozen=True, slots=True)
class Resolution:
    """Outcome of composing constraints over a desired value."""

    value: float
    binding: Constraint | None  # the constraint that set the value (None = free)
    floor: Constraint | None  # the binding (highest) floor, if any
    cap: Constraint | None  # the binding (lowest) cap, if any


def _binding_floor(constraints: Sequence[Constraint]) -> Constraint | None:
    floors = [c for c in constraints if c.kind is ConstraintKind.FLOOR]
    if not floors:
        return None
    # highest value binds; tie-break to the higher-precedence (lower int) cause
    return max(floors, key=lambda c: (c.value, -int(c.precedence)))


def _binding_cap(constraints: Sequence[Constraint]) -> Constraint | None:
    caps = [c for c in constraints if c.kind is ConstraintKind.CAP]
    if not caps:
        return None
    # lowest value binds; tie-break to the higher-precedence (lower int) cause
    return min(caps, key=lambda c: (c.value, int(c.precedence)))


def resolve_constraints(
    desired: float, constraints: Sequence[Constraint]
) -> Resolution:
    """Clamp ``desired`` through all constraints; report the binding one.

    Floors compose to their max, caps to their min. On inversion (floor above
    cap) the higher-precedence bound wins (ties -> the floor, health-first).
    """
    floor = _binding_floor(constraints)
    cap = _binding_cap(constraints)
    if floor is not None and cap is not None and floor.value > cap.value:
        winner = floor if int(floor.precedence) <= int(cap.precedence) else cap
        return Resolution(winner.value, winner, floor, cap)
    value = desired
    binding: Constraint | None = None
    if floor is not None and value < floor.value:
        value, binding = floor.value, floor
    if cap is not None and value > cap.value:
        value, binding = cap.value, cap
    return Resolution(value, binding, floor, cap)
