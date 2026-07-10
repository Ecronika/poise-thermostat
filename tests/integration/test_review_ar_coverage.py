"""CI-only coverage for the 2026-07-09 adversarial review (AR-xx) teardown paths.

Targets the new lifecycle glue the 2026-07-08 batch does not reach: the room
DISABLE park (``live_mode=True``, AR-03/AR-13), the idempotent / non-matching
branches of the TRV sensor-source restore (AR-18), rotated-trace cleanup (AR-44),
the setup guard for a registry-disabled required entity (AR-33), the hub-removal
boiler OFF gated on a persisted ``has_actuated`` (AR-15/AR-24), the hub
unavailable-safe frost request (AR-05), the ``PoiseHubStore`` round-trip plus its
restore/persist error paths and the reconcile-divergence branch (AR-08), and the
boiler-OFF hand-over helper (AR-24).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips
the whole directory at collection time.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise import async_remove_entry
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_ACTIVATION_DELAY,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_BOILER_MIN_OFF,
    CONF_BOILER_MIN_ON,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from custom_components.poise.hub_coordinator import PoiseHubCoordinator
from custom_components.poise.storage import PoiseHubStore, PoiseStore

ROOM: dict[str, Any] = {
    CONF_NAME: "AR Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_COMFORT_BASE: 21.0,
    CONF_SETBACK_DELTA: 3.0,
    CONF_CLIMATE_MODE: "auto",
}

_ON = "switch.boiler/switch.turn_on"
_OFF = "switch.boiler/switch.turn_off"


def _room_entry(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data={**ROOM, **data},
        title="AR Room",
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_room(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    hass.states.async_set("sensor.room_temp", "19.0", {"device_class": "temperature"})
    entry = _room_entry(hass, **data)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _setup_hub(hass: HomeAssistant, **data_extra: Any) -> PoiseHubCoordinator:
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_COUNT_THRESHOLD: 1,
            **data_extra,
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()
    return hub.runtime_data


# --- AR-03/AR-13: DISABLING a room parks the actuator (live_mode=True) ---------
async def test_room_disable_parks_heater(hass: HomeAssistant) -> None:
    """AR-03: disabling a room (kept, not deleted) hands a self-regulating heater
    back to heat@setback via ``_park_room_actuator(live_mode=True)``."""
    hass.states.async_set(
        "climate.trv",
        "heat",
        {"hvac_modes": ["heat"], "temperature": 18.0, "current_temperature": 19.0},
    )
    entry = await _setup_room(hass)
    coord = entry.runtime_data
    coord._has_actuated = True  # AR-11: gate the teardown park
    coord._climate_mode = "auto"

    with patch("custom_components.poise._execute_park", new_callable=AsyncMock) as park:
        await hass.config_entries.async_set_disabled_by(
            entry.entry_id, ConfigEntryDisabler.USER
        )
        await hass.async_block_till_done()

    assert park.await_count == 1
    plan = park.await_args.args[2]
    assert plan.kind == "climate"
    assert plan.hvac_mode == "heat"
    assert plan.setpoint == 18.0  # comfort_base 21 - setback 3, floored at 7


async def test_room_disable_parks_cool_only_off(hass: HomeAssistant) -> None:
    """AR-13: a room whose LIVE climate mode is cool_only parks OFF on disable,
    never heat@setback, even on a heat-capable device."""
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "cool"],
            "temperature": 18.0,
            "current_temperature": 19.0,
        },
    )
    entry = await _setup_room(hass)
    coord = entry.runtime_data
    coord._has_actuated = True
    coord._climate_mode = "cool_only"

    with patch("custom_components.poise._execute_park", new_callable=AsyncMock) as park:
        await hass.config_entries.async_set_disabled_by(
            entry.entry_id, ConfigEntryDisabler.USER
        )
        await hass.async_block_till_done()

    assert park.await_count == 1
    plan = park.await_args.args[2]
    assert plan.hvac_mode == "off"
    assert plan.setpoint is None


# --- _execute_park valve branch + AR-18 restore idempotency/skip --------------
async def test_room_remove_valve_parks_closed(hass: HomeAssistant) -> None:
    """``_execute_park`` valve branch: a direct ``number.`` valve is driven to 0 %
    (closed) on removal (F3)."""
    set_value = async_mock_service(hass, "number", "set_value")
    hass.states.async_set("number.valve", "40", {})
    entry = _room_entry(hass, **{CONF_ACTUATOR: "number.valve"})
    await PoiseStore(hass, entry.entry_id).save({"has_actuated": True})

    await async_remove_entry(hass, entry)

    assert set_value[-1].data["value"] == 0.0
    assert set_value[-1].data["entity_id"] == "number.valve"


async def test_restore_trv_internal_skips_internal_and_nonmatch(
    hass: HomeAssistant,
) -> None:
    """AR-18: the TRV sensor-source restore flips only a genuine external->internal
    select, skips one already 'internal' (idempotent) and one whose options are not
    an internal/external pair (not a sensor-source select)."""
    select_opt = async_mock_service(hass, "select", "select_option")
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")

    owner = MockConfigEntry(domain="demo", unique_id="owner")
    owner.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("demo", "trv-device")}
    )
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "climate", "demo", "trv-uid", device_id=device.id, suggested_object_id="trv"
    )
    src = ent_reg.async_get_or_create(
        "select", "demo", "s1", device_id=device.id, suggested_object_id="src"
    )
    already = ent_reg.async_get_or_create(
        "select", "demo", "s2", device_id=device.id, suggested_object_id="src2"
    )
    other = ent_reg.async_get_or_create(
        "select", "demo", "s3", device_id=device.id, suggested_object_id="mode"
    )
    hass.states.async_set("climate.trv", "heat", {"hvac_modes": ["heat"]})
    hass.states.async_set(
        src.entity_id, "external", {"options": ["internal", "external"]}
    )
    hass.states.async_set(
        already.entity_id, "internal", {"options": ["internal", "external"]}
    )
    hass.states.async_set(other.entity_id, "low", {"options": ["low", "high"]})

    entry = _room_entry(hass)
    await PoiseStore(hass, entry.entry_id).save(
        {"has_actuated": True, "climate_mode": "auto"}
    )
    await async_remove_entry(hass, entry)

    assert len(select_opt) == 1  # only the 'external' select is switched
    assert select_opt[-1].data["entity_id"] == src.entity_id
    assert select_opt[-1].data["option"] == "internal"


# --- AR-33: a registry-disabled required entity fails setup cleanly -----------
async def test_setup_guard_repairs_disabled_required_entity(
    hass: HomeAssistant,
) -> None:
    """AR-33: a required entity DISABLED in the registry raises a fixable
    ConfigEntryError + repair issue instead of an endless not-ready retry."""
    hass.states.async_set("sensor.room_temp", "20", {"device_class": "temperature"})
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "climate",
        "demo",
        "trv-uid",
        suggested_object_id="trv",  # -> climate.trv, matching ROOM's actuator
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    entry = _room_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert (
        DOMAIN,
        f"required_entity_disabled_{entry.entry_id}",
    ) in ir.async_get(hass).issues


# --- AR-44: removal deletes the trace file AND its rotated generation ----------
async def test_room_remove_deletes_rotated_trace(hass: HomeAssistant) -> None:
    """AR-44: removal deletes both the trace file and its single rotated
    generation (``<id>.jsonl`` and ``<id>.jsonl.1``)."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set("climate.trv", "heat", {"hvac_modes": ["heat"]})
    entry = _room_entry(hass)
    await PoiseStore(hass, entry.entry_id).save(
        {"has_actuated": True, "climate_mode": "auto"}
    )

    trace_dir = hass.config.path("poise_traces")
    os.makedirs(trace_dir, exist_ok=True)
    base = os.path.join(trace_dir, f"{entry.entry_id}.jsonl")
    for path in (base, f"{base}.1"):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{}\n")

    await async_remove_entry(hass, entry)

    assert not os.path.exists(base)
    assert not os.path.exists(f"{base}.1")


