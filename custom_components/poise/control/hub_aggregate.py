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
