"""Glue coverage for the 2026-07-08 adversarial lifecycle review fixes.

Exercises the new teardown/persistence paths in ``__init__`` and the hub
hand-over methods: capability-dependent actuator park on room deletion (F3),
TRV sensor-source restore (F6), stored-model + trace cleanup (F15), the
actuation-gated boiler OFF on hub removal (F12) and on disable (F4/F16), and the
learned-model flush on HA stop (F7).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise import async_remove_entry
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from custom_components.poise.storage import PoiseStore

ROOM = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_COMFORT_BASE: 21.0,
    CONF_SETBACK_DELTA: 3.0,
    CONF_CLIMATE_MODE: "auto",
}


def _room_entry(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data={**ROOM, **data}, title="Test Room"
    )
    entry.add_to_hass(hass)
    return entry


# --- F3/F6/F15: room-entry teardown -------------------------------------------
async def test_room_remove_parks_heater_and_deletes_store(
    hass: HomeAssistant,
) -> None:
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set("climate.trv", "heat", {"hvac_modes": ["heat", "cool"]})
    entry = _room_entry(hass)
    await PoiseStore(hass, entry.entry_id).save({"ekf_version": 1, "n_heating": 3})

    await async_remove_entry(hass, entry)

    assert set_mode[-1].data["hvac_mode"] == "heat"
    # comfort_base 21 - setback 3 = 18, floored at the frost floor
    assert set_temp[-1].data["temperature"] == 18.0
    assert await PoiseStore(hass, entry.entry_id).load() is None


async def test_room_remove_off_for_cool_only(hass: HomeAssistant) -> None:
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set("climate.trv", "cool", {"hvac_modes": ["cool", "fan_only"]})
    entry = _room_entry(hass, **{CONF_CLIMATE_MODE: "cool_only"})

    await async_remove_entry(hass, entry)

    assert set_mode[-1].data["hvac_mode"] == "off"
    assert len(set_temp) == 0  # off path never writes a setpoint


async def test_room_remove_closes_valve(hass: HomeAssistant) -> None:
    set_value = async_mock_service(hass, "number", "set_value")
    hass.states.async_set("number.valve", "40", {})
    entry = _room_entry(hass, **{CONF_ACTUATOR: "number.valve"})

    await async_remove_entry(hass, entry)

    assert set_value[-1].data["value"] == 0.0


async def test_room_remove_restores_trv_sensor_source(hass: HomeAssistant) -> None:
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
    sel = ent_reg.async_get_or_create(
        "select", "demo", "sel-uid", device_id=device.id, suggested_object_id="trv_src"
    )
    hass.states.async_set("climate.trv", "heat", {"hvac_modes": ["heat"]})
    hass.states.async_set(
        sel.entity_id, "external", {"options": ["internal", "external"]}
    )

    await async_remove_entry(hass, _room_entry(hass))

    assert select_opt[-1].data["option"] == "internal"
    assert select_opt[-1].data["entity_id"] == sel.entity_id


# --- F12: hub removal is actuation-gated --------------------------------------
async def test_hub_remove_silent_when_shadow_only(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "switch", "turn_off")
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",  # OFF only
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    await async_remove_entry(hass, hub)
    assert len(turn_off) == 0  # never actuated -> no OFF on a foreign boiler


# --- F4/F16: disabling the hub hands the boiler back + clears its issue --------
async def test_hub_disable_fires_off_and_clears_issue(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "switch", "turn_off")
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on",
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    ir.async_create_issue(
        hass,
        DOMAIN,
        "frost_zone_not_controlling_boiler",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="frost_zone_not_boiler",
        translation_placeholders={"zones": "Bad"},
    )
    hub.runtime_data._active_issues.add("frost_zone_not_controlling_boiler")

    await hass.config_entries.async_set_disabled_by(
        hub.entry_id, ConfigEntryDisabler.USER
    )
    await hass.async_block_till_done()

    assert len(turn_off) == 1
    issues = ir.async_get(hass).issues
    assert (DOMAIN, "frost_zone_not_controlling_boiler") not in issues


# --- F7: flush the learned model on HA stop -----------------------------------
async def test_flush_on_stop_persists_model(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "19.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {"hvac_modes": ["heat"], "temperature": 18.0, "current_temperature": 19.0},
    )
    entry = _room_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert await PoiseStore(hass, entry.entry_id).load() is not None