# --- AR-15/AR-24/AR-29: hub removal fires OFF from a persisted has_actuated ----
async def test_hub_remove_fires_off_from_persisted_state(hass: HomeAssistant) -> None:
    """AR-15/AR-24: deleting a hub that DID actuate (both actions wired + a
    persisted ``has_actuated``) fires the timeout-bounded boiler OFF and always
    clears the frost repair issue afterwards (AR-29)."""
    turn_off = async_mock_service(hass, "switch", "turn_off")
    await PoiseHubStore(hass).save({"has_actuated": True, "boiler_on": True})
    ir.async_create_issue(
        hass,
        DOMAIN,
        "frost_zone_not_controlling_boiler",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="frost_zone_not_boiler",
        translation_placeholders={"zones": "Bad"},
    )
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_ON_ACTION: _ON,
            CONF_BOILER_OFF_ACTION: _OFF,
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)

    await async_remove_entry(hass, hub)

    assert len(turn_off) == 1
    issues = ir.async_get(hass).issues
    assert (DOMAIN, "frost_zone_not_controlling_boiler") not in issues


# --- AR-05: an unavailable-safe boiler zone still fires the shared boiler ------
async def test_hub_fires_frost_for_unavailable_safe_zone(hass: HomeAssistant) -> None:
    """AR-05: a boiler-controlling zone locally degraded to unavailable-safe frost
    parking fires the shared boiler via a synthetic frost request, and the sensor
    defect is surfaced as a repair issue."""
    turn_on = async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.boiler", "off")
    zone = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.frostzone",
        data={CONF_CONTROLS_BOILER: True},
        title="Frostraum",
    )
    zone.add_to_hass(hass)
    zone.runtime_data = SimpleNamespace(
        data={"available": False, "unavailable_safe": True},
        last_update_success=True,
    )

    hub = await _setup_hub(
        hass,
        **{
            CONF_BOILER_ON_ACTION: _ON,
            CONF_BOILER_OFF_ACTION: _OFF,
            CONF_BOILER_ACTIVATION_DELAY: 0,
        },
    )
    await hub.async_refresh()
    await hass.async_block_till_done()

    assert len(turn_on) >= 1  # frost override fired the shared boiler
    assert hub.data["frost_unavailable_zones"] == [zone.entry_id]
    assert (DOMAIN, "hub_frost_zone_unavailable") in ir.async_get(hass).issues


