"""Review V1 (KRITISCH): an open window (or frozen sensor) must never leave a
cooling device in ``cool`` with the frost floor as its setpoint — that would run
the compressor at full load down to ~7 C. A heat-capable device is nudged to
``heat`` (holds the frost floor, idles); a cool-only device is turned ``off``.
Glue, CI-only.
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
    CONF_WINDOW_SENSOR,
    DOMAIN,
)


def _data(actuator: str) -> dict[str, Any]:
    return {
        CONF_NAME: "Zone",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: actuator,
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_WINDOW_SENSOR: "binary_sensor.window",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: True,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
    }


def _hot_open(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "27", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "30", {"device_class": "temperature"})
    hass.states.async_set("sensor.trm", "26", {"device_class": "temperature"})
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})


async def test_window_reversible_ac_nudged_out_of_cool(hass: HomeAssistant) -> None:
    """Reversible AC cooling + open window -> nudged to heat (NOT kept cooling)."""
    async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    _hot_open(hass)
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "heat", "off"],
            "temperature": 24.0,
            "current_temperature": 27.0,
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

    modes = [c.data.get("hvac_mode") for c in set_mode]
    assert "heat" in modes, "reversible AC must be nudged to heat on open window"
    assert "cool" not in modes, "must NOT keep/assert cool while the window is open"


async def test_window_cool_only_ac_turned_off(hass: HomeAssistant) -> None:
    """A cool-only AC + open window -> commanded off (never cool to the floor)."""
    async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    _hot_open(hass)
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "off"],
            "temperature": 24.0,
            "current_temperature": 27.0,
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

    modes = [c.data.get("hvac_mode") for c in set_mode]
    assert "off" in modes, "cool-only AC must be turned off on open window"
    assert "cool" not in modes, "must never re-assert cool while the window is open"
