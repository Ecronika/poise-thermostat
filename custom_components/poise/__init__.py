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
    """Apply an entry update: hot-apply tuning, reload on a structural change.

    E.13d: this listener is the SINGLE reload authority. HA deprecated the
    combination of an update listener with a reloading config-flow method
    (double load / race) — warning since 2026.6, error from 2026.12 — and the
    listener is the half we must keep: hot-applying tuning without a reload is
    what preserves the learned model for a mere comfort tweak. So the flow now
    only stores (``async_update_entry`` + ``async_abort`` written out —
    ``ConfigFlow.async_update_and_abort`` only exists from HA 2025.12, above
    our minimum; see ``config_flow.py``) and the decision lives here:

    * ``entry.data`` unchanged -> options-only -> hot-apply in place;
    * ``entry.data`` changed (a reconfigure rewired the zone) -> reload, which
      rebuilds the coordinator from the new wiring.

    Hub entries carry no coordinator state worth preserving, so a structural
    change reloads them the same way.
    """
    if _is_system(entry):
        # The hub has no hot-applyable tuning (F9), so a structural change can
        # only be rebuilt — but HA fires this listener for EVERY entry change
        # (rename, pref_disable_polling, …), and reloading on those would drop
        # the boiler timers for nothing.
        hub = entry.runtime_data
        if not hub.structural_unchanged(entry):
            hass.config_entries.async_schedule_reload(entry.entry_id)
        return
    coordinator = entry.runtime_data
    if coordinator.structural_unchanged(entry):
        await coordinator.async_apply_options(entry)
        return
    # Structural change: the coordinator in runtime_data is about to be
    # discarded, so do NOT hot-apply onto it — rebuild the entry instead.
    # SCHEDULE, never await: we are inside the entry-update that HA is still
    # processing (the flow has not returned yet), and awaiting the reload from
    # here tears the entry down mid-update. ``async_schedule_reload`` is what
    # HA's own reloading flow methods use.
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Integration-level setup: card, websocket command and domain services.

    Serves + auto-registers the bundled Lovelace card (ADR-0040) and the
    ``poise/card_version`` websocket command, and registers the two domain
    services ``poise.resume_schedule`` (ADR-0059 §6) and
    ``poise.comfort_feedback`` (ADR-0067 F1). HA imports stay local so the
    pure core remains importable without a HA runtime. The card is
    frontend-only and never touches control state.
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

    # ADR-0059 §6: poise.resume_schedule — clear any active manual override/preset on
    # the targeted room zones (or every room zone when no target is given) so they
    # fall back to the schedule at once. System/hub entries and entries without a live
    # coordinator (not yet / failed to set up) are skipped defensively.
    from homeassistant.core import ServiceCall
    from homeassistant.helpers.service import async_extract_config_entry_ids

    from .control.override import OverrideMode

    _resume_target_keys = ("entity_id", "device_id", "area_id", "floor_id", "label_id")

    async def _resume_schedule(call: ServiceCall) -> None:
        has_target = any(call.data.get(key) for key in _resume_target_keys)
        referenced = await async_extract_config_entry_ids(call) if has_target else set()
        for entry in hass.config_entries.async_entries(DOMAIN):
            if _is_system(entry):
                continue
            if has_target and entry.entry_id not in referenced:
                continue
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is None:
                continue
            coordinator.set_override(None, reason="user_resume")
            coordinator.set_preset(OverrideMode.NONE)
            await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "resume_schedule", _resume_schedule)

    # ADR-0067 F1: poise.comfort_feedback — fold one explicit "too warm/cold"
    # observation into the targeted room zones' feedback statistic (or every
    # room zone without a target). Observe-only; same defensive entry walk as
    # resume_schedule.
    import voluptuous as vol

    async def _comfort_feedback(call: ServiceCall) -> None:
        direction = call.data["direction"]
        has_target = any(call.data.get(key) for key in _resume_target_keys)
        referenced = await async_extract_config_entry_ids(call) if has_target else set()
        for entry in hass.config_entries.async_entries(DOMAIN):
            if _is_system(entry):
                continue
            if has_target and entry.entry_id not in referenced:
                continue
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is None:
                continue
            coordinator.submit_comfort_feedback(direction)

    hass.services.async_register(
        DOMAIN,
        "comfort_feedback",
        _comfort_feedback,
        schema=vol.Schema(
            {vol.Required("direction"): vol.In(["warm", "cold"])},
            extra=vol.ALLOW_EXTRA,  # HA target keys ride along
        ),
    )
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

        # AR-02: hold the tick's unsub on the hub itself instead of registering it
        # via entry.async_on_unload. async_on_unload would cancel the timer only
        # AFTER async_unload_platforms; the hub-unload branch cancels it FIRST,
        # before the blocking boiler OFF, so a tick can never fire in between and
        # command the boiler back ON just after we have handed it off.
        hub._tick_unsub = async_track_time_interval(
            hass, _hub_tick, timedelta(seconds=TICK_INTERVAL_S)
        )
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.BINARY_SENSOR]
        )
        # E.13d: the hub needs the same single reload authority as a room.
        # Its reconfigure now only STORES the new data, so without
        # a listener the new boiler wiring would sit in the entry unused until
        # the next restart. The hub has no hot-applyable tuning (its options
        # flow aborts, F9), so any update means: rebuild. Registered after the
        # forward for the same reason as the room path (AR-23).
        entry.async_on_unload(entry.add_update_listener(_async_options_updated))
        return True

    from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import issue_registry as ir

    from .const import CONF_ACTUATOR, CONF_TEMP_SENSOR
    from .coordinator import PoiseCoordinator

    # AR-34: read the required entity ids defensively — a corrupt entry that lost a
    # structural field must fail with a clear ConfigEntryError (a fixable error
    # state the user can act on), not raise KeyError from ``entry.data[...]`` into
    # an opaque SETUP_ERROR traceback.
    required: dict[str, str] = {}
    for key in (CONF_TEMP_SENSOR, CONF_ACTUATOR):
        eid = entry.data.get(key)
        if not isinstance(eid, str) or not eid:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="missing_required_setting",
                translation_placeholders={"title": entry.title, "key": key},
            )
        required[key] = eid

    # AR-33: a required entity that exists in the registry but is DISABLED there
    # never publishes a state, so a plain ConfigEntryNotReady would retry forever.
    # Surface a repair issue and fail with ConfigEntryError (a fixable error, no
    # endless not-ready loop). Defensive: a registry hiccup must never itself abort
    # setup.
    ent_reg = er.async_get(hass)
    disabled_ids: list[str] = []
    for eid in required.values():
        try:
            reg_ent = ent_reg.async_get(eid)
        except Exception:  # noqa: BLE001 - never let a registry lookup break setup
            reg_ent = None
        if reg_ent is not None and reg_ent.disabled:
            disabled_ids.append(eid)
    if disabled_ids:
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"required_entity_disabled_{entry.entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="required_entity_disabled",
            translation_placeholders={
                "entities": ", ".join(disabled_ids),
                "name": entry.title,
            },
        )
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="required_entity_disabled",
            translation_placeholders={"entities": ", ".join(disabled_ids)},
        )

    # Retry setup while a required entity does not exist yet — the actuator/sensor
    # may load after us (review A2). This guards only a *missing* entity; one that
    # exists but is unavailable/unknown passes here and is handled by the tick's
    # degraded path (hold last state, then the frost/mould safe state).
    missing = [eid for eid in required.values() if hass.states.get(eid) is None]
    if missing:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="required_entity_missing",
            translation_placeholders={"entities": ", ".join(missing)},
        )

    coordinator = PoiseCoordinator(hass, entry)
    await coordinator.async_bootstrap()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]
    )
    # AR-23: attach the state/stop/options listeners only AFTER the platforms set
    # up successfully. Registering them before the forward would leave dangling
    # listeners (and an EVENT_HOMEASSISTANT_STOP flush) bound to a half-initialised
    # entry if async_forward_entry_setups raised.
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP

    # React promptly to room/window/actuator changes, not only on the tick.
    coordinator.attach_listeners(entry)
    # F7/ADR-0007: flush the learned model on HA shutdown. HA does NOT call
    # async_unload_entry on a normal stop, so the counter-based save would otherwise
    # lose up to ~30 min of learning (and pending user intent) per restart.
    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, coordinator.async_flush_on_stop
        )
    )
    # Hot-apply tuning-option changes in place (no reload -> learning kept).
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Config-entry schema migration to 2.3 (ADR-0007/0008/0059).

    Split ``entry.data`` into structural inputs (kept in ``data``) + hot-applyable
    tuning (moved to ``options``) and normalize the multi-entity pickers
    (window/presence/occupancy) from a single id to a list, so the reconfigure
    step can later shrink to structural fields without silently dropping tuning
    that used to live in ``data``. Hub entries keep their content unchanged (only
    the version bumps).

    MINOR_VERSION 3 widens the REACH of that one split to entries stored at 2.2:
    the onboarding step used to write ``comfort_base``/``category``
    (``SETUP_TUNING_KEYS``) into ``data``, so those entries carried tuning in
    ``data`` until their first reconfigure. Re-running the split relocates them —
    and only them, because every other key a v2.2 ``data`` can hold is in
    ``STRUCTURAL_KEYS``. A value already present in ``options`` is the newer one
    and survives (the split's options-over-data merge), and the split is
    idempotent, so a repeated migration cannot corrupt the store.
    """
    # AR-36: HA itself refuses to *downgrade* a config entry — it never calls
    # async_migrate_entry when entry.version exceeds the integration's schema — so
    # this guard is defensive/dead. Kept as an explicit no-downgrade contract.
    if entry.version > 2:
        return False
    from .migration import apply_override_policy_default, migrate_room_entry

    stored_minor = entry.minor_version
    new_data, new_options = migrate_room_entry(dict(entry.data), dict(entry.options))
    # ADR-0059 §7: a room zone stored below minor_version 2 predates the manual
    # override policy, so pin it to the fixed-timer hold to keep today's behaviour;
    # a fresh zone leaves the key unset and the coordinator falls back to schedule.
    if not _is_system(entry):
        new_options = apply_override_policy_default(
            new_data, new_options, stored_minor_version=stored_minor
        )
    # AR-36: pin the minor_version alongside the major so HA records a complete
    # (version, minor_version) pair and does not treat the entry as needing a
    # minor migration on every load.
    hass.config_entries.async_update_entry(
        entry, data=new_data, options=new_options, version=2, minor_version=3
    )
    # F22: leave a diagnosable trace of the migration (ADR-0018).
    import logging

    logging.getLogger(__name__).info(
        "Poise: migrated config entry '%s' to schema version 2.3", entry.title
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import Platform

    if _is_system(entry):
        hub = entry.runtime_data
        from .const import CONF_BOILER_OFF_ACTION, CONF_BOILER_ON_ACTION
        from .control.hub_aggregate import BoilerState, parse_service_action
        from .control.lifecycle import resolve_hub_unload_off

        # AR-02: cancel the independent hub tick FIRST — before the (blocking) OFF
        # and before async_unload_platforms — so a tick cannot fire mid-hand-over
        # and switch the boiler back ON after we relinquish it.
        tick_unsub = getattr(hub, "_tick_unsub", None)
        if tick_unsub is not None:
            tick_unsub()
            hub._tick_unsub = None

        # F4/F12: hand the boiler back cleanly — fire OFF only at a genuine
        # relinquish (the entry is being disabled, the reconfigured data no longer
        # wires ON+OFF actuation, or it now points the boiler at a DIFFERENT target),
        # never on a plain reload onto the same target and never for a shadow-only
        # hub.
        old_off = (
            hub._action_off.data.get("entity_id")
            if hub._action_off is not None
            else None
        )
        old_on = (
            hub._action_on.data.get("entity_id") if hub._action_on is not None else None
        )
        new_off = parse_service_action(entry.data.get(CONF_BOILER_OFF_ACTION))
        new_on = parse_service_action(entry.data.get(CONF_BOILER_ON_ACTION))
        new_off_target = new_off.data.get("entity_id") if new_off is not None else None
        new_on_target = new_on.data.get("entity_id") if new_on is not None else None
        # AR-01: a reconfigure that re-points the boiler at a DIFFERENT target must
        # hand the OLD boiler back (async_fire_boiler_off fires the hub's OLD wired
        # action), not leave it running under the new target.
        target_changed = old_off != new_off_target or old_on != new_on_target
        still_actuating = new_on is not None and new_off is not None
        # AR-25: the hand-over OFF + the issue cleanup must run regardless of
        # whether the platform unload later succeeds — do them before it.
        if resolve_hub_unload_off(
            was_actuating=hub.actuation_active,
            disabled=entry.disabled_by is not None,
            still_actuating=still_actuating,
            target_changed=target_changed,
        ):
            await hub.async_fire_boiler_off()
            # AR-02: defensively reflect the relinquished state so nothing re-fires
            # the boiler ON from a stale belief.
            hub._boiler = BoilerState(on=False)
        # F16: a disable must not leave the frost repair issue behind.
        if entry.disabled_by is not None:
            hub.cleanup_issues()

        unloaded_sys = await hass.config_entries.async_unload_platforms(
            entry, [Platform.BINARY_SENSOR]
        )
        return bool(unloaded_sys)

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]
    )
    if unloaded:
        # Final save + repair-issue cleanup; a failed save keeps the
        # persistence_failed issue (see async_persist_and_cleanup).
        await entry.runtime_data.async_persist_and_cleanup()
        # AR-03: a DISABLE (entry kept but inactive) must also hand the actuator
        # back to a safe autonomous state — the same capability-appropriate park as
        # on removal — but WITHOUT deleting the learned model/trace, so a re-enable
        # resumes learning. A plain reload (disabled_by is None) keeps hands off so
        # it does not fight the imminent rebuild.
        if entry.disabled_by is not None:
            await _park_room_actuator(hass, entry, live_mode=True)
    return bool(unloaded)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean teardown on delete — park the actuator / hand the boiler back and drop
    orphaned state (review F3/F6/F12/F15/F16/F27)."""
    if _is_system(entry):
        await _remove_hub_entry(hass, entry)
    else:
        await _remove_room_entry(hass, entry)


async def _remove_hub_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the hub: fire the boiler OFF only if Poise actually commanded it —
    both actions wired AND the hub fired it at least once (has_actuated, AR-15) —
    with a blocking, timeout-bounded call so an execution error is observed not
    swallowed (F27/AR-24), and always clear the frost repair issue so it does not
    survive deinstallation (F16), even if the OFF path raises (AR-29)."""
    import asyncio
    import logging

    import voluptuous as vol
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import issue_registry as ir

    from .const import CONF_BOILER_OFF_ACTION, CONF_BOILER_ON_ACTION
    from .control.hub_aggregate import parse_service_action

    on = parse_service_action(entry.data.get(CONF_BOILER_ON_ACTION))
    off = parse_service_action(entry.data.get(CONF_BOILER_OFF_ACTION))
    try:
        # AR-15: a shadow-only hub (or one that never reached actuation) must never
        # turn off a boiler a foreign automation runs — gate on BOTH actions wired
        # AND the hub having actually fired the boiler at least once.
        if on is not None and off is not None:
            from .storage import PoiseHubStore

            hub_state = await PoiseHubStore(hass).load()
            has_actuated = bool(hub_state and hub_state.get("has_actuated", False))
            if has_actuated:
                # AR-24: bound the blocking OFF with the same timeout the hub's
                # normal actuation path uses, so a hung boiler integration cannot
                # stall entry removal.
                from .hub_coordinator import _BOILER_CALL_TIMEOUT_S

                try:
                    async with asyncio.timeout(_BOILER_CALL_TIMEOUT_S):
                        await hass.services.async_call(
                            off.domain, off.service, dict(off.data), blocking=True
                        )
                except (HomeAssistantError, ValueError, vol.Invalid, TimeoutError):
                    logging.getLogger(__name__).exception(
                        "Poise: boiler OFF on hub removal failed"
                    )
    finally:
        # AR-29: always clear the frost repair issue on removal, even if an
        # unexpected (e.g. schema) error escaped the OFF path above.
        ir.async_delete_issue(hass, DOMAIN, "frost_zone_not_controlling_boiler")


async def _remove_room_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Park the actuator (F3/F6, gated on prior actuation AR-11), then delete the
    stored model + its rotated trace (F15/AR-44)."""
    import logging

    from homeassistant.exceptions import HomeAssistantError

    from .storage import PoiseStore

    # AR-11/AR-13: the park reads has_actuated + the live climate_mode from the
    # store, so it must run BEFORE the store is removed.
    await _park_room_actuator(hass, entry, live_mode=False)

    # AR-44: narrow the best-effort suppression to the store/IO errors we actually
    # expect and log the rest, instead of a blanket Exception swallow.
    try:
        await PoiseStore(hass, entry.entry_id).async_remove()
    except (OSError, HomeAssistantError):
        logging.getLogger(__name__).exception(
            "Poise: EKF store removal on delete failed"
        )
    await hass.async_add_executor_job(
        _remove_trace_file,
        hass.config.path("poise_traces", f"{entry.entry_id}.jsonl"),
    )


async def _park_room_actuator(
    hass: HomeAssistant, entry: ConfigEntry, *, live_mode: bool
) -> None:
    """Park a room's actuator in a capability-appropriate end state and restore a
    TRV sensor source to internal (F3/F6). Shared by room-entry removal
    (``live_mode=False``) and a disable-unload (``live_mode=True``, AR-03); the
    caller performs any store/trace deletion.

    Gated on Poise having actually actuated the zone at least once (AR-11): a zone
    that never wrote the actuator leaves both the actuator and its sensor-source
    select untouched. ``heats_for_zone`` is decided from the LIVE climate mode in
    the persisted store (AR-13, the value a runtime ``set_climate_mode`` wrote),
    not from the static entry config which a runtime mode change never updates.
    """
    import logging

    from .const import (
        CONF_ACTUATOR,
        CONF_COMFORT_BASE,
        CONF_SETBACK_DELTA,
        DEFAULT_COMFORT_BASE,
        DEFAULT_SETBACK_DELTA,
        FROST_FLOOR_C,
    )
    from .control.lifecycle import resolve_park_command
    from .storage import PoiseStore

    stored = await PoiseStore(hass, entry.entry_id).load() or {}
    # AR-11: never actuated -> nothing to hand back; skip park AND select-restore.
    if not stored.get("has_actuated", False):
        return
    actuator = entry.data.get(CONF_ACTUATOR)
    if not (isinstance(actuator, str) and actuator):
        return
    logging.getLogger(__name__).debug(
        "Poise: parking room actuator %s on %s",
        actuator,
        "disable" if live_mode else "removal",
    )
    cfg = {**entry.data, **entry.options}
    st = hass.states.get(actuator)
    modes = (
        [str(m) for m in (st.attributes.get("hvac_modes") or [])]
        if st is not None
        else []
    )
    setback = float(cfg.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)) - float(
        cfg.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA)
    )
    # AR-13: the live climate mode is the store's, not the static entry config's.
    climate_mode = str(stored.get("climate_mode", "auto"))
    plan = resolve_park_command(
        is_valve=actuator.startswith("number."),
        hvac_modes=modes,
        heats_for_zone="heat" in modes and climate_mode != "cool_only",
        setback_setpoint=setback,
        floor=FROST_FLOOR_C,
    )
    await _execute_park(hass, actuator, plan)
    await _restore_trv_internal(hass, actuator)


