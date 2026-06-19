"""Home Assistant coordinator — wires the pure pipeline to HA (ADR-0006/0013).

Reads the zone's entities each tick, runs the pure tested pipeline, and writes
exactly one command to the actuator (single writer). The EKF (ADR-0002) learns
in the background and is persisted per room (ADR-0007). Live safety: window-open
pause and heating-failure notification (ADR-0012). Control output remains the
norm-comfort setpoint; direct valve modulation is enabled after live validation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import actuator as actuator_mod
from .clock import MonotonicClock
from .comfort.en16798 import Category
from .comfort.operative import operative_temperature
from .const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_HUMIDITY_SENSOR,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OUTDOOR_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_WINDOW_SENSOR,
    DEFAULT_TARGET_C,
    DEVICE_MAX_C,
    DOMAIN,
    EKF_SAVE_EVERY_TICKS,
    FROST_FLOOR_C,
    TICK_INTERVAL_S,
)
from .contracts import ActuatorCommand
from .controller import BangBangController
from .estimation.thermal_ekf import ThermalEKF
from .ingestion import RawSample, ingest_temperature
from .pipeline import ZoneInputs, corridor_for, run_tick
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


def _maturity(n: int) -> str:
    if n < 5:
        return "cold"
    if n < 50:
        return "early"
    if n < 150:
        return "learning"
    return "mature"


class PoiseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One coordinator per room; runs the pure pipeline each tick."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_S),
        )
        self._clock = MonotonicClock()
        self._controller = BangBangController()
        self._ekf = ThermalEKF()
        self._store = PoiseStore(hass, entry.entry_id)
        self._failure = HeatingFailureDetector()
        self._last_mono: float | None = None
        self._last_u_h: float = 0.0
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
            if data is not None:
                self._ekf = ThermalEKF.from_dict(data)
                _LOGGER.debug("Poise: restored learned model for %s", self.zone_name)
        except Exception:  # noqa: BLE001 - corrupt state must not block setup
            _LOGGER.exception("Poise: failed to restore learned model; starting fresh")

    def _read(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        return _num(self.hass.states.get(entity_id))

    def _window_open(self) -> bool:
        if not self._window:
            return False
        state = self.hass.states.get(self._window)
        return state is not None and state.state == "on"

    def _build_zone(self) -> ZoneInputs | None:
        air = self._read(self._temp)
        if air is None:
            return None
        now = self._clock.monotonic()
        reading = ingest_temperature([RawSample(air, now)], now=now)
        t_out = self._read(self._outdoor)
        t_rm = self._read(self._trm)
        if t_rm is None:
            t_rm = t_out
        device_max = DEVICE_MAX_C
        act = self.hass.states.get(self._actuator)
        if act is not None:
            mx = act.attributes.get("max_temp")
            if isinstance(mx, (int, float)):
                device_max = float(mx)
        return ZoneInputs(
            actuator_id=self._actuator,
            t_air=reading,
            target=DEFAULT_TARGET_C,
            frost_floor=FROST_FLOOR_C,
            device_max=device_max,
            t_rm=t_rm,
            rh_percent=self._read(self._humidity),
            t_out=t_out,
            t_mrt=self._read(self._mrt),
            category=self._category,
        )

    def _learn(self, zone: ZoneInputs) -> None:
        """Passive EKF observer; paused when a window is open (ADR-0002/0012)."""
        now = self._clock.monotonic()
        t_out = (
            zone.t_out
            if zone.t_out is not None
            else (zone.t_rm if zone.t_rm is not None else 5.0)
        )
        try:
            if self._last_mono is not None:
                dt_h = (now - self._last_mono) / 3600.0
                if 0.0 < dt_h < 1.0:
                    self._ekf.predict(dt_h, t_out=t_out, u_h=self._last_u_h)
                    self._ekf.update(zone.t_air.value)
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
                await self._store.save(self._ekf.to_dict())
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: failed to persist learned model")

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            return await self._run_once()

    async def _run_once(self) -> dict[str, Any]:
        zone = self._build_zone()
        if zone is None:
            return {"available": False}

        window_open = self._window_open()
        if not window_open:
            self._learn(zone)

        corridor = corridor_for(zone)
        commands = run_tick({"z": zone}, clock=self._clock, controller=self._controller)
        command = commands.get("z")

        if window_open:
            target = round(corridor.binding_lower().value, 1)  # close down the TRV
        elif self._override is not None:
            clamped, _ = corridor.clamp(self._override)
            target = round(clamped, 1)
        elif command is not None:
            target = command.value
        else:
            target = round(corridor.target, 1)

        heating = self._enabled and not window_open and zone.t_air.value < target - 0.1
        self._last_u_h = 1.0 if heating else 0.0

        failed = self._failure.update(
            now_h=self._clock.monotonic() / 3600.0,
            room=zone.t_air.value,
            setpoint=target,
            heating=heating,
        )
        await self._notify_failure(failed)

        if self._enabled and command is not None:
            final = ActuatorCommand(
                self._actuator, command.path, target, "heat", command.reason, None
            )
            try:
                await actuator_mod.write(self.hass, final)
            except Exception:  # noqa: BLE001 - never let actuator I/O kill the tick
                _LOGGER.exception("Poise: actuator write failed for %s", self._actuator)

        await self._maybe_save()

        lower = corridor.binding_lower()
        upper = corridor.binding_upper()
        t_mrt = self._read(self._mrt)
        operative = (
            operative_temperature(zone.t_air.value, t_mrt)
            if t_mrt is not None
            else zone.t_air.value
        )
        return {
            "available": True,
            "current_temperature": round(zone.t_air.value, 1),
            "target_temperature": target,
            "operative_temperature": round(operative, 1),
            "t_rm": round(zone.t_rm, 1) if zone.t_rm is not None else None,
            "comfort_low": round(lower.value, 1),
            "comfort_high": round(upper.value, 1),
            "binding_lower_cause": lower.cause,
            "category": self._category.value,
            "heating": heating,
            "window_open": window_open,
            "heating_failure": failed,
            "source": zone.t_air.source.value,
            "tau_hours": round(self._ekf.tau_hours, 1),
            "confidence": round(self._ekf.confidence, 2),
            "learning_phase": _maturity(self._ekf.n_updates),
        }
