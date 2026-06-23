"""Binary-sensor platform — boiler-demand shadow (ADR-0039, S1).

One entity on the "Poise System" hub entry. It reflects the aggregated
call-for-heat across all zones and is **diagnostic only** — Poise does not
switch any boiler in this stage (shadow; actuation is S2, opt-in).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .hub_coordinator import PoiseHubCoordinator

_ATTRS = (
    "active_zones",
    "weighted_demand",
    "frost_override",
    "zone_count",
    "controlling_zones",
    "actuation_enabled",
    "boiler_on",
    "available_power",
    "shed_count",
    "shed_zones",
    "compressor_groups",
    "flow_target",
    "flow_requested",
    "source_grants",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoiseHubCoordinator = entry.runtime_data
    async_add_entities([PoiseBoilerDemand(coordinator, entry)])


class PoiseBoilerDemand(CoordinatorEntity[PoiseHubCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "boiler_demand"
    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:fire"

    def __init__(self, coordinator: PoiseHubCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_boiler_demand"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Poise System",
            manufacturer="Poise",
            model="System Hub",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("boiler_demand"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {key: data.get(key) for key in _ATTRS}
