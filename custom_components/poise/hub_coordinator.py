"""Multi-zone hub coordinator — shared-resource aggregation (ADR-0038/0039).

Phase 2 of the two-phase tick — note it is **not synchronous**: hub and zones
tick independently (60 s each), so the hub reads each zone's *last published*
snapshot, up to ~60 s old (review #6). For boiler aggregation with activation
delay + min-cycle this staleness is immaterial.

All control decisions — including the tick-crossing boiler/compressor state
machines — live in the pure, unit-tested ``hub_aggregate`` helpers
(``step_boiler``/``step_min_cycle``); this module only reads HA state and
performs the single service call. With no boiler actions configured it stays
shadow-only. Load shedding (S3) and compressor grouping (S4) are computed as
diagnostics; zone-side enforcement is a later stage.
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
    CONF_COMPRESSOR_GROUP,
    CONF_CONTROLS_BOILER,
    CONF_CURRENT_POWER_SENSOR,
    CONF_DECLARED_POWER,
    CONF_DEFAULT_SOURCE,
    CONF_ENTRY_TYPE,
    CONF_FLOW_HYSTERESIS,
    CONF_FLOW_TEMP,
    CONF_MAX_FLOW_TEMP,
    CONF_MAX_POWER_SENSOR,
    CONF_SOURCE_POLICY,
    DEFAULT_BOILER_ACTIVATION_DELAY_S,
    DEFAULT_BOILER_COUNT_THRESHOLD,
    DEFAULT_BOILER_KEEPALIVE_S,
    DEFAULT_BOILER_MIN_OFF_S,
    DEFAULT_BOILER_MIN_ON_S,
    DEFAULT_FLOW_HYSTERESIS_C,
    DEFAULT_HEAT_SOURCE,
    DEFAULT_MAX_FLOW_TEMP_C,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    TICK_INTERVAL_S,
)
from .contracts import ZoneRequest
from .control.hub_aggregate import (
    BoilerState,
    ServiceAction,
    aggregate_boiler_demand,
    group_call_for_heat,
    parse_service_action,
    resolve_flow_temperature,
    resolve_load_shedding,
    resolve_source_policy,
    step_boiler,
    step_min_cycle,
    zone_request_from_data,
)

_LOGGER = logging.getLogger(__name__)


class PoiseHubCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Singleton hub: aggregates and (opt-in) actuates the shared boiler."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
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
        self._boiler = BoilerState()
        # S3 load shedding + S4 compressor groups (shadow stage)
        self._max_power_sensor = d.get(CONF_MAX_POWER_SENSOR)
        self._current_power_sensor = d.get(CONF_CURRENT_POWER_SENSOR)
        # NOTE: compressor min-cycle reuses the boiler timers for the shadow;
        # a heat-pump compressor needs its own (longer) min-off before actuation
        # is wired (review #5).
        self._group_on: dict[str, bool] = {}
        self._group_switch: dict[str, float] = {}
        self._max_flow = float(d.get(CONF_MAX_FLOW_TEMP, DEFAULT_MAX_FLOW_TEMP_C))
        self._flow_hysteresis = float(
            d.get(CONF_FLOW_HYSTERESIS, DEFAULT_FLOW_HYSTERESIS_C)
        )
        self._flow_current: float | None = None
        self._default_source = str(d.get(CONF_DEFAULT_SOURCE, DEFAULT_HEAT_SOURCE))

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
            dp = e.data.get(CONF_DECLARED_POWER)
            out.append(
                zone_request_from_data(
                    e.entry_id,
                    data,
                    controls_boiler=bool(e.data.get(CONF_CONTROLS_BOILER, False)),
                    declared_power=float(dp) if dp else None,
                    compressor_group=e.data.get(CONF_COMPRESSOR_GROUP),
                    flow_temp_request=(
                        float(ft) if (ft := e.data.get(CONF_FLOW_TEMP)) else None
                    ),
                    source_pref=e.data.get(CONF_SOURCE_POLICY),
                    mono_ts=now,
                )
            )
        return out

    def _power(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        st = self.hass.states.get(entity_id)
        if st is None or st.state in ("unknown", "unavailable", ""):
            return None
        try:
            return float(st.state)
        except (ValueError, TypeError):
            return None

    def _shared_resource_shadow(
        self, requests: list[ZoneRequest], now: float
    ) -> dict[str, Any]:
        """S3 load-shedding + S4 compressor-group shadow (computed, not enforced)."""
        max_p = self._power(self._max_power_sensor)
        cur_p = self._power(self._current_power_sensor)
        available = (max_p - cur_p) if max_p is not None and cur_p is not None else None
        shedding = (
            resolve_load_shedding(requests, available_power=available)
            if available is not None
            else None
        )
        groups: dict[str, bool] = {}
        for grp, want in group_call_for_heat(requests).items():
            on, switch = step_min_cycle(
                prev_on=self._group_on.get(grp, False),
                prev_switch_mono=self._group_switch.get(grp, -1.0e9),
                demand=want,
                now_mono=now,
                min_on_s=self._min_on,
                min_off_s=self._min_off,
            )
            self._group_on[grp] = on
            self._group_switch[grp] = switch
            groups[grp] = on
        flow = resolve_flow_temperature(
            requests,
            current=self._flow_current,
            max_flow=self._max_flow,
            hysteresis=self._flow_hysteresis,
        )
        self._flow_current = flow.target
        return {
            "available_power": round(available, 1) if available is not None else None,
            "shed_zones": list(shedding.shed) if shedding else [],
            "shed_count": len(shedding.shed) if shedding else 0,
            "compressor_groups": groups,
            "flow_target": flow.target,
            "flow_requested": flow.requested_max,
            "source_grants": resolve_source_policy(
                requests, default_source=self._default_source
            ),
        }

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
        step = step_boiler(
            self._boiler,
            demand=demand_active,
            now_mono=now,
            activation_delay_s=self._activation_delay,
            min_on_s=self._min_on,
            min_off_s=self._min_off,
            keepalive_s=self._keepalive,
        )
        self._boiler = step.state
        if step.call == "on" and self._action_on is not None:
            await self._call(self._action_on)
        elif step.call == "off" and self._action_off is not None:
            await self._call(self._action_off)

    async def _async_update_data(self) -> dict[str, Any]:
        now = self._clock.monotonic()
        requests = self._collect_requests()
        demand = aggregate_boiler_demand(
            requests,
            count_threshold=self._count_threshold,
            power_threshold=self._power_threshold,
        )
        if self._actuation:
            await self._actuate(demand.active, now)
        return {
            "boiler_demand": demand.active,
            "active_zones": demand.active_count,
            "weighted_demand": demand.weighted_demand,
            "frost_override": demand.frost_override,
            "zone_count": len(requests),
            "controlling_zones": sum(1 for r in requests if r.controls_boiler),
            "actuation_enabled": self._actuation,
            "boiler_on": self._boiler.on,
            **self._shared_resource_shadow(requests, now),
        }
