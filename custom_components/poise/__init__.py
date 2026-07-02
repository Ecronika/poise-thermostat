"""Poise — Setpoint Thermostat (Home Assistant integration entry point).

Home Assistant imports stay inside the functions so the pure core modules
remain importable without a HA runtime for fast tests (ADR-0005/0011).

Two entry types share this integration: a per-room *zone* entry (the thermostat)
and a singleton *system* hub entry (multi-zone shared-resource aggregation,
ADR-0038/0039). They are distinguished by ``entry.data[CONF_ENTRY_TYPE]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_SYSTEM, VERSION

# Config-entry-only integration schema (hassfest / quality-scale, review A3).
# Guarded so the pure core stays importable without a HA runtime (ADR-0005):
# importing any submodule runs this package __init__, and the test sandbox has
# no Home Assistant installed.
try:
    from homeassistant.helpers import config_validation as cv

    CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
except ImportError:  # pragma: no cover - only in the HA-free test environment
    pass

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


def _is_system(entry: ConfigEntry) -> bool:
    return bool(entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed tuning options in place — no reload, so learning survives (A10)."""
    if not _is_system(entry):
        await entry.runtime_data.async_apply_options(entry)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Serve + auto-register the bundled Lovelace card once (ADR-0040).

    HA imports stay local so the pure core remains importable without a HA
    runtime. The card is frontend-only and never touches control state.
    """
    import voluptuous as vol
    from homeassistant.components import websocket_api

    from .frontend import async_register_card

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/card_version"})
    @websocket_api.async_response
    async def _card_version(hass_, connection, msg):  # type: ignore[no-untyped-def]
        connection.send_result(msg["id"], {"version": VERSION})

    websocket_api.async_register_command(hass, _card_version)

    try:
        await async_register_card(hass)
    except Exception:  # noqa: BLE001 - a card failure must never block setup
        import logging

        logging.getLogger(__name__).exception("Poise card registration failed")
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

    from homeassistant.exceptions import ConfigEntryNotReady

    from .const import CONF_ACTUATOR, CONF_TEMP_SENSOR
    from .coordinator import PoiseCoordinator

    # Fail with retry/backoff (not silently available=False) while a required
    # entity is missing - the actuator/sensor may load after us (review A2).
    missing = [
        entry.data[k]
        for k in (CONF_TEMP_SENSOR, CONF_ACTUATOR)
        if hass.states.get(entry.data[k]) is None
    ]
    if missing:
        raise ConfigEntryNotReady(f"required entity not available yet: {missing}")

    coordinator = PoiseCoordinator(hass, entry)
    await coordinator.async_bootstrap()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    # A6: react promptly to room/window/actuator changes, not only on the tick.
    coordinator.attach_listeners(entry)
    # A10: hot-apply tuning-option changes in place (no reload -> learning kept).
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import Platform

    if _is_system(entry):
        unloaded_sys = await hass.config_entries.async_unload_platforms(
            entry, [Platform.BINARY_SENSOR]
        )
        return bool(unloaded_sys)

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]
    )
    if unloaded:
        # final save + repair-issue/notification cleanup (no learning loss)
        await entry.runtime_data.async_persist_and_cleanup()
    return bool(unloaded)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Deleting the hub: switch its boiler off so it is not left running (V2b)."""
    if not _is_system(entry):
        return
    import logging

    from .const import CONF_BOILER_OFF_ACTION
    from .control.hub_aggregate import parse_service_action

    off = parse_service_action(entry.data.get(CONF_BOILER_OFF_ACTION))
    if off is None:
        return
    try:
        await hass.services.async_call(
            off.domain, off.service, dict(off.data), blocking=False
        )
    except Exception:  # noqa: BLE001 - best-effort OFF on hub removal
        logging.getLogger(__name__).exception("Poise: boiler OFF on hub removal failed")
