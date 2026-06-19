"""Home Assistant coordinator — wires the pure pipeline to HA (ADR-0006/0013).

Each tick reads the configured zone's entities, runs the pure, tested pipeline,
and writes exactly one command to the underlying actuator (single writer). All
control logic stays in the pure core; this module only does I/O.
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
    DEFAULT_TARGET_C,
    DEVICE_MAX_C,
    DOMAIN,
    FROST_FLOOR_C,
    TICK_INTERVAL_S,
)
from .contracts import ActuatorCommand
from .controller import BangBangController
from .ingestion import RawSample, ingest_temperature
from .pipeline import ZoneInputs, corridor_for, run_tick

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
        self._category = Category(data.get(CONF_CATEGORY, "II"))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    def set_override(self, target: float | None) -> None:
        self._override = target

    def _read(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        return _num(self.hass.states.get(entity_id))

    def _build_zone(self) -> ZoneInputs | None:
        air = self._read(self._temp)
        if air is None:
            return None
        now = self._clock.monotonic()
        reading = ingest_temperature([RawSample(air, now)], now=now)
        t_out = self._read(self._outdoor)
        t_rm = self._read(self._trm)
        if t_rm is None:
            t_rm = t_out  # proxy until a running-mean sensor is connected
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

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            return await self._run_once()

    async def _run_once(self) -> dict[str, Any]:
        zone = self._build_zone()
        if zone is None:
            return {"available": False}
        corridor = corridor_for(zone)
        commands = run_tick({"z": zone}, clock=self._clock, controller=self._controller)
        command = commands.get("z")
        if self._override is not None:
            target, _ = corridor.clamp(self._override)
        elif command is not None:
            target = command.value
        else:
            target = corridor.target
        target = round(target, 1)
        heating = self._enabled and zone.t_air.value < target - 0.1

        if self._enabled and command is not None:
            final = ActuatorCommand(
                self._actuator,
                command.path,
                target,
                "heat",
                command.reason,
                command.clamped_by,
            )
            try:
                await actuator_mod.write(self.hass, final)
            except Exception:  # noqa: BLE001 - never let actuator I/O kill the tick
                _LOGGER.exception("Poise: actuator write failed for %s", self._actuator)

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
            "source": zone.t_air.source.value,
        }
