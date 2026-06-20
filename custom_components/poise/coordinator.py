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
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
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
    TICK_INTERVAL_S,
)
from .contracts import ActuatorCommand, ActuatorPath
from .control.optimal_start import (
    forecast_samples_from_response,
    mean_forecast_outdoor,
    plan_preheat,
)
from .devices.capability import climate_capability
from .estimation.psychrometrics import dewpoint as psychro_dewpoint
from .estimation.running_mean import RunningMeanTracker
from .estimation.solar import clear_sky_normalized, normalize_irradiance
from .estimation.thermal_ekf import ThermalEKF
from .ingestion import RawSample, ingest_temperature
from .safety.heating_failure import HeatingFailureDetector
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
        self._store = PoiseStore(hass, entry.entry_id)
        self._failure = HeatingFailureDetector()
        self._last_mono: float | None = None
        self._last_u_h: float = 0.0
        self._last_q_solar: float = 0.0
        self._save_counter = 0
        self._failure_notified = False
        self._notif_id = f"poise_heating_failure_{entry.entry_id}"
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
            elif data is not None:
                self._ekf = ThermalEKF.from_dict(data)  # legacy: bare EKF dict
        except Exception:  # noqa: BLE001 - corrupt state must not block setup
            _LOGGER.exception("Poise: failed to restore learned model; starting fresh")

    def _read(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        return _num(self.hass.states.get(entity_id))

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
                    {"ekf": self._ekf.to_dict(), "trm": self._trm_tracker.to_dict()}
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: failed to persist learned model")

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            return await self._run_once()

    async def _run_once(self) -> dict[str, Any]:
        air = self._read(self._temp)
        if air is None:
            return {"available": False}
        now = self._clock.monotonic()
        reading = ingest_temperature([RawSample(air, now)], now=now)
        room = reading.value
        t_out = self._read(self._outdoor)
        # internal EN 16798-1 running mean, used when no external T_rm sensor.
        if t_out is not None:
            self._trm_tracker.observe(t_out, dt_util.now().toordinal())
        t_rm_sensor = self._read(self._trm)
        if t_rm_sensor is not None:
            t_rm, t_rm_source = t_rm_sensor, "sensor"
        elif self._trm_tracker.current is not None:
            t_rm, t_rm_source = self._trm_tracker.current, "internal"
        else:
            t_rm = t_out
            t_rm_source = "outdoor" if t_out is not None else None
        t_out_eff = t_out if t_out is not None else (t_rm if t_rm is not None else 5.0)
        t_rm_eff = t_rm if t_rm is not None else t_out_eff
        rh = self._read(self._humidity)
        # solar disturbance q_solar (normalised, ADR-0010): internal clear-sky
        # estimate always runs; a measured irradiance sensor overrides the value
        # used (shadow-estimator principle, ADR-0026).
        elev = self._sun_elevation()
        q_solar_internal = clear_sky_normalized(elev) if elev is not None else 0.0
        ghi = self._read(self._irradiance)
        if ghi is not None:
            q_solar, q_solar_source = normalize_irradiance(ghi), "sensor"
        elif elev is not None:
            q_solar, q_solar_source = q_solar_internal, "internal"
        else:
            q_solar, q_solar_source = 0.0, "none"
        # virtual MRT (shadow, ADR-0017/0026): exterior envelope pulls MRT toward
        # outdoor + a solar radiant bump; a measured globe/MRT sensor overrides.
        mrt_internal = virtual_mrt(room, t_out_eff, q_solar)
        mrt_sensor = self._read(self._mrt)
        if mrt_sensor is not None:
            t_mrt, mrt_source = mrt_sensor, "sensor"
        else:
            t_mrt, mrt_source = mrt_internal, "internal"
        window_open = self._window_open()
        can_heat, can_cool = self._capability()
        device_max = self._device_max()

        if not window_open:
            self._learn(room, t_out_eff)

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

        decision = comfort_decide(
            t_rm=t_rm_eff,
            room=room,
            category=self._category,
            comfort_base=base,
            can_heat=can_heat,
            can_cool=can_cool,
            climate_mode=self._climate_mode,
            t_out=t_out_eff,
            t_mrt=t_mrt,
            frost_floor=FROST_FLOOR_C,
            mold_min=mold_min,
            dewpoint=dewpoint,
            priority=self._priority,
        )

        if window_open:
            target = round(max(FROST_FLOOR_C, mold_min or FROST_FLOOR_C), 1)
            mode = "off"
        elif self._override is not None:
            clamped = min(max(self._override, decision.heat_sp), decision.cool_sp)
            target, mode = round(clamped, 1), "manual"
        else:
            target, mode = round(decision.write_setpoint, 1), decision.mode

        target = min(target, device_max)
        heating = self._enabled and not window_open and mode == "heat"
        self._last_u_h = 1.0 if heating else 0.0
        self._last_q_solar = q_solar

        failed = self._failure.update(
            now_h=now / 3600.0,
            room=room,
            setpoint=target,
            heating=heating,
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
        }
