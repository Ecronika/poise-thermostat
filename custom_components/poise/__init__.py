"""Poise — Setpoint Thermostat (Home Assistant integration entry point).

HA-specific imports are kept inside the functions so the pure core modules
(contracts, clock, ingestion, arbitration, controller, pipeline) stay
importable without a Home Assistant runtime for fast, deterministic tests
(ADR-0005 dependency direction, ADR-0011 testability).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import PoiseCoordinator

    coordinator = PoiseCoordinator(hass, entry)
    await coordinator.async_bootstrap()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
