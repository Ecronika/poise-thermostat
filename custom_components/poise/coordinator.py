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
from .comfort.mold import mold_min_air_temperature
from .comfort.operative import operative_temperature
from .comfort.schedule import ComfortSchedule, ComfortWindow, parse_hhmm
from .comfort.virtual_mrt import virtual_mrt
from .const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_HUMIDITY_SENSOR,
    CONF_IRRADIANCE,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    DEFAULT_COMFORT_BASE,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_SETBACK_DELTA,
    DEVICE_MAX_C,
    DOMAIN,
    EKF_SAVE_EVERY_TICKS,
    FORECAST_TTL_S,
    FROST_FLOOR_C,
    LOW_BATTERY_PCT,
    MIN_PLAUSIBLE_TAU_H,
    SENSOR_FREEZE_AFTER_S,
    TICK_INTERVAL_S,
)
from .contracts import ActuatorCommand, ActuatorPath
from .control.optimal_start import (
    forecast_samples_from_response,
    mean_forecast_outdoor,
    plan_preheat,
)
from .control.tick_resolve import (
    resolve_write_target,
    select_mrt,
    select_q_solar,
    select_t_rm,
)
from .devices.capability import climate_capability
from .devices.model_fixes import (
    is_external_sensor_select,
    is_low_battery,
    looks_like_external_temp_number,
    looks_like_fault_alarm,
    looks_like_internal_schedule,
)
from .estimation.psychrometrics import dewpoint as psychro_dewpoint
from .estimation.running_mean import RunningMeanTracker
from .estimation.seasonless_rate import SeasonlessRate
from .estimation.thermal_ekf import ThermalEKF
from .ingestion import RawSample, ingest_temperature
from .safety.heating_failure import HeatingFailureDetector
from .safety.sensor_watchdog import is_frozen, sensor_at_heat_source
from .storage import PoiseStore

_LOGGER = logging.getLogger(__name__)

_INVALID = {"unknown", "unavailable", ""}


def _num(state: State | None) -> float | None:
    if state is None or state.state in _INVALID:
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


class PoiseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One coordinator per room; capability-aware dual-setpoint each tick."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_S),
        )
        self._clock = MonotonicClock()
        self._ekf = ThermalEKF()
        self._trm_tracker = RunningMeanTracker()
        self._seasonless = SeasonlessRate()
        self._prev_room: float | None = None
        self._prev_room_mono: float | None = None
        self._last_target: float | None = None
        self._store = PoiseStore(hass, entry.entry_id)
        self._failure = HeatingFailureDetector()
        self._last_mono: float | None = None
        self._last_u_h: float = 0.0
        self._last_q_solar: float = 0.0
        self._save_counter = 0
        self._failure_notified = False
        self._notif_id = f"poise_heating_failure_{entry.entry_id}"
        self._entry_id = entry.entry_id
        self._active_issues: set[str] = set()
        self._lock = asyncio.Lock()
        self._enabled = True
        self._override: float | None = None
        data = entry.data
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
        self._climate_mode: str = data.get(CONF_CLIMATE_MODE, "auto")
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
        self._forecast: list[tuple[float, float]] = []
        self._forecast_at: float | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    def set_override(self, target: float | None) -> None:
        self._override = target

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
        return (dt_util.utcnow() - state.last_changed).total_seconds()

    def _local_minute(self) -> int:
        now = dt_util.now()
        return now.hour * 60 + now.minute

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
        if failed and not self._failure_notified:
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
        elif not failed and self._failure_notified:
            self._failure_notified = False
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": self._notif_id},
                blocking=False,
            )

    async def _maybe_save(self) -> None:
        self._save_counter += 1
        if self._save_counter >= EKF_SAVE_EVERY_TICKS:
            self._save_counter = 0
            try:
                await self._store.save(
                    {
                        "ekf": self._ekf.to_dict(),
                        "trm": self._trm_tracker.to_dict(),
                        "seasonless": self._seasonless.to_dict(),
                    }
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: failed to persist learned model")

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
            return {"available": False}
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
        t_out_eff = t_out if t_out is not None else (t_rm if t_rm is not None else 5.0)
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
        window_open = self._window_open()
        can_heat, can_cool = self._capability()
        device_max = self._device_max()

        if not window_open and not frozen:
            self._learn(room, t_out_eff)
        self._observe_seasonless(room, t_out_eff)

        # mould floor + dewpoint cap from humidity
        mold_min = None
        dewpoint = None
        if rh is not None:
            dewpoint = psychro_dewpoint(room, rh)
            if t_out is not None:
                mold_min = mold_min_air_temperature(t_out, rh, room)

        # schedule: night setback + optimal-start preheat (ADR-0025).
        # Resolve the forecast outdoor (I/O) here, then let the pure planner
        # decide the effective base — the decision is unit-tested without HA.
        sched = self._schedule.state_at(self._local_minute())
        do_eval = (
            not sched.is_comfort
            and self._optimal_start
            and can_heat
            and self._ekf.identified
        )
        if do_eval:
            t_out_lead = await self._forecast_outdoor(
                float(sched.minutes_to_comfort), t_out_eff
            )
            model = self._ekf.get_model()
        else:
            t_out_lead, model = t_out_eff, None
        lo, hi = HEATING_LOWER[self._category], HEATING_UPPER[self._category]
        plan = plan_preheat(
            comfort_base=self._comfort_base,
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
        )
        base = plan.base
        preheating = plan.preheating
        preheat_outdoor = plan.preheat_outdoor

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
        heating = self._enabled and not window_open and mode == "heat"
        self._last_u_h = 1.0 if heating else 0.0
        self._last_q_solar = q_solar
        self._last_target = target

        failed = (
            self._failure.update(
                now_h=now / 3600.0,
                room=room,
                setpoint=target,
                heating=heating,
            )
            or fault_active
        )
        await self._notify_failure(failed)

        if self._enabled:
            cmd = ActuatorCommand(
                self._actuator, ActuatorPath.SETPOINT, target, "heat", mode, None
            )
            try:
                await actuator_mod.write(self.hass, cmd)
            except Exception:  # noqa: BLE001 - never let actuator I/O kill the tick
                _LOGGER.exception("Poise: actuator write failed for %s", self._actuator)
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
                    fed = (
                        operative_temperature(room, t_mrt) if operative_active else room
                    )
                    try:
                        await self.hass.services.async_call(
                            "number",
                            "set_value",
                            {"entity_id": ext_num, "value": round(fed, 1)},
                            blocking=False,
                        )
                    except Exception:  # noqa: BLE001 - feed is best-effort
                        _LOGGER.exception(
                            "Poise: external-temp write failed for %s", ext_num
                        )

        await self._maybe_save()

        operative = operative_temperature(room, t_mrt)
        binding = "mold" if mold_min and mold_min >= decision.heat_sp else "en16798"
        return {
            "available": True,
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
            "heating_failure": failed,
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
            "sensor_frozen": frozen,
            "norm_binding": norm_binding,
            "device_schedule_active": sched_active,
            "device_alarm": fault_active,
            "sensor_placement_suspect": heat_source_suspect,
            "trv_input_mode": (
                "operative" if operative_active else ("air" if ext_num else "none")
            ),
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
