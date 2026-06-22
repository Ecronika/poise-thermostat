"""Multi-zone hub coordinator — shared-resource aggregation (ADR-0038/0039).

Phase 2 of the two-phase tick. Reads each loaded Poise *zone* coordinator's last
``data`` dict, builds a :class:`ZoneRequest`, aggregates the boiler demand from
the opt-in zones, and — only if both on/off actions are configured — actuates a
shared boiler (Stufe 2). All decisions come from the pure, tested
``hub_aggregate`` helpers; this module is HA glue (single writer of the boiler).
With no actions configured it stays shadow-only (just the diagnostic sensor).
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
    CONF_BOILER_ACTIVATION_DELAY,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_BOILER_KEEPALIVE,
    CONF_BOILER_MIN_OFF,
    CONF_BOILER_MIN_ON,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_BOILER_POWER_THRESHOLD,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    DEFAULT_BOILER_ACTIVATION_DELAY_S,
    DEFAULT_BOILER_COUNT_THRESHOLD,
    DEFAULT_BOILER_KEEPALIVE_S,
    DEFAULT_BOILER_MIN_OFF_S,
    DEFAULT_BOILER_MIN_ON_S,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    TICK_INTERVAL_S,
)
from .contracts import ZoneRequest
from .control.hub_aggregate import (
    ServiceAction,
    aggregate_boiler_demand,
    parse_service_action,
    target_boiler_state,
)

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
    """Singleton hub: aggregates and (opt-in) actuates the shared boiler."""

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
        d = entry.data
        self._count_threshold = int(
            d.get(CONF_BOILER_COUNT_THRESHOLD, DEFAULT_BOILER_COUNT_THRESHOLD)
        )
        pw = d.get(CONF_BOILER_POWER_THRESHOLD)
        self._power_threshold = float(pw) if pw else None
        # actuation (Stufe 2) — only active when BOTH actions parse (opt-in)
        self._action_on = parse_service_action(d.get(CONF_BOILER_ON_ACTION))
        self._action_off = parse_service_action(d.get(CONF_BOILER_OFF_ACTION))
        self._actuation = self._action_on is not None and self._action_off is not None
        self._activation_delay = float(
            d.get(CONF_BOILER_ACTIVATION_DELAY, DEFAULT_BOILER_ACTIVATION_DELAY_S)
        )
        self._keepalive = float(
            d.get(CONF_BOILER_KEEPALIVE, DEFAULT_BOILER_KEEPALIVE_S)
        )
        self._min_on = float(d.get(CONF_BOILER_MIN_ON, DEFAULT_BOILER_MIN_ON_S))
        self._min_off = float(d.get(CONF_BOILER_MIN_OFF, DEFAULT_BOILER_MIN_OFF_S))
        self._boiler_on = False
        self._last_switch_mono = -1.0e9  # allow an immediate first switch
        self._demand_true_since: float | None = None
        self._last_keepalive_mono = 0.0

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
            controls = bool(e.data.get(CONF_CONTROLS_BOILER, False))  # opt-in
            out.append(
                zone_request_from_data(
                    e.entry_id, data, controls_boiler=controls, mono_ts=now
                )
            )
        return out

    async def _call(self, action: ServiceAction) -> None:
        try:
            await self.hass.services.async_call(
                action.domain, action.service, dict(action.data), blocking=False
            )
        except Exception:
            _LOGGER.exception(
                "Poise boiler action failed: %s.%s", action.domain, action.service
            )

    async def _actuate(self, demand_active: bool, now: float) -> None:
        if demand_active and self._demand_true_since is None:
            self._demand_true_since = now
        elif not demand_active:
            self._demand_true_since = None
        target = target_boiler_state(
            demand_active,
            currently_on=self._boiler_on,
            demand_true_since=self._demand_true_since,
            now_mono=now,
            activation_delay_s=self._activation_delay,
            last_switch_mono=self._last_switch_mono,
            min_on_s=self._min_on,
            min_off_s=self._min_off,
        )
        if target != self._boiler_on:
            action = self._action_on if target else self._action_off
            assert action is not None  # _actuation guarantees both are set
            await self._call(action)
            self._boiler_on = target
            self._last_switch_mono = now
            self._last_keepalive_mono = now
        elif (
            self._boiler_on
            and self._keepalive > 0.0
            and (now - self._last_keepalive_mono) >= self._keepalive
            and self._action_on is not None
        ):
            await self._call(self._action_on)
            self._last_keepalive_mono = now

    async def _async_update_data(self) -> dict[str, Any]:
        requests = self._collect_requests()
        demand = aggregate_boiler_demand(
            requests,
            count_threshold=self._count_threshold,
            power_threshold=self._power_threshold,
        )
        if self._actuation:
            await self._actuate(demand.active, self._clock.monotonic())
        return {
            "boiler_demand": demand.active,
            "active_zones": demand.active_count,
            "weighted_demand": demand.weighted_demand,
            "frost_override": demand.frost_override,
            "zone_count": len(requests),
            "controlling_zones": sum(1 for r in requests if r.controls_boiler),
            "actuation_enabled": self._actuation,
            "boiler_on": self._boiler_on,
        }