# --- AR-08: PoiseHubStore round-trip + restore/persist error paths -------------
async def test_hub_store_save_load_remove(hass: HomeAssistant) -> None:
    """AR-08: the singleton hub store round-trips and its ``async_remove`` swaps in
    a fresh Store so a later load re-reads the deleted file as None."""
    store = PoiseHubStore(hass)
    await store.save({"boiler_on": True, "has_actuated": True})
    assert await store.load() == {"boiler_on": True, "has_actuated": True}

    await store.async_remove()
    assert await store.load() is None


async def test_hub_restores_persisted_state_and_reconciles(
    hass: HomeAssistant,
) -> None:
    """AR-08: a fresh hub restores the persisted BoilerState (believed ON) plus
    ``has_actuated``, then reconciles the belief against a physically OFF boiler
    (the divergent else-branch)."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.boiler", "off")  # physically OFF
    await PoiseHubStore(hass).save(
        {
            "boiler_on": True,
            "has_actuated": True,
            "last_switch_wall": dt_util.utcnow().timestamp() - 10_000.0,
        }
    )

    hub = await _setup_hub(
        hass,
        **{
            CONF_BOILER_ON_ACTION: _ON,
            CONF_BOILER_OFF_ACTION: _OFF,
            CONF_BOILER_ACTIVATION_DELAY: 0,
            CONF_BOILER_MIN_ON: 0,
            CONF_BOILER_MIN_OFF: 0,
        },
    )

    assert hub._has_actuated is True  # restored from the persisted payload
    assert hub._reconciled is True  # belief(on) reconciled against real(off)
    assert hub._boiler.on is False  # reconciled to the real OFF boiler


async def test_hub_restore_survives_store_load_error(hass: HomeAssistant) -> None:
    """AR-08: a failing hub-store load is caught in ``_restore_state`` and must not
    break hub setup."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.boiler", "off")

    with patch(
        "custom_components.poise.storage.PoiseHubStore.load",
        new_callable=AsyncMock,
        side_effect=RuntimeError("corrupt hub store"),
    ):
        hub = await _setup_hub(
            hass,
            **{
                CONF_BOILER_ON_ACTION: _ON,
                CONF_BOILER_OFF_ACTION: _OFF,
                CONF_BOILER_ACTIVATION_DELAY: 0,
            },
        )

    assert hub._restored is True  # the failed restore was handled, setup survived


