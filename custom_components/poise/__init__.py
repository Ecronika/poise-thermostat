"""Poise — Setpoint Thermostat (Home Assistant integration entry point).

Home Assistant imports stay inside the functions so the pure core modules
remain importable without a HA runtime for fast tests (ADR-0005/0011).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import Platform

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

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [Platform.CLIMATE, Platform.SENSOR]
    )
    if unloaded:
        # final save + repair-issue/notification cleanup (no learning loss)
        await entry.runtime_data.async_persist_and_cleanup()
    return unloaded
