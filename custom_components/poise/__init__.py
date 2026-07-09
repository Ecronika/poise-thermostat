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
    if _is_system(entry):
        return
    coordinator = entry.runtime_data
    # F14: a reconfigure changes entry.data and reloads the entry; this update
    # listener fires first, so skip the in-place apply on the coordinator that is
    # about to be discarded (the reload rebuilds it) — hot-apply an options-only
    # change only.
    if coordinator.structural_unchanged(entry):
        await coordinator.async_apply_options(entry)


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
        # F2: drive the hub tick from an independent timer so it keeps aggregating
        # and actuating the boiler even if its only (diagnostic) entity is disabled.
        from datetime import timedelta

        from homeassistant.helpers.event import async_track_time_interval

        from .const import TICK_INTERVAL_S

        async def _hub_tick(_now: Any) -> None:
            await hub.async_refresh()

        entry.async_on_unload(
            async_track_time_interval(
                hass, _hub_tick, timedelta(seconds=TICK_INTERVAL_S)
            )
        )
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.BINARY_SENSOR]
        )
        return True

    from homeassistant.exceptions import ConfigEntryNotReady

    from .const import CONF_ACTUATOR, CONF_TEMP_SENSOR
    from .coordinator import PoiseCoordinator

    # Retry setup while a required entity does not exist yet — the actuator/sensor
    # may load after us (review A2). This guards only a *missing* entity; one that
    # exists but is unavailable/unknown passes here and is handled by the tick's
    # degraded path (hold last state, then the frost/mould safe state).
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
    # F7/ADR-0007: flush the learned model on HA shutdown. HA does NOT call
    # async_unload_entry on a normal stop, so the counter-based save would otherwise
    # lose up to ~30 min of learning (and pending user intent) per restart.
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP

    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, coordinator.async_flush_on_stop
        )
    )
    # A10: hot-apply tuning-option changes in place (no reload -> learning kept).
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """V1 -> V2 config-entry store migration (ADR-0007).

    Split ``entry.data`` into structural inputs (kept in ``data``) + hot-applyable
    tuning (moved to ``options``) and normalize the multi-entity pickers
    (window/presence/occupancy) from a single id to a list, so the reconfigure
    step can later shrink to structural fields without silently dropping tuning
    that used to live in ``data``. Hub entries keep their content unchanged (only
    the version bumps). A future (>2) schema is refused, not downgraded.
    """
    if entry.version > 2:
        return False
    from .migration import migrate_room_entry

    new_data, new_options = migrate_room_entry(dict(entry.data), dict(entry.options))
    hass.config_entries.async_update_entry(
        entry, data=new_data, options=new_options, version=2
    )
    # F22: leave a diagnosable trace of the migration (ADR-0018).
    import logging

    logging.getLogger(__name__).info(
        "Poise: migrated config entry '%s' to schema version 2", entry.title
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import Platform

    if _is_system(entry):
        hub = entry.runtime_data
        unloaded_sys = await hass.config_entries.async_unload_platforms(
            entry, [Platform.BINARY_SENSOR]
        )
        if unloaded_sys:
            from .const import CONF_BOILER_OFF_ACTION, CONF_BOILER_ON_ACTION
            from .control.hub_aggregate import parse_service_action
            from .control.lifecycle import resolve_hub_unload_off

            # F4/F12: hand the boiler back cleanly — fire OFF only at a genuine
            # relinquish (the entry is being disabled, or the reconfigured data no
            # longer wires ON+OFF actuation), never on a plain reload and never for
            # a shadow-only hub.
            still_actuating = (
                parse_service_action(entry.data.get(CONF_BOILER_ON_ACTION)) is not None
                and parse_service_action(entry.data.get(CONF_BOILER_OFF_ACTION))
                is not None
            )
            if resolve_hub_unload_off(
                was_actuating=hub.actuation_active,
                disabled=entry.disabled_by is not None,
                still_actuating=still_actuating,
            ):
                await hub.async_fire_boiler_off()
            # F16: a disable must not leave the frost repair issue behind.
            if entry.disabled_by is not None:
                hub.cleanup_issues()
        return bool(unloaded_sys)

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]
    )
    if unloaded:
        # final save + repair-issue/notification cleanup (no learning loss)
        await entry.runtime_data.async_persist_and_cleanup()
    return bool(unloaded)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean teardown on delete — park the actuator / hand the boiler back and drop
    orphaned state (review F3/F6/F12/F15/F16/F27)."""
    if _is_system(entry):
        await _remove_hub_entry(hass, entry)
    else:
        await _remove_room_entry(hass, entry)


async def _remove_hub_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the hub: fire the boiler OFF only if Poise was actuating it (F12),
    with a blocking call so an execution error is observed not swallowed (F27), and
    clear the frost repair issue so it does not survive deinstallation (F16)."""
    import logging

    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import issue_registry as ir

    from .const import CONF_BOILER_OFF_ACTION, CONF_BOILER_ON_ACTION
    from .control.hub_aggregate import parse_service_action

    on = parse_service_action(entry.data.get(CONF_BOILER_ON_ACTION))
    off = parse_service_action(entry.data.get(CONF_BOILER_OFF_ACTION))
    # F12: only switch a boiler Poise actually commanded (BOTH actions wired) — a
    # shadow-only hub must never turn off a boiler a foreign automation runs.
    if on is not None and off is not None:
        try:
            await hass.services.async_call(
                off.domain, off.service, dict(off.data), blocking=True
            )
        except (HomeAssistantError, ValueError):
            logging.getLogger(__name__).exception(
                "Poise: boiler OFF on hub removal failed"
            )
    ir.async_delete_issue(hass, DOMAIN, "frost_zone_not_controlling_boiler")


