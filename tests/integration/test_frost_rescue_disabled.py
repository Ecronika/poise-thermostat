"""Review V4: even DISABLED, a zone keeps the unconditional frost/mould floor —
but rescue-only, so a reasonable manual setpoint above the floor is never fought,
and a cool-only device (no frost duty) is left alone. Glue, CI-only.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
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
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)


def _data(actuator: str) -> dict[str, Any]:
    return {
        CONF_NAME: "Zone",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: actuator,
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: True,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
    }


def _cold(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "5", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "-2", {"device_class": "temperature"})
    hass.states.async_set("sensor.trm", "3", {"device_class": "temperature"})


async def _disable_and_tick(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coord: Any = entry.runtime_data
    coord.set_enabled(False)
    await coord.async_refresh()
    await hass.async_block_till_done()


async def test_disabled_heat_device_below_floor_gets_frost_rescue(
    hass: HomeAssistant,
) -> None:
    """Disabled zone, heat-capable device below the floor -> floor written and
    nudged to heat (the README 'unconditional safety floor' promise)."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    _cold(hass)
    hass.states.async_set(
        "climate.trv",
        "off",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 5.0,
            "current_temperature": 5.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_data("climate.trv"), title="Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    set_temp.clear()
    set_mode.clear()

    await _disable_and_tick(hass, entry)

    modes = [c.data.get("hvac_mode") for c in set_mode]
    assert set_temp, "disabled zone must still rescue a device below the frost floor"
    assert all(c.data.get("temperature") >= 7.0 for c in set_temp)
    assert "heat" in modes, "frost rescue must nudge the device into heat"


async def test_disabled_reasonable_setpoint_not_fought(hass: HomeAssistant) -> None:
    """Disabled zone with a sane manual setpoint above the floor -> hands-off."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _cold(hass)
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 19.0,
            "current_temperature": 18.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_data("climate.trv"), title="Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    set_temp.clear()

    await _disable_and_tick(hass, entry)

    assert not set_temp, "a reasonable setpoint above the floor must not be overwritten"


async def test_disabled_cool_only_device_left_alone(hass: HomeAssistant) -> None:
    """Disabled zone, cool-only device below the floor -> no frost duty, no write."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _cold(hass)
    hass.states.async_set(
        "climate.ac",
        "off",
        {
            "hvac_modes": ["cool", "off"],
            "temperature": 5.0,
            "current_temperature": 5.0,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=_data("climate.ac"), title="Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    set_temp.clear()

    await _disable_and_tick(hass, entry)

    assert not set_temp, "a cool-only device has no frost duty when disabled"
