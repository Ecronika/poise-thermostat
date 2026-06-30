"""Entry setup/unload + one live coordinator tick (review Ü1/E4).

The cycle test is the important one: it drives the *actual* actuating path
(``_run_once`` -> ``should_write`` -> ``actuator.write``) and asserts a real
``climate.set_temperature`` reaches the configured actuator — the path the
review flagged as untested.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    CONF_HUMIDITY_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


def _set_room_and_actuator(hass: HomeAssistant, *, room: float, sp: float) -> None:
    """A plausible room sensor + a heat-capable TRV with setpoint ``sp``."""
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def test_setup_creates_entities_then_unloads(hass: HomeAssistant) -> None:
    """A zone entry loads, registers climate/sensor/switch, and unloads clean."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_room_and_actuator(hass, room=19.5, sp=18.0)

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    reg = er.async_get(hass)
    domains = {e.domain for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    assert {"climate", "sensor", "switch"} <= domains

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_actuator_missing(hass: HomeAssistant) -> None:
    """Required entity absent -> ConfigEntryNotReady -> SETUP_RETRY (review A2)."""
    # only the room sensor exists; the actuator entity is not yet available
    hass.states.async_set("sensor.room_temp", "20", {"device_class": "temperature"})
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_coordinator_cycle_writes_setpoint(hass: HomeAssistant) -> None:
    """The live tick writes a setpoint to the configured actuator (the moat)."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    # room well below comfort, TRV parked at a clearly different setpoint
    _set_room_and_actuator(hass, room=18.0, sp=10.0)

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert set_temp, "coordinator did not write to the actuator"
    call = set_temp[-1]
    assert call.data["entity_id"] == "climate.trv"
    assert isinstance(call.data["temperature"], (int, float))
    # it heats toward comfort, not down to the stale 10 °C setpoint
    assert call.data["temperature"] > 15


async def test_system_hub_setup_creates_binary_sensor(hass: HomeAssistant) -> None:
    """The singleton hub entry loads and registers its boiler-demand sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
        title="Poise System",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    reg = er.async_get(hass)
    domains = {e.domain for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    assert "binary_sensor" in domains


async def test_current_humidity_published_for_card_lamp(hass: HomeAssistant) -> None:
    """ADR-0049: with a humidity sensor the climate entity exposes
    current_humidity, so the card's humidity lamp (and the native HA thermostat
    card) is actually live — not just read internally."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_room_and_actuator(hass, room=21.0, sp=21.0)
    hass.states.async_set(
        "sensor.room_rh",
        "54",
        {"device_class": "humidity", "unit_of_measurement": "%"},
    )
    data = {**ROOM_DATA, CONF_HUMIDITY_SENSOR: "sensor.room_rh"}
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    reg = er.async_get(hass)
    climate_eid = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(reg, entry.entry_id)
        if e.domain == "climate"
    )
    state = hass.states.get(climate_eid)
    assert state is not None
    assert state.attributes.get("current_humidity") == 54.0