async def _remove_room_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Park the actuator in a capability-appropriate end state, restore a TRV sensor
    source to internal, and delete the stored model + trace (review F3/F6/F15)."""
    from .const import (
        CONF_ACTUATOR,
        CONF_CLIMATE_MODE,
        CONF_COMFORT_BASE,
        CONF_SETBACK_DELTA,
        DEFAULT_COMFORT_BASE,
        DEFAULT_SETBACK_DELTA,
        FROST_FLOOR_C,
    )
    from .control.lifecycle import resolve_park_command

    cfg = {**entry.data, **entry.options}
    actuator = entry.data.get(CONF_ACTUATOR)
    if isinstance(actuator, str) and actuator:
        st = hass.states.get(actuator)
        modes = (
            [str(m) for m in (st.attributes.get("hvac_modes") or [])]
            if st is not None
            else []
        )
        setback = float(cfg.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)) - float(
            cfg.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA)
        )
        plan = resolve_park_command(
            is_valve=actuator.startswith("number."),
            hvac_modes=modes,
            heats_for_zone="heat" in modes
            and str(cfg.get(CONF_CLIMATE_MODE, "auto")) != "cool_only",
            setback_setpoint=setback,
            floor=FROST_FLOOR_C,
        )
        await _execute_park(hass, actuator, plan)
        await _restore_trv_internal(hass, actuator)
    import contextlib

    from .storage import PoiseStore

    with contextlib.suppress(Exception):  # store cleanup is best-effort
        await PoiseStore(hass, entry.entry_id).async_remove()
    await hass.async_add_executor_job(
        _remove_trace_file,
        hass.config.path("poise_traces", f"{entry.entry_id}.jsonl"),
    )


async def _execute_park(hass: HomeAssistant, actuator: str, plan: Any) -> None:
    """Perform the resolved park command on delete (review F3)."""
    import logging

    if plan is None:
        return
    try:
        if plan.kind == "valve":
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": actuator, "value": plan.valve_value},
                blocking=False,
            )
            return
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": actuator, "hvac_mode": plan.hvac_mode},
            blocking=False,
        )
        if plan.setpoint is not None:
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": actuator, "temperature": plan.setpoint},
                blocking=False,
            )
    except Exception:  # noqa: BLE001 - park on delete is best-effort
        logging.getLogger(__name__).exception("Poise: actuator park on removal failed")


async def _restore_trv_internal(hass: HomeAssistant, actuator: str) -> None:
    """Flip a TRV sensor-source select back to 'internal' so a deleted zone no
    longer regulates against a frozen external feed (review F6)."""
    import logging

    from homeassistant.helpers import entity_registry as er

    try:
        reg = er.async_get(hass)
        ent = reg.async_get(actuator)
        if ent is None or ent.device_id is None:
            return
        for dev_ent in er.async_entries_for_device(reg, ent.device_id):
            if dev_ent.domain != "select":
                continue
            st = hass.states.get(dev_ent.entity_id)
            options = (st.attributes.get("options") or []) if st is not None else []
            if "internal" in options:
                await hass.services.async_call(
                    "select",
                    "select_option",
                    {"entity_id": dev_ent.entity_id, "option": "internal"},
                    blocking=False,
                )
    except Exception:  # noqa: BLE001 - sensor-source restore is best-effort
        logging.getLogger(__name__).exception(
            "Poise: TRV sensor-source restore on removal failed"
        )


def _remove_trace_file(path: str) -> None:
    """Delete the per-entry trace file if present (review F15)."""
    import contextlib
    import os

    with contextlib.suppress(OSError):
        os.remove(path)
