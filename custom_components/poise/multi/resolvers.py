"""Pure resolver pipeline (ADR-0046 §4).

P0/P1 scope is strictly thermal: ``thermal_resolver`` picks one source and the
``assignment_planner`` builds (but does not execute) the commands a shadow can
display. ``humidity_resolver`` and ``air_movement_resolver`` are *no-op stubs*
with a stable interface and reason — they make no decisions and emit no commands
until P4-P7.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .model import (
    CMD_SERVICE,
    Axis,
    Command,
    DeviceHealth,
    Direction,
    StandbyPolicy,
    ZoneDevice,
)
from .reason import BlockingCause, FallbackCause, ReasonCode, ResolveReason


@dataclass(frozen=True, slots=True)
class DeviceRuntime:
    """Per-device live gate state the resolver reasons over (HA-free)."""

    health: DeviceHealth = DeviceHealth.OK
    min_off_active: bool = False
    mode_hold_active: bool = False
    external_override: bool = False


@dataclass(frozen=True, slots=True)
class ThermalDemand:
    direction: Direction | None
    target_c: float | None = None


_PRIORITY_REASON: Mapping[Direction, ReasonCode] = {
    Direction.HEAT: ReasonCode.THERMAL_HEAT_PRIORITY,
    Direction.COOL: ReasonCode.THERMAL_COOL_PRIORITY,
}


def _block_cause(rt: DeviceRuntime) -> BlockingCause | None:
    if rt.health is DeviceHealth.UNAVAILABLE:
        return BlockingCause.DEVICE_UNAVAILABLE
    if rt.health in (DeviceHealth.FAULT, DeviceHealth.STALE, DeviceHealth.LOCKOUT):
        return BlockingCause.DEVICE_UNHEALTHY
    if rt.external_override:
        return BlockingCause.EXTERNAL_OVERRIDE
    if rt.min_off_active:
        return BlockingCause.COMPRESSOR_MIN_OFF_ACTIVE
    if rt.mode_hold_active:
        return BlockingCause.MODE_HOLD_ACTIVE
    return None


def thermal_resolver(
    demand: ThermalDemand,
    devices: Sequence[ZoneDevice],
    runtimes: Mapping[str, DeviceRuntime],
) -> ResolveReason:
    """Pick one thermal source by priority; failover skips blocked candidates.

    P0 has no cost metadata, so the reason is always *priority* or *failover* —
    never ``*_cost_preferred`` (that requires data; ADR-0046 §6).
    """
    direction = demand.direction
    if direction is None:
        return ResolveReason(ReasonCode.NO_DEMAND)

    candidates = [d for d in devices if d.has(Axis.THERMAL, direction)]
    if not candidates:
        return ResolveReason(ReasonCode.NO_CAPABLE_SOURCE)

    def _rank(dev: ZoneDevice) -> tuple[int, str]:
        cap = dev.capability(Axis.THERMAL, direction)
        prio = cap.priority if cap is not None else 1000
        return (prio, dev.entity_id)

    ranked = sorted(candidates, key=_rank)
    blocked: list[BlockingCause] = []
    selected: ZoneDevice | None = None
    for dev in ranked:
        cause = _block_cause(runtimes.get(dev.entity_id, DeviceRuntime()))
        if cause is None:
            selected = dev
            break
        blocked.append(cause)

    if selected is None:
        return ResolveReason(ReasonCode.NO_CAPABLE_SOURCE, blocked=tuple(blocked))

    if blocked:  # the top-ranked candidate(s) were blocked -> this is a failover
        return ResolveReason(
            ReasonCode.FAILOVER_PRIMARY_UNHEALTHY,
            selected_source=selected.entity_id,
            blocked=tuple(blocked),
            fallback=FallbackCause.PRIMARY_UNHEALTHY,
        )
    return ResolveReason(
        _PRIORITY_REASON[direction], selected_source=selected.entity_id
    )


def humidity_resolver(*_: object) -> ResolveReason:
    """No-op until P4 (ADR-0046 §4). Stable interface, emits no commands."""
    return ResolveReason(ReasonCode.HUMIDITY_NOOP)


def air_movement_resolver(*_: object) -> ResolveReason:
    """No-op until P6 (ADR-0046 §4). Stable interface, emits no commands."""
    return ResolveReason(ReasonCode.AIR_MOVEMENT_NOOP)


_SERVICE_FOR_KIND: Mapping[str, str] = {
    "hvac_mode": "set_hvac_mode",
    "preset_mode": "set_preset_mode",
    "fan_mode": "set_fan_mode",
    CMD_SERVICE: "turn_on",
}


def _service_for(kind: str) -> str:
    # representative service name; the glue maps kind+domain to the real call
    return _SERVICE_FOR_KIND.get(kind, "set_hvac_mode")


def _standby_command(dev: ZoneDevice, now_wall: float) -> Command | None:
    policy = dev.standby_policy
    if policy is StandbyPolicy.LEAVE_AS_IS:
        return None
    service = "turn_off" if policy is StandbyPolicy.OFF else "set_hvac_mode"
    return Command(
        entity_id=dev.entity_id,
        domain=dev.domain,
        service=service,
        capability_id="standby",
        reason=ReasonCode.STANDBY,
        issued_at_wall=now_wall,
        dedupe_key=f"{dev.entity_id}:standby:{policy.value}",
    )


def assignment_planner(
    thermal: ResolveReason,
    demand: ThermalDemand,
    devices: Sequence[ZoneDevice],
    *,
    now_wall: float,
) -> tuple[dict[str, Command], ResolveReason]:
    """Build (never execute) the per-device commands a shadow displays. The
    selected source gets its thermal command; every other device gets its
    standby command. Reason objects are pure diagnostics — they never change a
    control decision (ADR-0046 §15).
    """
    commands: dict[str, Command] = {}
    selected = thermal.selected_source
    direction = demand.direction
    target = demand.target_c

    for dev in devices:
        cap = (
            dev.capability(Axis.THERMAL, direction)
            if (dev.entity_id == selected and direction is not None)
            else None
        )
        if cap is not None:
            mode = cap.mode_command or ""
            sp = cap.setpoint_command
            data: dict[str, Any] = {}
            echo: dict[str, Any] = {}
            if cap.command_kind == "hvac_mode" and mode:
                echo["hvac_mode"] = mode
            if sp is not None and target is not None:
                data[sp] = round(target, 1)
                echo[sp] = round(target, 1)
            target_str = "" if target is None else f"{round(target, 1)}"
            commands[dev.entity_id] = Command(
                entity_id=dev.entity_id,
                domain=dev.domain,
                service=_service_for(cap.command_kind),
                capability_id=cap.capability_id,
                reason=thermal.reason,
                issued_at_wall=now_wall,
                dedupe_key=f"{dev.entity_id}:{mode}:{target_str}",
                data=data,
                expected_echo=echo,
            )
        else:
            standby = _standby_command(dev, now_wall)
            if standby is not None:
                commands[dev.entity_id] = standby
    return commands, thermal