async def _execute_park(hass: HomeAssistant, actuator: str, plan: Any) -> None:
    """Perform the resolved park command on delete/disable (review F3/F27).

    Blocking on every call (AR-17/F27) so an execution error surfaces instead of
    being lost as a fire-and-forget background task, and ``set_hvac_mode`` is
    awaited BEFORE ``set_temperature`` so a device that only accepts a setpoint in
    its target mode honours it. Expected execution errors are caught and logged,
    not silently swallowed.
    """
    import logging

    from homeassistant.exceptions import HomeAssistantError

    if plan is None:
        return
    try:
        if plan.kind == "valve":
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": actuator, "value": plan.valve_value},
                blocking=True,
            )
            return
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": actuator, "hvac_mode": plan.hvac_mode},
            blocking=True,
        )
        if plan.setpoint is not None:
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": actuator, "temperature": plan.setpoint},
                blocking=True,
            )
    except (HomeAssistantError, ValueError):
        logging.getLogger(__name__).exception("Poise: actuator park on removal failed")


async def _restore_trv_internal(hass: HomeAssistant, actuator: str) -> None:
    """Flip a TRV sensor-source select back to 'internal' so a deleted/disabled zone
    no longer regulates the device against a now-frozen external feed (review F6).

    Only touches a select the repo's own classifier recognises as a sensor-source
    switch (``is_external_sensor_select`` — must expose BOTH 'external' and
    'internal', AR-18) and skips one already 'internal' (idempotent, no needless
    write).
    """
    import logging

    from homeassistant.helpers import entity_registry as er

    from .devices.model_fixes import is_external_sensor_select

    try:
        reg = er.async_get(hass)
        ent = reg.async_get(actuator)
        if ent is None or ent.device_id is None:
            return
        for dev_ent in er.async_entries_for_device(reg, ent.device_id):
            if dev_ent.domain != "select":
                continue
            st = hass.states.get(dev_ent.entity_id)
            if st is None:
                continue
            options = st.attributes.get("options") or []
            # AR-18: only a genuine internal/external sensor-source select.
            if not is_external_sensor_select(dev_ent.entity_id, options):
                continue
            # AR-18: already internal -> nothing to do (idempotent, no thrash).
            if st.state == "internal":
                continue
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
    """Delete the per-entry trace file and its one rotated generation (F15/AR-44).

    ``trace/recorder.py`` rotates to ``<name>.1`` (a single previous generation),
    so a clean delete must drop both files, else a removed zone leaves a stale
    ``<entry_id>.jsonl.1`` behind.
    """
    import contextlib
    import os

    for candidate in (path, f"{path}.1"):
        with contextlib.suppress(OSError):
            os.remove(candidate)
