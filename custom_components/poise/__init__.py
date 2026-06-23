"""Poise — Setpoint Thermostat (Home Assistant integration entry point).

Home Assistant imports stay inside the functions so the pure core modules
remain importable without a HA runtime for fast tests (ADR-0005/0011).

Two entry types share this integration: a per-room *zone* entry (the thermostat)
and a singleton *system* hub entry (multi-zone shared-resource aggregation,
ADR-0038/0039). They are distinguished by ``entry.data[CONF_ENTRY_TYPE]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SYSTEM, VERSION

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


def _is_system(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve + auto-register the bundled Lovelace card once (ADR-0040).

    HA imports stay local so the pure core remains importable without a HA
    runtime. The card is frontend-only and never touches control state.
    """
    import voluptuous as vol
    from homeassistant.components import websocket_api
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
    from homeassistant.core import CoreState

    from .frontend import JSModuleRegistration

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/card_version"})
    @websocket_api.async_response
    async def _card_version(hass_, connection, msg):  # type: ignore[no-untyped-def]
        connection.send_result(msg["id"], {"version": VERSION})

    websocket_api.async_register_command(hass, _card_version)

    async def _register(_event=None):  # type: ignore[no-untyped-def]
        try:
            await JSModuleRegistration(hass).async_register()
        except Exception:  # noqa: BLE001 — frontend registration must never block setup
            import logging

            logging.getLogger(__name__).exception("Poise card registration failed")

    if hass.state is CoreState.running:
        await _register()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register)
    return True


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
