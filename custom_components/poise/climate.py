"""Climate platform — one Poise thermostat per room (ADR-0016).

A thin view over the coordinator (which runs the pure pipeline). The comfort
attributes are the card contract; the entity never contains control logic.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MAX_C, DOMAIN, FROST_FLOOR_C
from .coordinator import PoiseCoordinator

_ATTRS = (
    "operative_temperature",
    "t_rm",
    "t_rm_source",
    "t_rm_internal",
    "comfort_low",
    "comfort_high",
    "binding_lower_cause",
    "category",
    "source",
    "tau_hours",
    "confidence",
    "learning_phase",
    "window_open",
    "heating_failure",
    "heat_sp",
    "cool_sp",
    "mode",
    "identified",
    "identification_progress",
    "schedule_state",
    "minutes_to_comfort",
    "preheating",
    "preheat_outdoor",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoiseCoordinator = entry.runtime_data
    async_add_entities([PoiseClimate(coordinator, entry)])


class PoiseClimate(CoordinatorEntity[PoiseCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = FROST_FLOOR_C
    _attr_max_temp = DEVICE_MAX_C
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: PoiseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.zone_name,
            manufacturer="Poise",
            model="Setpoint Thermostat",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _d(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self._d.get("available"))

    @property
    def current_temperature(self) -> float | None:
        return self._d.get("current_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self._d.get("target_temperature")

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.coordinator.enabled else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if not self.coordinator.enabled:
            return HVACAction.OFF
        return HVACAction.HEATING if self._d.get("heating") else HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {key: self._d.get(key) for key in _ATTRS}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self.coordinator.set_override(float(temp))
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self.coordinator.set_enabled(hvac_mode == HVACMode.HEAT)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        self.coordinator.set_enabled(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        self.coordinator.set_enabled(False)
        await self.coordinator.async_request_refresh()
