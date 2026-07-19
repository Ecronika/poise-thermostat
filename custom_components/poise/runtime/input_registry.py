"""Listener reaction registry (refactoring plan, phase 1 + finding 7).

Classifies every zone input entity by how the coordinator reacts to one of
its state changes: ``IMMEDIATE`` entities are subscribed via
``async_track_state_change_event`` and any real change requests a coalesced
refresh (A6); everything else is only picked up by the next scheduled tick.
The ``InputRegistry`` turns the watched set into an explicit, testable
contract instead of an inline tuple in ``attach_listeners`` (coordinator.py
line 1193).

Phase-1 scope: pure types and builder only — ``attach_listeners`` keeps its
inline list until the adapter is rewired against this registry (plan phase 6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias


class Reaction(Enum):
    """How the coordinator reacts to a state change of an input entity."""

    # Watched: a real state change requests a coalesced refresh (A6).
    IMMEDIATE = "immediate"
    # Unwatched: the change is only observed by the next scheduled tick.
    NEXT_TICK = "next_tick"


@dataclass(frozen=True, slots=True)
class InputSpec:
    """One zone input entity with its reaction class and functional role."""

    entity_id: str
    reaction: Reaction
    role: str


# The zone's complete input contract — the phase-1 deliverable the plan names
# ``InputRegistry``. A plain ordered tuple on purpose: order IS contract (the
# IMMEDIATE entries appear in listener registration order) and the registry
# is immutable once built. Phase-6 wiring accepts this nominal type.
# noqa UP040: the `type` statement is 3.12-only; the pure CI gate runs on 3.10.
InputRegistry: TypeAlias = tuple[InputSpec, ...]  # noqa: UP040


def build_input_registry(
    *,
    temp: str | None,
    windows: Sequence[str] = (),
    actuator: str | None,
    presence_entities: Sequence[str] = (),
    occupancy_entities: Sequence[str] = (),
    outdoor: str | None = None,
    humidity: str | None = None,
    trm: str | None = None,
    mrt: str | None = None,
    irradiance: str | None = None,
    weather: str | None = None,
    trv_ext_temp: str | None = None,
) -> InputRegistry:
    """Build the zone's input registry from its configured entity ids.

    The ``IMMEDIATE`` set is EXACTLY today's watched list — ``(temp,
    *windows, actuator)`` with falsy ids skipped, in that order (coordinator
    line 1193) — so the future listener wiring can consume the registry
    verbatim without changing which changes trigger a refresh. Every other
    input, including presence and occupancy, is ``NEXT_TICK``.
    """
    specs: list[InputSpec] = []
    if temp:
        specs.append(InputSpec(temp, Reaction.IMMEDIATE, "temp_sensor"))
    specs.extend(
        InputSpec(entity_id, Reaction.IMMEDIATE, "window_sensor")
        for entity_id in windows
        if entity_id
    )
    if actuator:
        specs.append(InputSpec(actuator, Reaction.IMMEDIATE, "actuator"))
    # Finding 7 — conserved listener gap: a presence flip can end a hold the
    # moment the tick sees it (coordinator lines 787-804), yet presence and
    # occupancy entities are NOT watched (line 1193), so the reaction waits
    # for the next tick. This registry pins that behaviour; promoting them to
    # IMMEDIATE is behaviour fix F-PRESENCE and happens in phase 10 only.
    specs.extend(
        InputSpec(entity_id, Reaction.NEXT_TICK, "presence_home")
        for entity_id in presence_entities
        if entity_id
    )
    specs.extend(
        InputSpec(entity_id, Reaction.NEXT_TICK, "occupancy")
        for entity_id in occupancy_entities
        if entity_id
    )
    for entity_id, role in (
        (outdoor, "outdoor_sensor"),
        (humidity, "humidity_sensor"),
        (trm, "trm_sensor"),
        (mrt, "mrt_sensor"),
        (irradiance, "irradiance_sensor"),
        (weather, "weather"),
        (trv_ext_temp, "trv_external_temp"),
    ):
        if entity_id:
            specs.append(InputSpec(entity_id, Reaction.NEXT_TICK, role))
    return tuple(specs)


def immediate_entities(registry: InputRegistry) -> tuple[str, ...]:
    """The watched entity ids in registration order — the listener's input."""
    return tuple(s.entity_id for s in registry if s.reaction is Reaction.IMMEDIATE)
