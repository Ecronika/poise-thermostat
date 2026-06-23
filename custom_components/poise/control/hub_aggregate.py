"""Pure multi-zone resource aggregation for the hub (ADR-0038/0039).

HA-free and fully testable: given the set of :class:`ZoneRequest`s, compute the
shared-resource decisions. S0 ships the boiler-demand aggregate (ADR-0039); the
hub glue (registry, coordinator, actuation) consumes these helpers and never
re-decides. Frost safety wins over thresholds; min-cycle gating prevents
short-cycling (ADR-0006 monotonic time, passed in by the caller).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..const import FROST_FLOOR_C
from ..contracts import ZoneRequest


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0)


# a room at or just above the frost floor is in the anti-freeze regime
_FROST_MARGIN_C = 0.5


def zone_request_from_data(
    zone_id: str,
    data: dict[str, Any],
    *,
    controls_boiler: bool,
    declared_power: float | None,
    compressor_group: str | None,
    flow_temp_request: float | None,
    mono_ts: float,
) -> ZoneRequest:
    """Build a ZoneRequest from a zone's published ``data`` dict + its config.

    Pure and unit-tested (review #1/#2). ``heat_demand`` uses the live tpi_duty
    shadow estimate when present, else a binary fall-back from ``heating``
    (review #7). ``frost_active`` is a PHYSICAL signal derived from the room
    temperature — the binding-cause string never carries "frost" (the frost
    floor is the lowest bound and never binds the lower cause), so the old
    cause-string derivation was always False (review #2). ``health_active`` is
    read from the mould binding cause, which the coordinator does publish.
    """
    heating = bool(data.get("heating"))
    cause = str(data.get("binding_lower_cause") or "").lower()
    duty = data.get("tpi_duty")
    heat_demand = float(duty) if duty is not None else (1.0 if heating else 0.0)
    room = data.get("current_temperature")
    sp = data.get("heat_sp")
    gap = (float(sp) - float(room)) if room is not None and sp is not None else 0.0
    frost_active = room is not None and float(room) <= FROST_FLOOR_C + _FROST_MARGIN_C
    health_active = "mould" in cause or "schimmel" in cause or "mold" in cause
    return ZoneRequest(
        zone_id=zone_id,
        heating=heating,
        hvac_action="heating" if heating else "idle",
        heat_demand=heat_demand,
        comfort_gap=gap,
        frost_active=frost_active,
        controls_boiler=controls_boiler,
        mono_ts=mono_ts,
        declared_power=declared_power,
        compressor_group=compressor_group,
        flow_temp_request=flow_temp_request,
        health_active=health_active,
    )


@dataclass(frozen=True, slots=True)
class BoilerDemand:
    """Aggregated call-for-heat for a shared heat generator (ADR-0039)."""

    active: bool
    active_count: int
    weighted_demand: float
    frost_override: bool


def aggregate_boiler_demand(
    requests: Sequence[ZoneRequest],
    *,
    count_threshold: int = 1,
    power_threshold: float | None = None,
) -> BoilerDemand:
    """Decide whether a shared boiler should run, from opt-in zones only.

    Only zones with ``controls_boiler`` participate. A zone calls for heat when
    ``heating`` is true; its weighted contribution is
    ``(declared_power or 1.0) * clamp01(heat_demand)``. Demand is active when the
    count of calling zones reaches ``count_threshold`` OR (when configured) the
    weighted sum reaches ``power_threshold``. Any participating zone in frost
    protection forces demand on, independent of thresholds (frost-safe).
    """
    participating = [r for r in requests if r.controls_boiler]
    calling = [r for r in participating if r.heating]
    active_count = len(calling)
    weighted = sum((r.declared_power or 1.0) * _clamp01(r.heat_demand) for r in calling)
    # frost safety considers ALL zones, not just opt-in ones: a freezing room
    # must be able to fire a shared boiler even if mis-configured (ADR-0039).
    frost_override = any(r.frost_active for r in requests)
    by_count = active_count >= count_threshold
    by_power = power_threshold is not None and weighted >= power_threshold
    return BoilerDemand(
        active=frost_override or by_count or by_power,
        active_count=active_count,
        weighted_demand=round(weighted, 3),
        frost_override=frost_override,
    )


def gate_min_cycle(
    desired_on: bool,
    *,
    currently_on: bool,
    last_change_mono: float,
    now_mono: float,
    min_on_s: float,
    min_off_s: float,
) -> bool:
    """Hold the generator state until min-on/min-off elapsed (anti short-cycle).

    Returns the gated on/off. A desired change is blocked until the relevant
    minimum dwell has passed since the last change (ADR-0006 monotonic time).
    """
    if desired_on == currently_on:
        return currently_on
    elapsed = now_mono - last_change_mono
    if currently_on:  # want to turn off
        return elapsed < min_on_s  # stay on until min-on satisfied
    return elapsed >= min_off_s  # turn on only once min-off satisfied


@dataclass(frozen=True, slots=True)
class ServiceAction:
    """A parsed HA service call: ``domain.service`` plus call data (ADR-0039)."""

    domain: str
    service: str
    data: dict[str, str]


def parse_service_action(spec: str | None) -> ServiceAction | None:
    """Parse ``entity_id/domain.service[/attr:value...]`` (Versatile format).

    Returns None for empty/malformed specs (the hub then stays shadow-only).
    Attribute values are kept as strings (e.g. ``hvac_mode:heat``).
    """
    if not spec:
        return None
    parts = [p.strip() for p in spec.split("/") if p.strip()]
    if len(parts) < 2 or "." not in parts[0] or "." not in parts[1]:
        return None
    domain, service = parts[1].split(".", 1)
    data: dict[str, str] = {"entity_id": parts[0]}
    for extra in parts[2:]:
        if ":" in extra:
            key, value = extra.split(":", 1)
            data[key.strip()] = value.strip()
    return ServiceAction(domain=domain.strip(), service=service.strip(), data=data)


def target_boiler_state(
    demand: bool,
    *,
    currently_on: bool,
    demand_true_since: float | None,
    now_mono: float,
    activation_delay_s: float,
    last_switch_mono: float,
    min_on_s: float,
    min_off_s: float,
) -> bool:
    """Resolve the commanded boiler state from demand + timing guards (ADR-0039).

    Turning ON additionally waits ``activation_delay_s`` of continuous demand
    (valve-open time); turning OFF has no delay. The result is then min-cycle
    gated (anti short-cycle). Pure: all time is passed in (ADR-0006).
    """
    if not currently_on:
        ready = (
            demand
            and demand_true_since is not None
            and (now_mono - demand_true_since) >= activation_delay_s
        )
        desired = ready
    else:
        desired = demand
    return gate_min_cycle(
        desired,
        currently_on=currently_on,
        last_change_mono=last_switch_mono,
        now_mono=now_mono,
        min_on_s=min_on_s,
        min_off_s=min_off_s,
    )


@dataclass(frozen=True, slots=True)
class SheddingResult:
    """Which zones to shed to fit the power budget (ADR-0013, Versatile method)."""

    shed: tuple[str, ...]  # zone_ids, in the order they were shed
    freed_power: float
    deficit: float


def resolve_load_shedding(
    requests: Sequence[ZoneRequest], *, available_power: float
) -> SheddingResult:
    """Smallest-gap load shedding (Versatile method, ADR-0013).

    ``available_power = max_power - current_power`` (negative = overload). When
    overloaded, heating zones are shed **closest to their setpoint first** (they
    can best spare the heat) until the deficit is covered. A zone in frost
    protection is never shed (frost-safe). Zones without a declared power are
    not sheddable (unknown contribution). Pure: no actuation, no time.
    """
    if available_power >= 0:
        return SheddingResult((), 0.0, 0.0)
    deficit = -available_power
    candidates = sorted(
        (
            r
            for r in requests
            if r.heating
            and r.declared_power
            and not r.frost_active
            and not r.health_active  # mould/health floor also protected
        ),
        key=lambda r: r.comfort_gap,  # smallest gap = nearest setpoint = shed first
    )
    shed: list[str] = []
    freed = 0.0
    for r in candidates:
        if freed >= deficit:
            break
        shed.append(r.zone_id)
        freed += float(r.declared_power or 0.0)
    return SheddingResult(tuple(shed), round(freed, 3), round(deficit, 3))


def group_call_for_heat(requests: Sequence[ZoneRequest]) -> dict[str, bool]:
    """Per compressor group: does any member zone currently call for heat?

    Groups a shared outdoor unit; the hub then applies min-run/off (ADR-0013)
    via :func:`gate_min_cycle` per group. Zones without a group are ignored.
    """
    out: dict[str, bool] = {}
    for r in requests:
        if r.compressor_group:
            out[r.compressor_group] = out.get(r.compressor_group, False) or r.heating
    return out


@dataclass(frozen=True, slots=True)
class BoilerState:
    """Tick-crossing boiler orchestration state (pure; ADR-0039)."""

    on: bool = False
    last_switch_mono: float = -1.0e9  # allow an immediate first switch
    demand_true_since: float | None = None
    last_keepalive_mono: float = 0.0


@dataclass(frozen=True, slots=True)
class BoilerStep:
    """Result of one orchestration step: the next state and the call to make."""

    state: BoilerState
    call: str | None  # "on" | "off" | None — which action the hub should invoke


def step_boiler(
    state: BoilerState,
    *,
    demand: bool,
    now_mono: float,
    activation_delay_s: float,
    min_on_s: float,
    min_off_s: float,
    keepalive_s: float,
) -> BoilerStep:
    """Advance the boiler state machine by one tick (pure, fully testable).

    Folds the activation latch (``demand_true_since``), the activation delay,
    the min-on/min-off cycle guard (:func:`target_boiler_state`) and the
    keep-alive resend into one deterministic transition. The coordinator only
    performs the returned ``call`` — no control state lives in the glue, so the
    hardware-protecting logic is unit-tested, not 0%-covered (review #1).
    """
    demand_true_since = state.demand_true_since
    if demand and demand_true_since is None:
        demand_true_since = now_mono
    elif not demand:
        demand_true_since = None
    target = target_boiler_state(
        demand,
        currently_on=state.on,
        demand_true_since=demand_true_since,
        now_mono=now_mono,
        activation_delay_s=activation_delay_s,
        last_switch_mono=state.last_switch_mono,
        min_on_s=min_on_s,
        min_off_s=min_off_s,
    )
    if target != state.on:
        return BoilerStep(
            BoilerState(
                on=target,
                last_switch_mono=now_mono,
                demand_true_since=demand_true_since,
                last_keepalive_mono=now_mono,
            ),
            "on" if target else "off",
        )
    if (
        state.on
        and keepalive_s > 0.0
        and (now_mono - state.last_keepalive_mono) >= keepalive_s
    ):
        return BoilerStep(
            BoilerState(
                on=state.on,
                last_switch_mono=state.last_switch_mono,
                demand_true_since=demand_true_since,
                last_keepalive_mono=now_mono,
            ),
            "on",
        )
    return BoilerStep(
        BoilerState(
            on=state.on,
            last_switch_mono=state.last_switch_mono,
            demand_true_since=demand_true_since,
            last_keepalive_mono=state.last_keepalive_mono,
        ),
        None,
    )


def step_min_cycle(
    *,
    prev_on: bool,
    prev_switch_mono: float,
    demand: bool,
    now_mono: float,
    min_on_s: float,
    min_off_s: float,
) -> tuple[bool, float]:
    """One min-cycle transition for a shared resource (e.g. compressor group).

    Returns ``(new_on, new_switch_mono)``; the switch timestamp only advances
    on an actual state change. Pure — the hub stores the returned tuple.
    """
    on = gate_min_cycle(
        demand,
        currently_on=prev_on,
        last_change_mono=prev_switch_mono,
        now_mono=now_mono,
        min_on_s=min_on_s,
        min_off_s=min_off_s,
    )
    return on, (now_mono if on != prev_on else prev_switch_mono)


@dataclass(frozen=True, slots=True)
class FlowDecision:
    """The flow-temperature setpoint for a shared heat generator (ADR-0013, S5)."""

    target: float | None  # commanded flow setpoint (None = no flow demand)
    requested_max: float | None  # highest requested flow temp (pre-hysteresis)
    changed: bool  # did the command move (past hysteresis) this tick


def resolve_flow_temperature(
    requests: Sequence[ZoneRequest],
    *,
    current: float | None,
    max_flow: float,
    hysteresis: float,
) -> FlowDecision:
    """Highest-request-wins flow allocation, capped, with anti-hunt hysteresis.

    A single shared flow must satisfy the **most demanding** heating zone, so the
    max requested flow temperature wins, clamped to ``max_flow``. To stop the
    generator hunting on small fluctuations (the risk ADR-0013 flagged for this
    no-field-reference design), the command only moves when the new request
    differs from the current command by at least ``hysteresis``. Pure: no time,
    no actuation; the hub holds ``current`` across ticks. Harness-validated
    against oscillation (ADR-0011, ``run_flow_allocator``).
    """
    reqs = [
        r.flow_temp_request
        for r in requests
        if r.heating and r.flow_temp_request is not None
    ]
    if not reqs:
        return FlowDecision(None, None, current is not None)  # demand gone -> release
    requested = min(max(reqs), max_flow)
    if current is None:
        return FlowDecision(requested, requested, True)
    if abs(requested - current) < hysteresis:
        return FlowDecision(current, requested, False)  # within band -> hold
    return FlowDecision(requested, requested, True)
