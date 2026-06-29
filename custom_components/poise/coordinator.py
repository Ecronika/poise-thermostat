"""Home Assistant coordinator — wires the pure pipeline to HA (ADR-0006/0013/0023).

Each tick reads the zone's entities, builds the capability-aware dual-setpoint
comfort decision (ADR-0023), applies the comfort schedule / night setback and
optimal-start preheat (ADR-0025), and writes exactly one capability-correct
command to the actuator (single writer). The EKF (ADR-0002/0024) learns in the
background and is persisted per room (ADR-0007). Live safety: window-open pause
and heating-failure notification (ADR-0012).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import actuator as actuator_mod
from .clock import MonotonicClock
from .comfort.dual_setpoint import decide as comfort_decide
from .comfort.en16798 import HEATING_LOWER, HEATING_UPPER, Category
from .comfort.mold import mold_min_air_temperature_detail
from .comfort.operative import operative_temperature
from .comfort.schedule import ComfortSchedule, ComfortWindow, parse_hhmm
from .comfort.virtual_mrt import virtual_mrt
from .const import (
    CONF_ACTUATOR,
    CONF_ANNUAL_KWH,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_COOL_MIN_OUTDOOR,
    CONF_ENTRY_TYPE,
    CONF_HEAT_MAX_OUTDOOR,
    CONF_HUMIDITY_SENSOR,
    CONF_IRRADIANCE,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_PRICE_EUR_KWH,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    DEFAULT_ANNUAL_KWH,
    DEFAULT_COMFORT_BASE,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_COOL_MIN_OUTDOOR_C,
    DEFAULT_HEAT_MAX_OUTDOOR_C,
    DEFAULT_PRICE_EUR_KWH,
    DEFAULT_SETBACK_DELTA,
    DEVICE_MAX_C,
    DOMAIN,
    EKF_SAVE_EVERY_TICKS,
    ENTRY_TYPE_SYSTEM,
    FORECAST_TTL_S,
    FROST_FLOOR_C,
    LOW_BATTERY_PCT,
    MIN_PLAUSIBLE_TAU_H,
    SENSOR_FREEZE_AFTER_S,
    TICK_INTERVAL_S,
    WRITE_DEADBAND_C,
)
from .contracts import ActuatorCommand, ActuatorPath
from .control.cover_shading import (
    predict_peak_operative,
    shading_target_position,
)
from .control.hdh_savings import HdhConfig, HdhSavings
from .control.mpc_shadow import evaluate_shadow
from .control.optimal_start import (
    forecast_samples_from_response,
    mean_forecast_outdoor,
    plan_preheat,
)
from .control.outcome_scoring import (
    OutcomeSession,
    OutcomeStats,
    observe_session,
)
from .control.override import (
    OverrideConfig,
    OverrideMode,
    manual_override_expired,
    mode_comfort_base,
)
from .control.pi import PiCompensator
from .control.pi_shadow import evaluate_pi_shadow
from .control.tick_resolve import (
    heat_drive_signal,
    needs_mode_nudge,
    resolve_write_target,
    sanitize_override,
    select_mrt,
    select_q_solar,
    select_t_rm,
    should_write,
    snap_to_step,
)
from .control.tpi_shadow import evaluate_tpi_shadow
from .control.window_auto import (
    WindowAutoConfig,
    WindowAutoState,
    adaptive_open_threshold,
    effective_window_open,
    step_window_auto,
)
from .devices.capability import classify_number_entity, climate_capability
from .devices.model_fixes import (
    is_external_sensor_select,
    is_low_battery,
    looks_like_external_temp_number,
    looks_like_fault_alarm,
    looks_like_internal_schedule,
    looks_like_valve_steps,
)
from .estimation.psychrometrics import dewpoint as psychro_dewpoint
from .estimation.running_mean import RunningMeanTracker
from .estimation.seasonless_rate import SeasonlessRate
from .estimation.thermal_ekf import ThermalEKF
from .ingestion import RawSample, ingest_temperature, parse_finite
from .multi import lifecycle as _lifecycle
from .multi.discovery import EntitySnapshot
from .multi.model import DeviceHealth, Direction
from .multi.resolvers import ThermalDemand
from .multi.shadow import evaluate_thermal_shadow
from .safety.heating_failure import (
    HeatingFailureDetector,
    actuator_running,
    failure_notification_action,
)
from .safety.sensor_watchdog import (
    frozen_safe_target,
    is_frozen,
    sensor_age_seconds,
    sensor_at_heat_source,
    should_learn,
    valve_stuck,
)
from .storage import PoiseStore

_LOGGER = logging.getLogger(__name__)
# Conservative outdoor default when neither a sensor nor the running mean is
# known — mirrors control.mpc_controller._FALLBACK_T_OUT_C (a cold-ish day keeps
# heating engaged rather than mild-locking it out).
_FALLBACK_OUTDOOR_C = 5.0
# Comfort mode -> thermal-arbitration direction (ADR-0046 P1 shadow). "idle" and
# any other value map to None (no thermal demand).
_THERMAL_DIR: dict[str, Direction] = {"heat": Direction.HEAT, "cool": Direction.COOL}

_INVALID = {"unknown", "unavailable", ""}


def _num(state: State | None) -> float | None:
    if state is None or state.state in _INVALID:
        return None
    return parse_finite(state.state)  # rejects NaN/Inf at the boundary (C1)


def _num_attr(state: State | None, key: str) -> float | None:
    """Read a numeric attribute (e.g. a climate setpoint) or None."""
    if state is None or state.state == "unavailable":
        return None
    return parse_finite(state.attributes.get(key))


class PoiseCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """One coordinator per room; capability-aware dual-setpoint each tick."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_S),
            # H-5: the snapshot carries a per-tick monotonic heartbeat ("mono_ts",
            # ADR-0038 hub staleness) that necessarily differs every tick, so the
            # data is never equal tick-to-tick -- always_update=False could never
            # skip and was a no-op. Be honest: every tick is a genuinely new state.
            # (Refresh storms from input churn are cut by the _on_change filter, H-1.)
            always_update=True,
        )
        self._clock = MonotonicClock()
        self._ekf = ThermalEKF()
        self._trm_tracker = RunningMeanTracker()
        self._seasonless = SeasonlessRate()
        # Sensorless open-window detection (shadow, ADR-0041): slope-based,
        # decoupled prev-sample so it observes regardless of heating.
        self._window_auto = WindowAutoState()
        self._window_auto_cfg = WindowAutoConfig()
        self._wa_prev_room: float | None = None
        self._wa_prev_mono: float | None = None
        self._window_bypass: bool = False  # ignore window reaction (ADR-0041 stage 2)
        self._wa_open_threshold: float = self._window_auto_cfg.open_threshold
        self._pi = PiCompensator()
        self._prev_room: float | None = None
        self._prev_room_mono: float | None = None
        self._last_target: float | None = None
        self._last_written_mode: str | None = None
        self._last_fed: float | None = None
        self._dirty = False  # override/enabled/mode changed -> persist next save
        self._store = PoiseStore(hass, entry.entry_id)
        self._failure = HeatingFailureDetector()
        self._last_mono: float | None = None
        self._last_u_h: float = 0.0
        self._last_q_solar: float = 0.0
        self._save_counter = 0
        self._failure_notified = False
        # Silver log-when-unavailable: log the loss/recovery of the room sensor
        # exactly once each, not every 60 s tick.
        self._unavailable_logged = False
        self._notif_id = f"poise_heating_failure_{entry.entry_id}"
        self._entry_id = entry.entry_id
        self._active_issues: set[str] = set()
        self._lock = asyncio.Lock()
        self._enabled = True
        self._override: float | None = None
        self._override_set_wall: float | None = None
        # ADR-0046 P2: per-device anti-short-cycle lifecycle (wall-clock, survives
        # restart). Shadow-only today — tracks the actuator's run-state + health to
        # report the min-off / health gate; actuates nothing until P3.
        self._multi_lifecycle = _lifecycle.DeviceLifecycle()
        self._preset: OverrideMode = OverrideMode.NONE
        self._override_cfg = OverrideConfig()
        # options override data for hot-applyable tuning (A10); structural
        # inputs (sensors/actuator) live only in data.
        data = {**entry.data, **entry.options}
        self.zone_name: str = data[CONF_NAME]
        self._temp: str = data[CONF_TEMP_SENSOR]
        self._actuator: str = data[CONF_ACTUATOR]
        self._trm: str | None = data.get(CONF_TRM_SENSOR)
        self._outdoor: str | None = data.get(CONF_OUTDOOR_SENSOR)
        self._humidity: str | None = data.get(CONF_HUMIDITY_SENSOR)
        self._mrt: str | None = data.get(CONF_MRT_SENSOR)
        self._window: str | None = data.get(CONF_WINDOW_SENSOR)
        self._category = Category(data.get(CONF_CATEGORY, "II"))
        self._comfort_base: float = float(
            data.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)
        )
        # ADR-0044 outcome scoring + ADR-0045 efficiency report (diagnostic only)
        self._outcome_stats = OutcomeStats()
        self._outcome_session = OutcomeSession()
        self._hdh = HdhSavings()
        self._hdh_cfg = HdhConfig(
            annual_kwh=float(data.get(CONF_ANNUAL_KWH, DEFAULT_ANNUAL_KWH)),
            price_eur_kwh=float(data.get(CONF_PRICE_EUR_KWH, DEFAULT_PRICE_EUR_KWH)),
        )
        self._climate_mode: str = data.get(CONF_CLIMATE_MODE, "auto")
        self._cool_min_outdoor: float = float(
            data.get(CONF_COOL_MIN_OUTDOOR, DEFAULT_COOL_MIN_OUTDOOR_C)
        )
        self._heat_max_outdoor: float = float(
            data.get(CONF_HEAT_MAX_OUTDOOR, DEFAULT_HEAT_MAX_OUTDOOR_C)
        )
        weight = float(data.get(CONF_COMFORT_WEIGHT, DEFAULT_COMFORT_WEIGHT))
        self._priority: float = weight / 100.0
        delta = float(data.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA))
        start = parse_hhmm(data.get(CONF_COMFORT_START))
        end = parse_hhmm(data.get(CONF_COMFORT_END))
        if start is not None and end is not None and delta > 0.0:
            self._schedule = ComfortSchedule.from_windows(
                [ComfortWindow(start, end)], delta
            )
        else:
            self._schedule = ComfortSchedule.always_comfort()
        self._optimal_start: bool = bool(data.get(CONF_OPTIMAL_START, True))
        # optimal-stop coasts to the lower comfort edge before window end; for
        # now coupled to optimal-start (predictive scheduling), splittable later.
        self._optimal_stop: bool = self._optimal_start
        self._weather: str | None = data.get(CONF_WEATHER)
        self._irradiance: str | None = data.get(CONF_IRRADIANCE)
        self._trv_ext_temp: str | None = data.get(CONF_TRV_EXTERNAL_TEMP)
        self._operative_input: bool = bool(data.get(CONF_OPERATIVE_INPUT, False))
        self._guards_resolved = False
        self._sched_entity: str | None = None
        self._fault_entity: str | None = None
        self._battery_entity: str | None = None
        self._ext_temp_auto: str | None = None
        self._sensor_select: str | None = None
        self._valve_entity: str | None = None
        self._valve_closing_steps: str | None = None
        self._valve_idle_steps: str | None = None
        self._forecast: list[tuple[float, float]] = []
        self._forecast_at: float | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value
        self._dirty = True

    def set_override(self, target: float | None) -> None:
        # Validate at the trust boundary: reject non-finite, clamp to the safe
        # envelope so a bad manual setpoint can never reach the actuator (C2).
        self._override = sanitize_override(target, FROST_FLOOR_C, DEVICE_MAX_C)
        self._override_set_wall = (
            dt_util.utcnow().timestamp() if self._override is not None else None
        )
        self._dirty = True

    def set_climate_mode(self, mode: str) -> None:
        self._climate_mode = mode
        self._dirty = True

    def set_window_bypass(self, on: bool) -> None:
        self._window_bypass = on
        self._dirty = True

    def set_preset(self, mode: OverrideMode) -> None:
        self._preset = mode
        self._dirty = True

    @property
    def preset(self) -> OverrideMode:
        return self._preset

    @property
    def window_bypass(self) -> bool:
        return self._window_bypass

    @property
    def capability(self) -> tuple[bool, bool]:
        """(can_heat, can_cool) of the actuator (review P2 cooling modes)."""
        return self._capability()

    @property
    def via_device_id(self) -> tuple[str, str] | None:
        """Device-registry link from this zone to the system hub (M9).

        Returns the hub device identifier when a system entry is configured, so
        zones nest under the Poise System device; ``None`` (no link) otherwise.
        """
        for e in self.hass.config_entries.async_entries(DOMAIN):
            if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM:
                return (DOMAIN, e.entry_id)
        return None

    @property
    def climate_mode(self) -> str:
        return self._climate_mode

    async def async_bootstrap(self) -> None:
        """Restore the learned EKF before the first control tick (ADR-0007)."""
        try:
            data = await self._store.load()
            if isinstance(data, dict) and "ekf" in data:
                self._ekf = ThermalEKF.from_dict(data["ekf"])
                if isinstance(data.get("trm"), dict):
                    self._trm_tracker = RunningMeanTracker.from_dict(data["trm"])
                if isinstance(data.get("seasonless"), dict):
                    self._seasonless = SeasonlessRate.from_dict(data["seasonless"])
                if isinstance(data.get("window_auto"), dict):
                    self._window_auto = WindowAutoState.from_dict(data["window_auto"])
                if isinstance(data.get("multi_lifecycle"), dict):
                    # ADR-0046 P2: restore the wall-clock lifecycle so a compressor
                    # min-off keeps counting across a restart (conservative on a
                    # skewed clock — a future stamp is clamped, never trusted long).
                    self._multi_lifecycle = _lifecycle.from_dict(
                        data["multi_lifecycle"], now=dt_util.utcnow().timestamp()
                    )
                if isinstance(data.get("outcome_stats"), dict):
                    self._outcome_stats = OutcomeStats.from_dict(data["outcome_stats"])
                if isinstance(data.get("hdh_savings"), dict):
                    self._hdh = HdhSavings.from_dict(data["hdh_savings"])
                self._window_bypass = bool(data.get("window_bypass", False))
                try:
                    self._preset = OverrideMode(data.get("preset", "none"))
                except ValueError:
                    self._preset = OverrideMode.NONE
                self._enabled = bool(data.get("enabled", True))
                ov = data.get("override")
                self._override = float(ov) if isinstance(ov, (int, float)) else None
                # C5: restore the *wall-clock* set-time so the 2 h auto-revert
                # measures real elapsed time and a hold cannot outlive a restart.
                osw = data.get("override_set_wall")
                self._override_set_wall = (
                    float(osw)
                    if self._override is not None and isinstance(osw, (int, float))
                    else None
                )
                cm = data.get("climate_mode")
                if isinstance(cm, str):
                    self._climate_mode = cm
            elif data is not None:
                self._ekf = ThermalEKF.from_dict(data)  # legacy: bare EKF dict
        except Exception:  # noqa: BLE001 - corrupt state must not block setup
            _LOGGER.exception("Poise: failed to restore learned model; starting fresh")
        # cold-start prior (ADR-0004): seed beta_h from the seasonless estimate
        # only while the EKF has never observed heating (e.g. new season); once it
        # learns from real heating it owns the parameter (never parallel, G6).
        if self._ekf.n_heating == 0 and self._seasonless.phase in (
            "learning",
            "mature",
        ):
            t_out = self._seasonless.mean_outdoor
            if t_out is not None:
                prior = self._seasonless.heat_rate_prior(
                    self._comfort_base, t_out, dt_util.now().toordinal()
                )
                if prior is not None:
                    self._ekf.seed_beta_h(prior)

    async def async_apply_options(self, entry: ConfigEntry) -> None:
        """Apply changed tuning options in place, without a reload (A10).

        Re-reads the volatile tuning fields (options over data) and updates the
        live state, so an options change does **not** discard the learned EKF
        transient that a full reload would. Structural inputs are not options.
        """
        data = {**entry.data, **entry.options}
        self._comfort_base = float(data.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE))
        self._hdh_cfg = HdhConfig(
            annual_kwh=float(data.get(CONF_ANNUAL_KWH, DEFAULT_ANNUAL_KWH)),
            price_eur_kwh=float(data.get(CONF_PRICE_EUR_KWH, DEFAULT_PRICE_EUR_KWH)),
        )
        self._category = Category(data.get(CONF_CATEGORY, "II"))
        self._climate_mode = data.get(CONF_CLIMATE_MODE, "auto")
        self._cool_min_outdoor = float(
            data.get(CONF_COOL_MIN_OUTDOOR, DEFAULT_COOL_MIN_OUTDOOR_C)
        )
        self._heat_max_outdoor = float(
            data.get(CONF_HEAT_MAX_OUTDOOR, DEFAULT_HEAT_MAX_OUTDOOR_C)
        )
        self._priority = (
            float(data.get(CONF_COMFORT_WEIGHT, DEFAULT_COMFORT_WEIGHT)) / 100.0
        )
        delta = float(data.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA))
        start = parse_hhmm(data.get(CONF_COMFORT_START))
        end = parse_hhmm(data.get(CONF_COMFORT_END))
        if start is not None and end is not None and delta > 0.0:
            self._schedule = ComfortSchedule.from_windows(
                [ComfortWindow(start, end)], delta
            )
        else:
            self._schedule = ComfortSchedule.always_comfort()
        self._optimal_start = bool(data.get(CONF_OPTIMAL_START, True))
        self._optimal_stop = self._optimal_start
        self._operative_input = bool(data.get(CONF_OPERATIVE_INPUT, False))
        await self.async_request_refresh()

    def attach_listeners(self, entry: ConfigEntry) -> None:
        """React promptly to input changes, not only on the 60 s tick (A6).

        Subscribes to the room sensor, the window sensor and the actuator; any
        change requests a refresh (coalesced by the coordinator's own debounce).
        The tick still owns learning/safety -- this only cuts *reaction* latency
        (notably an open window) from up to a tick to near-instant. Removed on
        unload via ``entry.async_on_unload``.
        """
        from homeassistant.core import Event
        from homeassistant.helpers.event import async_track_state_change_event

        watched = [e for e in (self._temp, self._window, self._actuator) if e]

        async def _on_change(event: Event) -> None:
            # H-1: skip pure attribute churn. A watched entity may emit many
            # state-change events per tick while the value Poise reacts to is
            # unchanged; refresh only on a real change (the state itself, or --
            # for the actuator -- its hvac_action attribute).
            new = event.data.get("new_state")
            if new is None:
                return
            old = event.data.get("old_state")
            if old is not None and old.state == new.state:
                old_action = old.attributes.get("hvac_action")
                new_action = new.attributes.get("hvac_action")
                is_actuator = event.data.get("entity_id") == self._actuator
                if not (is_actuator and old_action != new_action):
                    return
            await self.async_request_refresh()

        entry.async_on_unload(
            async_track_state_change_event(self.hass, watched, _on_change)
        )

    def _resolve_device_guards(self) -> None:
        """Find schedule/fault/battery entities on the actuator's device (once)."""
        if self._guards_resolved:
            return
        self._guards_resolved = True
        try:
            from homeassistant.helpers import entity_registry as er

            reg = er.async_get(self.hass)
            ent = reg.async_get(self._actuator)
            if ent is None or ent.device_id is None:
                return
            for e in er.async_entries_for_device(
                reg, ent.device_id, include_disabled_entities=False
            ):
                eid = e.entity_id
                if self._sched_entity is None and looks_like_internal_schedule(eid):
                    self._sched_entity = eid
                elif self._fault_entity is None and looks_like_fault_alarm(eid):
                    self._fault_entity = eid
                elif (
                    self._battery_entity is None
                    and eid.startswith("sensor.")
                    and e.original_device_class == "battery"
                ):
                    self._battery_entity = eid
                elif self._ext_temp_auto is None and looks_like_external_temp_number(
                    eid, e.original_device_class
                ):
                    self._ext_temp_auto = eid
                elif self._sensor_select is None and eid.startswith("select."):
                    sel = self.hass.states.get(eid)
                    if is_external_sensor_select(
                        eid, sel.attributes.get("options") if sel else None
                    ):
                        self._sensor_select = eid
                elif (
                    self._valve_entity is None
                    and eid.startswith("number.")
                    and classify_number_entity(eid) == "valve"
                ):
                    self._valve_entity = eid
                elif looks_like_valve_steps(eid) == "closing":
                    self._valve_closing_steps = eid
                elif looks_like_valve_steps(eid) == "idle":
                    self._valve_idle_steps = eid
        except Exception:  # noqa: BLE001 - guard resolution must never break setup
            _LOGGER.debug("Poise: device-guard resolution failed", exc_info=True)

    def _issue(
        self,
        issue_id: str,
        active: bool,
        *,
        translation_key: str,
        placeholders: dict[str, str] | None = None,
    ) -> None:
        """Raise/clear a Home Assistant repair issue on transitions (ADR-0012)."""
        if active and issue_id not in self._active_issues:
            self._active_issues.add(issue_id)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=translation_key,
                translation_placeholders=placeholders or {},
            )
        elif not active and issue_id in self._active_issues:
            self._active_issues.discard(issue_id)
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _read(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        return _num(self.hass.states.get(entity_id))

    def _sensor_age(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        # last_changed (the value-change time, per the watchdog contract): a
        # dead/stuck sensor that keeps re-publishing the SAME value still bumps
        # last_updated, so only last_changed detects "available but frozen".
        # "Sensor lost / unavailable" is handled separately by the ingestion
        # degradation ladder. Threshold is long (hours) so a legitimately stable
        # room never false-positives (best-of: VTherm/BT, review F1).
        return sensor_age_seconds(dt_util.utcnow(), state.last_changed)

    def _local_minute(self) -> int:
        now = dt_util.now()
        return int(now.hour * 60 + now.minute)

    def _window_open(self) -> bool:
        if not self._window:
            return False
        state = self.hass.states.get(self._window)
        return state is not None and state.state == "on"

    def _capability(self) -> tuple[bool, bool]:
        act = self.hass.states.get(self._actuator)
        modes = act.attributes.get("hvac_modes") if act else None
        if modes:
            return climate_capability([str(m) for m in modes])
        return True, False  # default: assume a heat-only TRV

    def _device_max(self) -> float:
        act = self.hass.states.get(self._actuator)
        if act is not None:
            mx = act.attributes.get("max_temp")
            if isinstance(mx, (int, float)):
                return float(mx)
        return DEVICE_MAX_C

    def _sun_elevation(self) -> float | None:
        sun = self.hass.states.get("sun.sun")
        if sun is None:
            return None
        elev = sun.attributes.get("elevation")
        return float(elev) if isinstance(elev, (int, float)) else None

    async def _forecast_outdoor(self, horizon_min: float, fallback: float) -> float:
        """Mean forecast outdoor temp over the preheat window (ADR-0025).

        Refreshes the cached hourly forecast at most every FORECAST_TTL_S. A
        missing weather entity or any failure degrades to ``fallback`` (the
        constant current outdoor), so optimal-start never depends on a forecast.
        """
        if not self._weather:
            return fallback
        now = self._clock.monotonic()
        if self._forecast_at is None or (now - self._forecast_at) >= FORECAST_TTL_S:
            try:
                resp = await self.hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"type": "hourly", "entity_id": self._weather},
                    blocking=True,
                    return_response=True,
                )
                self._forecast = forecast_samples_from_response(
                    resp, self._weather, dt_util.utcnow()
                )
                self._forecast_at = now
            except Exception:  # noqa: BLE001 - forecast must never break the tick
                _LOGGER.debug("Poise: weather forecast unavailable; constant outdoor")
                return fallback
        return mean_forecast_outdoor(self._forecast, horizon_min, fallback)

    def _learn(self, room: float, t_out: float) -> None:
        """Passive EKF observer; paused on open window (ADR-0002/0024)."""
        now = self._clock.monotonic()
        try:
            if self._last_mono is not None:
                dt_h = (now - self._last_mono) / 3600.0
                if 0.0 < dt_h < 1.0:
                    self._ekf.predict(
                        dt_h,
                        t_out=t_out,
                        u_h=self._last_u_h,
                        q_solar=self._last_q_solar,
                    )
                    self._ekf.update(room)
        except Exception:  # noqa: BLE001 - learning must never break control
            _LOGGER.exception("Poise: EKF observer step failed")
        finally:
            self._last_mono = now

    def _observe_window_auto(self, room: float, t_out: float) -> None:
        """Feed the sensorless slope detector (ADR-0041).

        Skipped when a window sensor exists (measured > estimated, ADR-0012).
        Observes every tick — a window can open whether or not we heat. The open
        threshold is adapted to the learned tau once the model is identified
        (steeper natural cooling -> higher threshold), else the fixed default.
        """
        if self._window is not None:
            return
        now = self._clock.monotonic()
        cfg = self._window_auto_cfg
        if self._ekf.identified:
            self._wa_open_threshold = adaptive_open_threshold(
                self._ekf.tau_hours, room, t_out, cfg
            )
            cfg = replace(cfg, open_threshold=self._wa_open_threshold)
        else:
            self._wa_open_threshold = cfg.open_threshold
        if self._wa_prev_room is not None and self._wa_prev_mono is not None:
            dt_h = (now - self._wa_prev_mono) / 3600.0
            if 0.0 < dt_h < 1.0:
                slope = (room - self._wa_prev_room) / dt_h
                self._window_auto = step_window_auto(
                    self._window_auto, slope, dt_h * 60.0, cfg
                )
        self._wa_prev_room = room
        self._wa_prev_mono = now

    def _observe_seasonless(self, room: float, t_out: float) -> None:
        """Record a normalised heat-up rate while heating (shadow, ADR-0004/0026)."""
        now = self._clock.monotonic()
        if (
            self._prev_room is not None
            and self._prev_room_mono is not None
            and self._last_target is not None
            and self._last_u_h > 0.5  # heating drove the just-elapsed interval
        ):
            dt_h = (now - self._prev_room_mono) / 3600.0
            if 0.0 < dt_h < 1.0:
                rate = (room - self._prev_room) / dt_h
                if rate > 0.0:
                    self._seasonless.observe(
                        rate, self._last_target, t_out, dt_util.now().toordinal()
                    )
        self._prev_room = room
        self._prev_room_mono = now

    async def _notify_failure(self, failed: bool) -> None:
        action = failure_notification_action(failed, self._failure_notified)
        if action == "create":
            self._failure_notified = True
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": f"Poise: heating failure — {self.zone_name}",
                    "message": (
                        f"{self.zone_name} is not warming up despite a heating "
                        "demand. Check the valve, radiator or boiler."
                    ),
                    "notification_id": self._notif_id,
                },
                blocking=False,
            )
        elif action == "dismiss":
            self._failure_notified = False
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": self._notif_id},
                blocking=False,
            )

    def _save_payload(self) -> dict[str, Any]:
        return {
            "ekf": self._ekf.to_dict(),
            "trm": self._trm_tracker.to_dict(),
            "seasonless": self._seasonless.to_dict(),
            "window_auto": self._window_auto.to_dict(),
            "multi_lifecycle": _lifecycle.to_dict(self._multi_lifecycle),
            "outcome_stats": self._outcome_stats.to_dict(),
            "hdh_savings": self._hdh.to_dict(),
            "window_bypass": self._window_bypass,
            "preset": self._preset.value,
            "enabled": self._enabled,
            "override": self._override,
            "override_set_wall": self._override_set_wall,
            "climate_mode": self._climate_mode,
        }

    async def _maybe_save(self) -> None:
        self._save_counter += 1
        if self._save_counter >= EKF_SAVE_EVERY_TICKS or self._dirty:
            self._save_counter = 0
            self._dirty = False
            try:
                await self._store.save(self._save_payload())
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: failed to persist learned model")

    async def async_persist_and_cleanup(self) -> None:
        """Final save + repair-issue/notification cleanup on unload (review P1.3)."""
        try:
            await self._store.save(self._save_payload())
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Poise: final save on unload failed")
        for issue_id in list(self._active_issues):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._active_issues.clear()
        if self._failure_notified:
            self._failure_notified = False
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "dismiss",
                    {"notification_id": self._notif_id},
                    blocking=False,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: notification dismiss on unload failed")

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            return await self._run_once()

    def _emit_health_issues(self) -> tuple[bool, bool, bool, bool]:
        """Raise/clear device-health repair issues; return the status flags."""
        self._issue(
            f"actuator_unavailable_{self._entry_id}",
            self.hass.states.get(self._actuator) is None,
            translation_key="actuator_unavailable",
            placeholders={"entity": self._actuator},
        )
        frozen = is_frozen(self._sensor_age(self._temp), SENSOR_FREEZE_AFTER_S)
        self._issue(
            f"sensor_frozen_{self._entry_id}",
            frozen,
            translation_key="sensor_frozen",
            placeholders={"entity": self._temp},
        )
        self._resolve_device_guards()
        sched_active = fault_active = False
        if self._sched_entity:
            st = self.hass.states.get(self._sched_entity)
            sched_active = st is not None and st.state == "on"
            self._issue(
                f"device_schedule_{self._entry_id}",
                sched_active,
                translation_key="device_schedule",
                placeholders={"entity": self._sched_entity},
            )
        if self._fault_entity:
            st = self.hass.states.get(self._fault_entity)
            fault_active = st is not None and st.state == "on"
            self._issue(
                f"device_alarm_{self._entry_id}",
                fault_active,
                translation_key="device_alarm",
                placeholders={"entity": self._fault_entity},
            )
        if self._battery_entity:
            self._issue(
                f"low_battery_{self._entry_id}",
                is_low_battery(self._read(self._battery_entity), LOW_BATTERY_PCT),
                translation_key="low_battery",
                placeholders={"entity": self._battery_entity},
            )
        heat_source_suspect = sensor_at_heat_source(
            self._ekf.tau_hours,
            self._ekf.identified,
            min_plausible_tau_h=MIN_PLAUSIBLE_TAU_H,
        )
        self._issue(
            f"sensor_at_heat_source_{self._entry_id}",
            heat_source_suspect,
            translation_key="sensor_at_heat_source",
            placeholders={"entity": self._temp},
        )
        return frozen, sched_active, fault_active, heat_source_suspect

    async def _run_once(self) -> dict[str, Any]:
        air = self._read(self._temp)
        self._issue(
            f"sensor_unavailable_{self._entry_id}",
            air is None,
            translation_key="sensor_unavailable",
            placeholders={"entity": self._temp},
        )
        if air is None:
            if not self._unavailable_logged:
                _LOGGER.warning(
                    "Poise %s: room temperature sensor %s is unavailable; "
                    "holding the entity in its last state until it returns",
                    self.zone_name,
                    self._temp,
                )
                self._unavailable_logged = True
            return {"available": False}
        if self._unavailable_logged:
            _LOGGER.info(
                "Poise %s: room temperature sensor %s is back; resuming control",
                self.zone_name,
                self._temp,
            )
            self._unavailable_logged = False
        frozen, sched_active, fault_active, heat_source_suspect = (
            self._emit_health_issues()
        )
        now = self._clock.monotonic()
        reading = ingest_temperature([RawSample(air, now)], now=now)
        room = reading.value
        t_out = self._read(self._outdoor)
        # internal EN 16798-1 running mean, used when no external T_rm sensor.
        if t_out is not None:
            self._trm_tracker.observe(t_out, dt_util.now().toordinal())
        t_rm, t_rm_source = select_t_rm(
            self._read(self._trm), self._trm_tracker.current, t_out
        )
        t_out_eff = (
            t_out
            if t_out is not None
            else (t_rm if t_rm is not None else _FALLBACK_OUTDOOR_C)
        )
        t_rm_eff = t_rm if t_rm is not None else t_out_eff
        rh = self._read(self._humidity)
        # solar disturbance q_solar (normalised, ADR-0010): internal clear-sky
        # estimate always runs; a measured irradiance sensor overrides the value
        # used (shadow-estimator principle, ADR-0026).
        q_solar, q_solar_source, q_solar_internal = select_q_solar(
            self._sun_elevation(), self._read(self._irradiance)
        )
        # virtual MRT (shadow, ADR-0017/0026): exterior envelope pulls MRT toward
        # outdoor + a solar radiant bump; a measured globe/MRT sensor overrides.
        mrt_internal = virtual_mrt(room, t_out_eff, q_solar)
        t_mrt, mrt_source = select_mrt(self._read(self._mrt), mrt_internal)
        if (
            self._override is not None
            and self._override_set_wall is not None
            and manual_override_expired(
                self._override_set_wall,
                dt_util.utcnow().timestamp(),
                self._override_cfg,
            )
        ):
            self._override = None
            self._override_set_wall = None
            self._dirty = True
        sensor_window_open = self._window_open()
        window_open = effective_window_open(
            sensor_open=sensor_window_open,
            auto_open=self._window_auto.open,
            bypass=self._window_bypass,
        )
        can_heat, can_cool = self._capability()
        device_max = self._device_max()

        if should_learn(window_open=window_open, frozen=frozen):
            self._learn(room, t_out_eff)
        self._observe_seasonless(room, t_out_eff)
        self._observe_window_auto(room, t_out_eff)

        # mould floor + dewpoint cap from humidity
        mold_min = None
        mold_capped = False
        dewpoint = None
        if rh is not None:
            dewpoint = psychro_dewpoint(room, rh)
            # C8: keep a (conservative) mould floor even without an outdoor sensor
            # by using the effective outdoor proxy instead of skipping it.
            # F15: surface when the required floor is clipped at 24 °C -- the room
            # really needs dehumidification there, so protection is insufficient.
            mold_min, mold_capped = mold_min_air_temperature_detail(t_out_eff, rh, room)

        # schedule: night setback + optimal-start preheat (ADR-0025).
        # Resolve the forecast outdoor (I/O) here, then let the pure planner
        # decide the effective base — the decision is unit-tested without HA.
        sched = self._schedule.state_at(self._local_minute())
        # A model is needed for the predictive plan in BOTH phases: preheat during
        # setback (lead = minutes to comfort) and coast/optimal-stop during comfort
        # (lead = minutes to setback). H2: build it whenever the EKF is identified
        # and either feature is enabled — it was previously built only during
        # setback, which left the comfort-phase coast (optimal-stop) branch dead.
        predictive = (
            can_heat
            and self._ekf.identified
            and (self._optimal_start or self._optimal_stop)
        )
        if predictive:
            lead_minutes = (
                sched.minutes_to_setback
                if sched.is_comfort
                else sched.minutes_to_comfort
            )
            t_out_lead = await self._forecast_outdoor(float(lead_minutes), t_out_eff)
            model = self._ekf.get_model()
        else:
            t_out_lead, model = t_out_eff, None
        lo, hi = HEATING_LOWER[self._category], HEATING_UPPER[self._category]
        plan = plan_preheat(
            comfort_base=mode_comfort_base(
                self._preset, self._comfort_base, self._override_cfg
            ),
            is_comfort=sched.is_comfort,
            setback_offset=sched.setback_offset,
            minutes_to_comfort=float(sched.minutes_to_comfort),
            optimal_start_enabled=self._optimal_start,
            can_heat=can_heat,
            identified=self._ekf.identified,
            model=model,
            room=room,
            t_out_lead=t_out_lead,
            heat_lower=lo,
            heat_upper=hi,
            optimal_stop_enabled=self._optimal_stop,
            minutes_to_setback=float(sched.minutes_to_setback),
            coast_lower=lo,
        )
        base = plan.base
        preheating = plan.preheating
        preheat_outdoor = plan.preheat_outdoor
        coasting = plan.coasting

        # operative TRV-input mode (ADR-0029): write the operative target and feed
        # the operative temperature, IF the thermostat can be calibrated to an
        # external sensor (i.e. a valid external-temperature input). Otherwise fall
        # back to air-side control and flag a repair issue (fault tolerance).
        # external-temp input: explicit config, else auto-detected on the device
        # (pavax-verified). The number is write-only, so a "unknown" state is fine;
        # only "unavailable" means the device is offline (ADR-0029).
        ext_num = self._trv_ext_temp or (
            self._ext_temp_auto if self._operative_input else None
        )
        ext_state = self.hass.states.get(ext_num) if ext_num else None
        ext_ok = ext_state is not None and ext_state.state != "unavailable"
        operative_active = self._operative_input and ext_ok
        self._issue(
            f"operative_unsupported_{self._entry_id}",
            self._operative_input and not ext_ok,
            translation_key="operative_unsupported",
            placeholders={"entity": ext_num or "—"},
        )
        if operative_active:
            room_decide = operative_temperature(room, t_mrt)
            t_mrt_decide: float | None = None  # MRT lives in the fed/written values
        else:
            room_decide = room
            t_mrt_decide = t_mrt
        decision = comfort_decide(
            t_rm=t_rm_eff,
            room=room_decide,
            category=self._category,
            comfort_base=base,
            can_heat=can_heat,
            can_cool=can_cool,
            climate_mode=self._climate_mode,
            cool_min_outdoor=self._cool_min_outdoor,
            heat_max_outdoor=self._heat_max_outdoor,
            t_out=t_out_eff,
            t_mrt=t_mrt_decide,
            frost_floor=FROST_FLOOR_C,
            mold_min=mold_min,
            dewpoint=dewpoint,
            priority=self._priority,
        )

        wt = resolve_write_target(
            window_open=window_open,
            override=self._override,
            heat_sp=decision.heat_sp,
            cool_sp=decision.cool_sp,
            write_setpoint=decision.write_setpoint,
            comfort_mode=decision.mode,
            frost_floor=FROST_FLOOR_C,
            mold_min=mold_min,
            device_max=device_max,
        )
        target, mode, norm_binding = wt.target, wt.mode, wt.norm_binding
        binding_precedence = wt.binding_precedence
        if frozen:
            # C3/Ü3: the room sensor is stale -> do not chase a comfort target on
            # a dead value; degrade to the health floor and let the actuator hold
            # it with its own sensor (fail toward warmth).
            target = frozen_safe_target(FROST_FLOOR_C, mold_min)
            mode = "heat"
            self._last_target = target
        act_state = self.hass.states.get(self._actuator)
        heating = self._enabled and not window_open and mode == "heat"
        # A1: the EKF heating-drive uses the actuator's *real* running state when
        # reported (TRVZB running_state -> hvac_action), else our heat intent.
        self._last_u_h = heat_drive_signal(
            act_state.attributes.get("hvac_action") if act_state else None,
            fallback_heating=heating,
        )
        self._last_q_solar = q_solar
        self._last_target = target

        # C6: the failure detector keys on the actuator's real running state
        # (hvac_action) when reported, not just our heat intent.
        running = actuator_running(
            act_state.attributes.get("hvac_action") if act_state else None,
            fallback=heating,
        )
        failed = (
            self._failure.update(
                now_h=now / 3600.0,
                room=room,
                setpoint=target,
                running=running,
            )
            or fault_active
        )
        await self._notify_failure(failed)

        if self._enabled:
            # H1/A2: keep a controllable actuator in the mode that matches our
            # write — cool when we cool, heat otherwise — so it follows our
            # setpoint instead of its own off/auto schedule (TRVZB system_mode).
            desired_hvac = "cool" if mode == "cool" else "heat"
            act_modes = (
                (act_state.attributes.get("hvac_modes") or []) if act_state else []
            )
            if needs_mode_nudge(
                act_state.state if act_state else None,
                desired_hvac,
                supported=desired_hvac in act_modes,
            ):
                try:
                    await self.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {"entity_id": self._actuator, "hvac_mode": desired_hvac},
                        blocking=False,
                    )
                except Exception:  # noqa: BLE001 - mode nudge is best-effort
                    _LOGGER.exception(
                        "Poise: set_hvac_mode(%s) failed for %s",
                        desired_hvac,
                        self._actuator,
                    )
            # Compare to the actuator's *actual* setpoint, not our last command, so
            # we re-assert when something external (e.g. an "off"/away automation)
            # changed it, while still skipping writes when it already matches
            # (review P1.2; live-test finding 2026-06-21).
            actual_sp = _num_attr(act_state, "temperature")
            # snap our target to the device's setpoint step so a coarse TRV's
            # rounded echo doesn't trigger a write every tick (review R2)
            step = _num_attr(act_state, "target_temperature_step") or 0.1
            mode_changed = mode != self._last_written_mode
            if should_write(
                actual_sp,
                snap_to_step(target, step),
                mode_changed=mode_changed,
                deadband=WRITE_DEADBAND_C,
            ):
                cmd = ActuatorCommand(
                    actuator_id=self._actuator,
                    path=ActuatorPath.SETPOINT,
                    value=target,
                    hvac_mode=mode,
                    reason="tick",
                )
                try:
                    await actuator_mod.write(self.hass, cmd)
                    self._last_written_mode = mode
                except Exception:  # noqa: BLE001 - never let actuator I/O kill the tick
                    _LOGGER.exception(
                        "Poise: actuator write failed for %s", self._actuator
                    )
            # feed the true room temperature to a TRV external-temperature input
            # (ADR-0029): the thermostat then modulates against the real sensor.
            if ext_num and ext_ok:
                # ensure the TRV uses its external sensor (pavax-verified); on the
                # tick we switch it, skip the write so the device can settle.
                switched = False
                if self._sensor_select:
                    sel = self.hass.states.get(self._sensor_select)
                    if sel is not None and sel.state not in ("external", "unavailable"):
                        try:
                            await self.hass.services.async_call(
                                "select",
                                "select_option",
                                {
                                    "entity_id": self._sensor_select,
                                    "option": "external",
                                },
                                blocking=False,
                            )
                            switched = True
                        except Exception:  # noqa: BLE001
                            _LOGGER.exception("Poise: sensor-select switch failed")
                if not switched:
                    fed = round(
                        operative_temperature(room, t_mrt)
                        if operative_active
                        else room,
                        1,
                    )
                    if should_write(
                        self._last_fed, fed, mode_changed=False, deadband=0.1
                    ):
                        try:
                            await self.hass.services.async_call(
                                "number",
                                "set_value",
                                {"entity_id": ext_num, "value": fed},
                                blocking=False,
                            )
                            self._last_fed = fed
                        except Exception:  # noqa: BLE001 - feed is best-effort
                            _LOGGER.exception(
                                "Poise: external-temp write failed for %s", ext_num
                            )

        await self._maybe_save()

        operative = operative_temperature(room, t_mrt)
        # Predictive solar-shading shadow (ADR-0043): forecast the peak operative
        # temperature (Tier-2 linear while the EKF is not identified, e.g. summer)
        # and what a cover *would* do — diagnostic only, no cover is moved yet.
        # --- Diagnostics-only shadows (review P2/R-4) -----------------------
        # The setpoint is already written above. A failure in any predictive
        # shadow (e.g. a degenerate value from a not-yet-identified EKF) must
        # NEVER take control reporting offline — so the whole block is guarded and
        # degrades to neutral diagnostics while the written setpoint stands.
        binding = "en16798"
        _cover_peak = operative
        _cover_pos = 0.0
        _cover_reason = ""
        shadow_objs: dict[str, Any] = {
            "pi_active": False,
            "pi_setpoint": None,
            "pi_offset": None,
            "multi_active_source": None,
            "multi_reason": "shadow_error",
            "multi_severity": "info",
            "multi_blocked": [],
            "multi_min_off_remaining": 0,
            "multi_device_health": self._multi_lifecycle.health,
            "tpi_active": False,
            "tpi_duty": None,
            "tpi_valve_percent": None,
            "mpc_active": False,
            "mpc_power": None,
            "mpc_weight": None,
            "mpc_setpoint": None,
            "mpc_regime": "hold",
        }
        try:
            _cm = self._ekf.get_model()
            _cover_peak = predict_peak_operative(
                operative,
                t_out_eff,
                [q_solar] * 36,
                alpha=_cm.alpha,
                beta_s=_cm.beta_s,
                dt_h=5.0 / 60.0,
                confident=self._ekf.identified and self._ekf.temperature_std < 0.5,
            )
            _cover_pos, _cover_reason = shading_target_position(
                peak=_cover_peak,
                t_upper=decision.cool_sp,
                current_position=0.0,
                oriented_q=q_solar,
            )
            binding = "mold" if mold_min and mold_min >= decision.heat_sp else "en16798"
            # shadow MPC (ADR-0033): what the predictive controller *would* command
            # against the live EKF state; reported only, dormant until identified.
            shadow = evaluate_shadow(
                identified=self._ekf.identified,
                t_air=room,
                t_out=t_out_eff,
                t_rm=t_rm_eff,
                tau_hours=self._ekf.tau_hours,
                model=self._ekf.get_model(),
                prediction_std=self._ekf.temperature_std,
                confidence=self._ekf.confidence,
                target=decision.heat_sp,
                lower=decision.heat_sp,
                upper=decision.cool_sp,
            )
            # shadow direct-valve TPI duty (ADR-0036): computed + reported only.
            tpi = evaluate_tpi_shadow(
                valve_available=self._valve_entity is not None,
                model=self._ekf.get_model(),
                target=decision.heat_sp,
                room=room,
                t_out=t_out_eff,
            )
            # PI-compensated setpoint shadow (ADR-0037): setpoint-only devices.
            pi = evaluate_pi_shadow(
                self._pi,
                applies=self._valve_entity is None,
                target=decision.heat_sp,
                room=room,
                external=t_out_eff,  # real outdoor temp (review F-1: external==room
                dt_h=TICK_INTERVAL_S / 3600.0,  # killed the k_ext feed-forward term)
            )
            # F-1: the shadow is pure now — advance the persisted integrator here,
            # exactly once per tick, instead of as a hidden side effect of the read.
            if pi.next_acc is not None:
                self._pi.acc = pi.next_acc
            # Phase-1/2 thermal-arbitration shadow (ADR-0046): transient ZoneDevice.
            _act_modes = (
                (act_state.attributes.get("hvac_modes") or []) if act_state else []
            )
            _act_avail = act_state is not None and act_state.state not in (
                "unavailable",
                "unknown",
            )
            # P2: fold the actuator's run-state into the per-device lifecycle on a
            # wall-clock basis, then derive the resolver's min-off / health gate.
            _now_wall = dt_util.utcnow().timestamp()
            _act_action = act_state.attributes.get("hvac_action") if act_state else None
            self._multi_lifecycle = _lifecycle.observe(
                self._multi_lifecycle,
                conditioning=_act_action in ("heating", "cooling"),
                mode=act_state.state if (act_state and _act_avail) else None,
                now=_now_wall,
                health=(
                    DeviceHealth.OK.value
                    if _act_avail
                    else DeviceHealth.UNAVAILABLE.value
                ),
            )
            _multi_policy = _lifecycle.LifecyclePolicy()
            _multi_runtime = _lifecycle.to_runtime(
                self._multi_lifecycle, _now_wall, _multi_policy
            )
            multi_shadow = evaluate_thermal_shadow(
                EntitySnapshot(
                    entity_id=self._actuator,
                    domain="climate",
                    hvac_modes=tuple(str(m) for m in _act_modes),
                    available=_act_avail,
                ),
                ThermalDemand(_THERMAL_DIR.get(decision.mode), decision.target),
                runtime=_multi_runtime,
            )
            shadow_objs = {
                "pi_active": pi.active,
                "pi_setpoint": pi.setpoint,
                "pi_offset": pi.offset,
                "multi_active_source": multi_shadow.active_source,
                "multi_reason": multi_shadow.reason,
                "multi_severity": multi_shadow.severity,
                "multi_blocked": list(multi_shadow.blocked),
                "multi_min_off_remaining": round(
                    _lifecycle.min_off_remaining(
                        self._multi_lifecycle, _now_wall, _multi_policy
                    )
                ),
                "multi_device_health": self._multi_lifecycle.health,
                "tpi_active": tpi.active,
                "tpi_duty": tpi.duty,
                "tpi_valve_percent": tpi.valve_percent,
                "mpc_active": shadow.active,
                "mpc_power": shadow.power,
                "mpc_weight": shadow.weight,
                "mpc_setpoint": shadow.setpoint,
                "mpc_regime": shadow.regime,
            }
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            _LOGGER.exception(
                "Poise: shadow evaluation failed; the written setpoint stands, "
                "diagnostics degraded this tick"
            )
        # valve health (A3): a near-zero closing-step count means the motorised
        # valve failed calibration / is jammed — advisory diagnostic + repair issue.
        closing_steps = self._read(self._valve_closing_steps)
        idle_steps = self._read(self._valve_idle_steps)
        v_stuck = valve_stuck(closing_steps)
        valve_health = (
            "stuck" if v_stuck else ("ok" if closing_steps is not None else "unknown")
        )
        self._issue(
            f"valve_stuck_{self._entry_id}",
            v_stuck,
            translation_key="valve_stuck",
            placeholders={"entity": self._valve_closing_steps or "—"},
        )
        # ADR-0044 outcome scoring + ADR-0045 efficiency report (diagnostic only;
        # never raises — a scoring slip must not break the control tick).
        outcome_diag: dict[str, Any] = {
            "outcome_last_score": None,
            "outcome_ts_avg": None,
            "outcome_obs_avg": None,
            "outcome_n": 0,
            "savings_kwh_month": 0.0,
            "savings_eur_month": 0.0,
            "savings_pct": 0.0,
        }
        try:
            _tick_min = TICK_INTERVAL_S / 60.0
            self._hdh = self._hdh.observe(
                comfort=self._comfort_base,
                setpoint=decision.heat_sp,
                outdoor=t_out_eff,
                dt_min=_tick_min,
                now_month=dt_util.now().month,
                cfg=self._hdh_cfg,
            )
            self._outcome_session, _fin = observe_session(
                self._outcome_session,
                temp=room,
                target=decision.heat_sp,
                heating=heating,
                controlling=self._enabled,
                dt_min=_tick_min,
                expected_minutes=float(sched.minutes_to_comfort),
                q_solar=q_solar,
                outdoor=t_out_eff,
            )
            if _fin is not None:
                self._outcome_stats = self._outcome_stats.observe(
                    _fin.score, _fin.controller
                )
            _rep = self._hdh.report(self._hdh_cfg)
            outcome_diag = {
                "outcome_last_score": self._outcome_stats.last_score,
                "outcome_ts_avg": self._outcome_stats.ts_avg,
                "outcome_obs_avg": self._outcome_stats.obs_avg,
                "outcome_n": self._outcome_stats.ts_n + self._outcome_stats.obs_n,
                "savings_kwh_month": _rep["kwh"],
                "savings_eur_month": _rep["eur"],
                "savings_pct": _rep["pct"],
            }
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            _LOGGER.debug("Poise outcome/savings diagnostics failed", exc_info=True)
        return {
            "available": True,
            **outcome_diag,
            # H3/ADR-0038: monotonic stamp of when this snapshot was produced, so
            # the system hub can detect a silently stale zone (age-based staleness).
            "mono_ts": now,
            "current_temperature": round(room, 1),
            "target_temperature": target,
            "operative_temperature": round(operative, 1),
            "t_rm": round(t_rm_eff, 1),
            "t_rm_source": t_rm_source,
            "t_rm_internal": (
                round(self._trm_tracker.current, 1)
                if self._trm_tracker.current is not None
                else None
            ),
            "q_solar": round(q_solar, 3),
            "q_solar_source": q_solar_source,
            "q_solar_internal": round(q_solar_internal, 3),
            "beta_s": round(self._ekf.get_model().beta_s, 3),
            "mrt": round(t_mrt, 1),
            "mrt_source": mrt_source,
            "mrt_internal": round(mrt_internal, 1),
            "heat_sp": decision.heat_sp,
            "cool_sp": decision.cool_sp,
            "mode": mode,
            "comfort_low": decision.heat_sp,
            "comfort_high": decision.cool_sp,
            "binding_lower_cause": binding,
            "category": self._category.value,
            "heating": heating,
            "window_open": window_open,
            "window_auto_detected": self._window_auto.open,
            "window_auto_threshold": round(self._wa_open_threshold, 1),
            "window_bypass": self._window_bypass,
            "preset": self._preset.value,
            "override_active": self._override is not None,
            "cover_predicted_peak": round(_cover_peak, 1),
            "cover_would_shade": _cover_pos > 0,
            "cover_shade_position": _cover_pos,
            "cover_shade_reason": _cover_reason,
            "window_auto_slope": self._window_auto.ema_slope,
            "heating_failure": failed,
            "mold_capped": mold_capped,  # F15: mould floor clipped at 24 °C
            "source": reading.source.value,
            "tau_hours": round(self._ekf.tau_hours, 1),
            "confidence": round(self._ekf.confidence, 2),
            "identified": self._ekf.identified,
            "learning_phase": self._ekf.learning_phase,
            "identification_progress": round(self._ekf.data_factor, 2),
            "schedule_state": "comfort" if sched.is_comfort else "setback",
            "minutes_to_comfort": sched.minutes_to_comfort,
            "preheating": preheating,
            "preheat_outdoor": preheat_outdoor,
            "coasting": coasting,
            "minutes_to_setback": sched.minutes_to_setback,
            "sensor_frozen": frozen,
            "norm_binding": norm_binding,
            "binding_precedence": binding_precedence,
            "device_schedule_active": sched_active,
            "device_alarm": fault_active,
            "sensor_placement_suspect": heat_source_suspect,
            "trv_input_mode": (
                "operative" if operative_active else ("air" if ext_num else "none")
            ),
            "valve_health": valve_health,
            "valve_closing_steps": closing_steps,
            "valve_idle_steps": idle_steps,
            **shadow_objs,
            "tpi_valve_entity": self._valve_entity,
            "seasonless_phase": self._seasonless.phase,
            "seasonless_rate": (
                round(p, 3)
                if (
                    p := self._seasonless.heat_rate_prior(
                        decision.heat_sp, t_out_eff, dt_util.now().toordinal()
                    )
                )
                is not None
                else None
            ),
        }
