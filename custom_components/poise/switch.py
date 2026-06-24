"""Switch platform — window-detection bypass (ADR-0041, stage 2).

A per-zone toggle that makes Poise ignore the open-window reaction (configured
sensor and sensorless slope alike). It is the escape hatch for a false slope
detection or a deliberate "heat with the window open" override (community:
BT #1638/#1487). When on, the window signal is forced closed; the underlying
detection still runs and is reported, it is just not applied.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoiseCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoiseCoordinator = entry.runtime_data
    async_add_entities([PoiseWindowBypassSwitch(coordinator, entry)])


class PoiseWindowBypassSwitch(CoordinatorEntity[PoiseCoordinator], SwitchEntity):
    """Toggle that suppresses the open-window reaction for this zone."""

    _attr_has_entity_name = True
    _attr_translation_key = "window_bypass"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, coordinator: PoiseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_window_bypass"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.zone_name,
            manufacturer="Poise",
            model="Setpoint Thermostat",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.window_bypass

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_window_bypass(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_window_bypass(False)
        await self.coordinator.async_request_refresh()
