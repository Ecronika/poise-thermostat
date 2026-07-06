"""Presence coupling — hierarchical occupancy resolver (ADR-0058).

Home-gate (person/tracker) on the outside, room-occupancy Eco-modulation inside.
A single bool cannot carry two setback depths, so the resolver returns a
three-level ``PresenceLevel`` and the *depth* is an offset, not the ``occupied``
clamp:

- ``COMFORT`` — presence is neutral; the schedule/preset decides ``occupied`` as
  today.
- ``ROOM_ECO`` — house occupied but the room empty past the hold → the glue maps
  this to ``occupied = False`` AND a shallow ``base - eco_delta`` (the ECO-preset
  depth). ``occupied`` MUST be ``False`` there, else ``HEATING_LOWER[cat]`` clamps
  the flat offset away; the safeguard against "too deep" is the shallow offset
  itself, the health floors sit below regardless. Mechanically identical to the
  night setback, only a different offset source → no new control mechanism.
- ``AWAY`` — the house is empty (``home = False``) → the existing away/setback
  path (full drift toward the health floor).

Precedence (ADR-0058): the ``home`` gate is outermost — preheat overrides only the
*room* level, never the house gate (else optimal-start would preheat an empty
house). Fail-safe: an unavailable/unknown/absent entity resolves to *present*
here (``home``/``room_absent_min`` are supplied fail-safe by the glue) — a dead
tracker must never cool or heat-down the house. Pure and HA-free (ADR-0005/0011).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

DEFAULT_ABSENCE_AFTER_MIN = 30.0  # room-empty hold before Eco (PIR-safe; 5..120)
DEFAULT_ECO_DELTA_K = 2.0  # = the ECO-preset offset (override.py); one Eco depth


class PresenceLevel(Enum):
    COMFORT = "comfort"
    ROOM_ECO = "room_eco"
    AWAY = "away"


@dataclass(frozen=True, slots=True)
class PresenceConfig:
    absence_after_min: float = DEFAULT_ABSENCE_AFTER_MIN
    eco_delta: float = DEFAULT_ECO_DELTA_K


def step_room_absence(
    absent_since: float | None, *, present: bool | None, now: float
) -> float | None:
    """Asymmetric room-absence anchor: *present* resets immediately, *absent*
    starts/holds the monotonic clock. ``present is None`` (no sensor, unavailable,
    or a fresh restart) counts as present → clock cleared (fail-safe + the
    conservative restart latch). Returns the monotonic timestamp the room became
    absent, or ``None`` while present."""
    if present is not False:  # True or None -> present / fail-safe
        return None
    return now if absent_since is None else absent_since


def resolve_presence(
    *,
    home: bool | None,
    room_absent_min: float,
    is_comfort: bool,
    preheating: bool,
    cfg: PresenceConfig,
) -> PresenceLevel:
    """Resolve the presence contribution for this tick (ADR-0058).

    ``home`` is the house gate: only an explicit ``False`` closes it (``None`` =
    not configured or unavailable → gate open, fail-safe present). ``room_absent_min``
    is the debounced empty-minutes from :func:`step_room_absence` (0 while present,
    unavailable, sensor-less, or just-restarted). ROOM_ECO applies only inside the
    comfort window; the schedule owns the night setback.
    """
    if home is False:
        return PresenceLevel.AWAY
    if preheating:
        return PresenceLevel.COMFORT
    if is_comfort and room_absent_min >= cfg.absence_after_min:
        return PresenceLevel.ROOM_ECO
    return PresenceLevel.COMFORT


def any_present(values: Iterable[bool | None]) -> bool | None:
    """OR-reduce presence tri-states across several entities (ADR-0058).

    Any entity resolving *present* wins (``True``). Only when every entity
    resolves and all are *absent* is the result ``False``. An empty set — or any
    unresolved (``None``) entity with no present one — yields ``None``: fail-safe
    present, matching the single-entity gate, so a dead tracker never closes the
    house gate. Used for both the house-presence set and the room-occupancy set
    (both fail-safe to present).
    """
    vals = list(values)
    if any(v is True for v in vals):
        return True
    if vals and all(v is False for v in vals):
        return False
    return None
