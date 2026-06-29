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

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
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
    HUB_ZONE_STALE_AFTER_S,
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
_BOILER_CALL_TIMEOUT_S = 10.0  # a hung boiler service must not stall the hub (N-1)


class PoiseHubCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
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
        self._active_issues: set[str] = set()

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
            # H3/ADR-0038: a zone whose last coordinator update failed exposes a
            # stale snapshot — never call for heat on it (the zone entity already
            # reports unavailable via last_update_success; the hub must match).
            if not getattr(coord, "last_update_success", True):
                continue
            # H3/ADR-0038: drop a zone whose snapshot is too old even though its
            # coordinator still "succeeds" — a silently hung update loop must not
            # call for heat forever. Both stamps use the process monotonic clock.
            zmono = data.get("mono_ts")
            # review 2.2: a MISSING stamp is fail-CLOSED — treat the zone as stale
            # and drop it, instead of stamping it "now" (eternally fresh), which
            # would let a silently hung / version-mismatched zone call for heat
            # forever (the very failure this age check exists to prevent).
            if zmono is None or (now - float(zmono)) > HUB_ZONE_STALE_AFTER_S:
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
                    mono_ts=float(zmono),  # guaranteed present by the guard above
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

    async def _call(self, action: ServiceAction) -> bool:
        # blocking=True so a failed boiler action is observable synchronously
        # (review 2.3); wrapped in a timeout so a hung boiler integration cannot
        # stall the whole hub tick (review N-1). A timeout/error counts as failure
        # -> the caller keeps the old state and retries next tick.
        try:
            async with asyncio.timeout(_BOILER_CALL_TIMEOUT_S):
                await self.hass.services.async_call(
                    action.domain, action.service, dict(action.data), blocking=True
                )
            return True
        except Exception:
            _LOGGER.exception(
                "Poise boiler action failed/timed out: %s.%s",
                action.domain,
                action.service,
            )
            return False

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
        # Safety (review 2.3): never record the boiler OFF internally while it may
        # still be physically on. If the OFF call fails, keep the previous state so
        # the next tick re-issues OFF (the keep-alive also re-asserts it).
        if step.call == "off" and self._action_off is not None:
            if not await self._call(self._action_off):
                return
        elif step.call == "on" and self._action_on is not None:
            await self._call(self._action_on)
        self._boiler = step.state

    def _zone_name(self, zone_id: str) -> str:
        entry = self.hass.config_entries.async_get_entry(zone_id)
        return entry.title if entry is not None else zone_id

    def _update_frost_issues(self, excluded: tuple[str, ...]) -> None:
        """N-2 (ADR-0039 Korrektur #3): a freezing zone that does not control the
        boiler silently loses shared-boiler frost protection. Surface it as a
        repair issue so the config error is visible; cleared when none remain.
        """
        issue_id = "frost_zone_not_controlling_boiler"
        if excluded:
            self._active_issues.add(issue_id)
            ir.async_create_issue(  # idempotent; refreshes the zone list each tick
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="frost_zone_not_boiler",
                translation_placeholders={
                    "zones": ", ".join(self._zone_name(z) for z in excluded)
                },
            )
        elif issue_id in self._active_issues:
            self._active_issues.discard(issue_id)
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def _async_update_data(self) -> dict[str, Any]:
        now = self._clock.monotonic()
        requests = self._collect_requests()
        demand = aggregate_boiler_demand(
            requests,
            count_threshold=self._count_threshold,
            power_threshold=self._power_threshold,
        )
        self._update_frost_issues(demand.frost_excluded)
        if self._actuation:
            await self._actuate(demand.active, now)
        return {
            "boiler_demand": demand.active,
            "active_zones": demand.active_count,
            "weighted_demand": demand.weighted_demand,
            "frost_override": demand.frost_override,
            "frost_zone": demand.frost_zone_id,  # which zone forced frost (P1/2.1)
            "frost_excluded": list(demand.frost_excluded),  # N-2
            "zone_count": len(requests),
            "controlling_zones": sum(1 for r in requests if r.controls_boiler),
            "actuation_enabled": self._actuation,
            "boiler_on": self._boiler.on,
            **self._shared_resource_shadow(requests, now),
        }
