"""The atomic, deterministic tick (ADR-0006, ADR-0014).

This module is **pure**: it imports no Home Assistant. That keeps the control
logic fast and deterministically testable (ADR-0011) and enforces the
downward dependency direction (ADR-0005). The HA coordinator (coordinator.py)
merely wraps :func:`run_tick` with a lock and a refresh schedule.

Per-tick order (subset for Phase 0; full order in the Programmstrukturplan):
    ingest -> comfort(corridor) -> control -> arbitration -> one command/zone
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from . import arbitration
from .clock import Clock
from .contracts import (
    ActuatorCommand,
    Bound,
    ComfortCorridor,
    Maturity,
    Reading,
    ThermalState,
)
from .controller import Controller


@dataclass(frozen=True, slots=True)
class ZoneInputs:
    """Conditioned per-zone inputs handed to the tick (Phase 0 shape)."""

    actuator_id: str
    t_air: Reading
    target: float
    frost_floor: float
    device_max: float
    mold_min: float | None = None


def build_corridor(zone: ZoneInputs) -> ComfortCorridor:
    """Compose the comfort corridor; binding bound is computed later (ADR-0013).

    Phase 0 uses a fixed target band; Phase 1 replaces this with the EN 16798
    adaptive band on T_rm plus the mould-protection minimum (ADR-0017).
    """
    lower = [Bound(zone.frost_floor, "frost")]
    if zone.mold_min is not None:
        lower.append(Bound(zone.mold_min, "mold"))
    upper = [Bound(zone.device_max, "device_max")]
    return ComfortCorridor(tuple(lower), tuple(upper), zone.target, "air")


def _state_from(zone: ZoneInputs) -> ThermalState:
    """Phase-0 trivial state straight from the air reading.

    The Extended Kalman Filter populates tau/losses/betas from Phase 2 (ADR-0002).
    """
    return ThermalState(
        t_air=zone.t_air.value,
        tau=0.0,
        loss_uc=0.0,
        beta_h=0.0,
        beta_c=0.0,
        beta_s=0.0,
        beta_o=0.0,
        q_solar=0.0,
        t_rm=zone.t_air.value,
        confidence=zone.t_air.confidence,
        maturity=Maturity.COLD,
    )


def run_tick(
    zones: Mapping[str, ZoneInputs],
    *,
    clock: Clock,
    controller: Controller,
) -> dict[str, ActuatorCommand]:
    """Run one atomic tick over all zones.

    Determinism (ADR-0014): zones are processed in sorted key order, there is
    no hidden randomness, and the only time source is the injected ``clock``.
    Isolation (ADR-0012): a failure in one zone never aborts the tick.
    """
    _ = clock  # reserved for Phase 1+ (timing-dependent comfort/learning)
    commands: dict[str, ActuatorCommand] = {}
    for zone_id in sorted(zones):
        zone = zones[zone_id]
        try:
            corridor = build_corridor(zone)
            state = _state_from(zone)
            request = controller.evaluate(state, corridor, zone.actuator_id)
            commands[zone_id] = arbitration.resolve(
                corridor, request, device_max=zone.device_max
            )
        except Exception:  # noqa: BLE001 - per-zone isolation by design (ADR-0012)
            continue
    return commands
