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

from ..contracts import ZoneRequest


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0)


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
    frost_override = any(r.frost_active for r in participating)
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
        (r for r in requests if r.heating and r.declared_power and not r.frost_active),
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
