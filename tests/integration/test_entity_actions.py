"""Entity-driven glue tests: climate/switch services, override clamp, persistence.

These drive the integration the way a user (or the card) does — through the
climate and switch entity services — and assert the coordinator reacts and,
where relevant, the configured actuator is (or is not) written.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DEVICE_MAX_C,
    DOMAIN,
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


def _states(hass: HomeAssistant, *, room: float = 19.0, sp: float = 15.0) -> None:
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


async def _setup_zone(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str) -> str:
    reg = er.async_get(hass)
    for e in er.async_entries_for_config_entry(reg, entry.entry_id):
        if e.domain == domain:
            return e.entity_id
    raise AssertionError(f"no {domain} entity for entry")


async def test_set_preset_mode_via_service(hass: HomeAssistant) -> None:
    """climate.set_preset_mode flows through to the coordinator + entity attr."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass)
    eid = _entity_id(hass, entry, "climate")

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {ATTR_ENTITY_ID: eid, "preset_mode": "eco"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert entry.runtime_data.preset.value == "eco"
    assert hass.states.get(eid).attributes["preset_mode"] == "eco"


async def test_window_bypass_switch_toggles(hass: HomeAssistant) -> None:
    """The bypass switch flips the coordinator's window_bypass flag."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass)
    switch_eid = _entity_id(hass, entry, "switch")

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: switch_eid}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.window_bypass is True

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: switch_eid}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.window_bypass is False


async def test_override_is_clamped_to_device_max(hass: HomeAssistant) -> None:
    """An absurd override is clamped into the envelope before the actuator (C2)."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=18.0, sp=15.0)
    entry = await _setup_zone(hass)

    entry.runtime_data.set_override(50.0)  # far above the device maximum
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert set_temp, "no actuator write after override"
    assert set_temp[-1].data["temperature"] <= DEVICE_MAX_C
    assert set_temp[-1].data["temperature"] != 50.0


async def test_disabled_skips_actuator_write(hass: HomeAssistant) -> None:
    """When disabled the live tick must not write to the actuator."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=18.0, sp=15.0)
    entry = await _setup_zone(hass)
    eid = _entity_id(hass, entry, "climate")

    before = len(set_temp)
    entry.runtime_data.set_enabled(False)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert len(set_temp) == before  # no further writes while disabled
    assert hass.states.get(eid).state == "off"


async def test_reload_preserves_override(hass: HomeAssistant) -> None:
    """Override survives an entry reload via the persisted store (C5 area)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass)

    entry.runtime_data.set_override(23.0)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data._override == 23.0


async def test_climate_exposes_comfort_band_attributes(hass: HomeAssistant) -> None:
    """The climate entity surfaces the EN 16798 comfort band for the card."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass)
    attrs = hass.states.get(_entity_id(hass, entry, "climate")).attributes

    assert attrs.get("comfort_low") is not None
    assert attrs.get("comfort_high") is not None
    assert attrs["comfort_low"] < attrs["comfort_high"]
