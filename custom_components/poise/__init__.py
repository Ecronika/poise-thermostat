"""Poise — Setpoint Thermostat (Home Assistant integration entry point).

Home Assistant imports stay inside the functions so the pure core modules
remain importable without a HA runtime for fast tests (ADR-0005/0011).

Two entry types share this integration: a per-room *zone* entry (the thermostat)
and a singleton *system* hub entry (multi-zone shared-resource aggregation,
ADR-0038/0039). They are distinguished by ``entry.data[CONF_ENTRY_TYPE]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CONF_ENTRY_TYPE, ENTRY_TYPE_SYSTEM

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


def _is_system(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import Platform

    if _is_system(entry):
        from .hub_coordinator import PoiseHubCoordinator

        hub = PoiseHubCoordinator(hass, entry)
        await hub.async_config_entry_first_refresh()
        entry.runtime_data = hub
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.BINARY_SENSOR]
        )
        return True

    from .coordinator import PoiseCoordinator

    coordinator = PoiseCoordinator(hass, entry)
    await coordinator.async_bootstrap()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.CLIMATE, Platform.SENSOR]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import Platform

    if _is_system(entry):
        return await hass.config_entries.async_unload_platforms(
            entry, [Platform.BINARY_SENSOR]
        )

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [Platform.CLIMATE, Platform.SENSOR]
    )
    if unloaded:
        # final save + repair-issue/notification cleanup (no learning loss)
        await entry.runtime_data.async_persist_and_cleanup()
    return unloaded
