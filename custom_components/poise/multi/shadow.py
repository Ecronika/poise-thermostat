"""Thermal-arbitration shadow evaluator (ADR-0046 §14, Phase 1).

Runs the pure thermal pipeline against the zone's actuator — built as a transient
``ZoneDevice`` via the read-path (ADR-0046 §13) — and returns a flat,
diagnostics-friendly result: the source Poise *would* drive and why. P1 is
shadow-only: this emits **no** command and changes **no** actuator write; it only
exposes the active source + reason so the seam can be observed before TRV+AC
arbitration goes live (P3).
"""

from __future__ import annotations

from dataclasses import dataclass

from .discovery import EntitySnapshot, transient_zone_device
from .model import DeviceHealth
from .resolvers import DeviceRuntime, ThermalDemand, thermal_resolver


@dataclass(frozen=True, slots=True)
class ThermalShadow:
    """Flat, HA-attribute-friendly view of the thermal pipeline's choice."""

    active_source: str | None  # entity_id of the chosen source, or None
    reason: str  # ReasonCode value (stable code, not localised text)
    severity: str  # Severity value ("info" | "warn")
    blocked: tuple[str, ...]  # BlockingCause values that vetoed candidates
    capabilities: tuple[str, ...]  # the device's capability ids (e.g. "thermal:heat")


def evaluate_thermal_shadow(
    snapshot: EntitySnapshot,
    demand: ThermalDemand,
    *,
    runtime: DeviceRuntime | None = None,
    role: str | None = None,
) -> ThermalShadow:
    """Which thermal source would the pipeline pick for this demand, and why.

    Pure + HA-free. ``runtime`` defaults from ``snapshot.available`` (an
    unavailable actuator is reported as blocked, never silently selected).
    """
    device = transient_zone_device(snapshot, role=role)
    if runtime is None:
        runtime = DeviceRuntime(
            health=DeviceHealth.OK if snapshot.available else DeviceHealth.UNAVAILABLE
        )
    reason = thermal_resolver(demand, [device], {device.entity_id: runtime})
    return ThermalShadow(
        active_source=reason.selected_source,
        reason=reason.reason.value,
        severity=reason.severity.value,
        blocked=tuple(b.value for b in reason.blocked),
        capabilities=tuple(c.capability_id for c in device.capabilities),
    )