async def test_hub_persist_survives_store_save_error(hass: HomeAssistant) -> None:
    """AR-08: a failing hub-store save is best-effort — the tick still actuates the
    boiler even though the state could not be persisted."""
    turn_on = async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.boiler", "off")
    zone = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.fz",
        data={CONF_CONTROLS_BOILER: True},
        title="FZ",
    )
    zone.add_to_hass(hass)
    zone.runtime_data = SimpleNamespace(
        data={"available": False, "unavailable_safe": True},
        last_update_success=True,
    )

    with patch(
        "custom_components.poise.storage.PoiseHubStore.save",
        new_callable=AsyncMock,
        side_effect=RuntimeError("disk full"),
    ):
        hub = await _setup_hub(
            hass,
            **{
                CONF_BOILER_ON_ACTION: _ON,
                CONF_BOILER_OFF_ACTION: _OFF,
                CONF_BOILER_ACTIVATION_DELAY: 0,
            },
        )

    assert len(turn_on) >= 1  # boiler still fired despite the persist failure
    assert hub._boiler.on is True


# --- AR-24: the boiler-OFF hand-over helper -----------------------------------
async def test_hub_fire_boiler_off_noop_without_action(hass: HomeAssistant) -> None:
    """``async_fire_boiler_off`` returns without a call when no OFF action is
    wired (the guard at the top of the hand-over helper)."""
    turn_off = async_mock_service(hass, "switch", "turn_off")
    hub = await _setup_hub(hass)  # no boiler actions
    await hub.async_fire_boiler_off()
    assert len(turn_off) == 0


async def test_hub_fire_boiler_off_swallows_error(hass: HomeAssistant) -> None:
    """``async_fire_boiler_off`` is best-effort: a boiler OFF that raises is logged,
    not propagated (the timeout-wrapped hand-over call + its except)."""

    async def _boom(call: ServiceCall) -> None:
        raise RuntimeError("boiler stuck on")

    hass.services.async_register("switch", "turn_off", _boom)
    hub = await _setup_hub(hass, **{CONF_BOILER_OFF_ACTION: _OFF})
    await hub.async_fire_boiler_off()  # must not raise


async def test_restore_trv_internal_swallows_error(hass: HomeAssistant) -> None:
    """AR-18: the TRV sensor-source restore is best-effort — a classifier/registry
    error is caught and never aborts room removal or the store cleanup."""
    async_mock_service(hass, "select", "select_option")
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")

    owner = MockConfigEntry(domain="demo", unique_id="owner")
    owner.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=owner.entry_id, identifiers={("demo", "trv-device")}
    )
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "climate", "demo", "trv-uid", device_id=device.id, suggested_object_id="trv"
    )
    sel = ent_reg.async_get_or_create(
        "select", "demo", "s1", device_id=device.id, suggested_object_id="src"
    )
    hass.states.async_set("climate.trv", "heat", {"hvac_modes": ["heat"]})
    hass.states.async_set(
        sel.entity_id, "external", {"options": ["internal", "external"]}
    )

    entry = _room_entry(hass)
    await PoiseStore(hass, entry.entry_id).save(
        {"has_actuated": True, "climate_mode": "auto"}
    )

    with patch(
        "custom_components.poise.devices.model_fixes.is_external_sensor_select",
        side_effect=RuntimeError("classifier boom"),
    ):
        await async_remove_entry(hass, entry)  # must not raise

    assert await PoiseStore(hass, entry.entry_id).load() is None

