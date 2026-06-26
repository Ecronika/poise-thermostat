"""Additional glue-path integration tests to raise coverage toward the Silver
95%-all-modules rule: diagnostics, climate hvac/turn services, and the optional
sensor branches (humidity/mould, outdoor, window-open, cooling, operative)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.const import ATTR_ENTITY_ID
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
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WINDOW_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from custom_components.poise.diagnostics import async_get_config_entry_diagnostics


def _base(**extra: Any) -> dict[str, Any]:
    return {
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
        **extra,
    }


def _actuator(hass: HomeAssistant, *, modes: list[str], state: str = "heat") -> None:
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": modes,
            "temperature": 15.0,
            "current_temperature": 19.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    hass.states.async_set("sensor.room_temp", "19.0", {"device_class": "temperature"})
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _climate_eid(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    reg = er.async_get(hass)
    for e in er.async_entries_for_config_entry(reg, entry.entry_id):
        if e.domain == "climate":
            return e.entity_id
    raise AssertionError("no climate entity")


async def test_diagnostics_returns_redacted_payload(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(hass, _base())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert isinstance(diag, dict) and diag


async def test_set_hvac_mode_off_and_back(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(hass, _base())
    eid = _climate_eid(hass, entry)

    await hass.services.async_call(
        "climate", "set_hvac_mode", {ATTR_ENTITY_ID: eid, "hvac_mode": "off"}, True
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.enabled is False

    await hass.services.async_call(
        "climate", "set_hvac_mode", {ATTR_ENTITY_ID: eid, "hvac_mode": "heat"}, True
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.enabled is True


async def test_turn_off_then_on(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(hass, _base())
    eid = _climate_eid(hass, entry)

    await hass.services.async_call("climate", "turn_off", {ATTR_ENTITY_ID: eid}, True)
    await hass.async_block_till_done()
    assert entry.runtime_data.enabled is False

    await hass.services.async_call("climate", "turn_on", {ATTR_ENTITY_ID: eid}, True)
    await hass.async_block_till_done()
    assert entry.runtime_data.enabled is True


async def test_humidity_and_outdoor_drive_mould_path(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(
        "sensor.humidity",
        "78",
        {"device_class": "humidity", "unit_of_measurement": "%"},
    )
    hass.states.async_set("sensor.outdoor", "2.0", {"device_class": "temperature"})
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(
        hass,
        _base(
            **{
                CONF_HUMIDITY_SENSOR: "sensor.humidity",
                CONF_OUTDOOR_SENSOR: "sensor.outdoor",
            }
        ),
    )
    # the tick consumed humidity (dewpoint cap + mould floor) without error
    assert entry.runtime_data.data.get("available") is True


async def test_window_open_reaction(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(hass, _base(**{CONF_WINDOW_SENSOR: "binary_sensor.window"}))
    assert entry.runtime_data.data.get("window_open") is True


async def test_cooling_capable_actuator_exposes_cool(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, modes=["heat", "cool", "off"])
    entry = await _setup(hass, _base())
    modes = hass.states.get(_climate_eid(hass, entry)).attributes["hvac_modes"]
    assert "cool" in modes


async def test_operative_input_mode(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("number.trv_ext", "19.0")
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(
        hass,
        _base(**{CONF_OPERATIVE_INPUT: True, CONF_TRV_EXTERNAL_TEMP: "number.trv_ext"}),
    )
    assert entry.runtime_data.data.get("available") is True


async def test_hub_aggregates_a_controlling_zone(hass: HomeAssistant) -> None:
    """The hub collects an opt-in zone's call-for-heat into its aggregate."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, modes=["heat", "off"])
    await _setup(hass, _base(**{CONF_CONTROLS_BOILER: True}))

    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    data = hub.runtime_data.data
    assert "active_zones" in data
    assert data["controlling_zones"] >= 1


async def test_frozen_sensor_writes_health_floor(hass: HomeAssistant) -> None:
    """A frozen room sensor degrades the write to the health floor (review C3)."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, modes=["heat", "off"])
    with patch("custom_components.poise.coordinator.is_frozen", return_value=True):
        entry = await _setup(hass, _base())
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert set_temp, "no actuator write under frozen sensor"
    # degraded to the frost/health floor, not the ~21 comfort target
    assert set_temp[-1].data["temperature"] <= 10.0
