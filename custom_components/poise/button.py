"""Button platform — explicit comfort feedback (ADR-0067 F1).

Two per-zone buttons ("too warm" / "too cold"): the voluntary feedback channel
behind the household clo-offset suggestion learning. A press folds ONE
observation into the persisted feedback statistic — observe-only, nothing
acts, and masked situations (open window, active hold, setback/absent, frozen
sensors, invalid PMV, anticipation extreme day, far-from-neutral PMV) are
discarded by the coordinator with a debug-logged reason.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoiseCoordinator

# Coordinator-driven; a press is a single fold, no per-entity throttling.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoiseCoordinator = entry.runtime_data
    async_add_entities(
        [
            PoiseComfortFeedbackButton(coordinator, entry, "warm"),
            PoiseComfortFeedbackButton(coordinator, entry, "cold"),
        ]
    )


class PoiseComfortFeedbackButton(CoordinatorEntity[PoiseCoordinator], ButtonEntity):  # type: ignore[misc]
    """One direction of the "too warm / too cold" feedback channel."""

    _attr_has_entity_name = True
    # Like the window-bypass switch: enabled by default because it is
    # user-facing INPUT, not a diagnostic — a hidden feedback button collects
    # nothing, and the ADR-0067 F2 clo-offset suggestion is built on this
    # statistic. Deliberately part of the lean default-entity contract
    # (test_entity_defaults).
    _attr_entity_registry_enabled_default = True

    def __init__(
        self, coordinator: PoiseCoordinator, entry: ConfigEntry, direction: str
    ) -> None:
        super().__init__(coordinator)
        self._direction = direction
        self._attr_translation_key = f"too_{direction}"
        self._attr_unique_id = f"{entry.entry_id}_feedback_{direction}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.zone_name,
            manufacturer="Poise",
            model="Setpoint Thermostat",
            entry_type=DeviceEntryType.SERVICE,
            via_device=coordinator.via_device_id,
        )

    async def async_press(self) -> None:
        self.coordinator.submit_comfort_feedback(self._direction)
