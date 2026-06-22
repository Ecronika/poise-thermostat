"""Multi-zone hub coordinator — shared-resource aggregation (ADR-0038/0039).

Phase 2 of the two-phase tick. Reads each loaded Poise *zone* coordinator's last
``data`` dict, builds a :class:`ZoneRequest`, and aggregates shared-resource
decisions. S1 ships the boiler-demand **shadow**: it computes the aggregate and
exposes it as a diagnostic ``binary_sensor`` — it never calls a switch service
(no actuation). All decisions come from the pure, tested ``hub_aggregate``
helpers; this module is only HA glue (single writer of shared resources later).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .clock import MonotonicClock
from .const import (
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_BOILER_POWER_THRESHOLD,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    DEFAULT_BOILER_COUNT_THRESHOLD,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    TICK_INTERVAL_S,
)
from .contracts import ZoneRequest
from .control.hub_aggregate import aggregate_boiler_demand

_LOGGER = logging.getLogger(__name__)


def zone_request_from_data(
    zone_id: str, data: dict[str, Any], *, controls_boiler: bool, mono_ts: float
) -> ZoneRequest:
    """Build a ZoneRequest from a zone coordinator's published ``data`` dict."""
    heating = bool(data.get("heating"))
    cause = str(data.get("binding_lower_cause") or "")
    duty = data.get("tpi_duty")
    heat_demand = float(duty) if duty is not None else (1.0 if heating else 0.0)
    room = data.get("current_temperature")
    sp = data.get("heat_sp")
    gap = (float(sp) - float(room)) if room is not None and sp is not None else 0.0
    return ZoneRequest(
        zone_id=zone_id,
        heating=heating,
        hvac_action="heating" if heating else "idle",
        heat_demand=heat_demand,
        comfort_gap=gap,
        frost_active="frost" in cause.lower(),
        controls_boiler=controls_boiler,
        mono_ts=mono_ts,
    )


class PoiseHubCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Singleton hub: aggregates shared-resource decisions across all zones."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_hub",
            update_interval=timedelta(seconds=TICK_INTERVAL_S),
            always_update=False,
        )
        self._clock = MonotonicClock()
        self._entry = entry
        self._count_threshold = int(
            entry.data.get(CONF_BOILER_COUNT_THRESHOLD, DEFAULT_BOILER_COUNT_THRESHOLD)
        )
        pw = entry.data.get(CONF_BOILER_POWER_THRESHOLD)
        self._power_threshold = float(pw) if pw else None

    def _collect_requests(self) -> list[ZoneRequest]:
        now = self._clock.monotonic()
        out: list[ZoneRequest] = []
        for e in self.hass.config_entries.async_entries(DOMAIN):
            if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM:
                continue  # skip the hub itself
            coord = getattr(e, "runtime_data", None)
            data = getattr(coord, "data", None)
            if not isinstance(data, dict) or not data.get("available"):
                continue
            controls = bool(e.data.get(CONF_CONTROLS_BOILER, True))
            out.append(
                zone_request_from_data(
                    e.entry_id, data, controls_boiler=controls, mono_ts=now
                )
            )
        return out

    async def _async_update_data(self) -> dict[str, Any]:
        requests = self._collect_requests()
        demand = aggregate_boiler_demand(
            requests,
            count_threshold=self._count_threshold,
            power_threshold=self._power_threshold,
        )
        return {
            "boiler_demand": demand.active,
            "active_zones": demand.active_count,
            "weighted_demand": demand.weighted_demand,
            "frost_override": demand.frost_override,
            "zone_count": len(requests),
        }
