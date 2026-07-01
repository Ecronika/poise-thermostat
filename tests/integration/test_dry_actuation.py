"""ADR-0050 S2c: the live dry mode-nudge (glue, CI-only).

A humid room sitting in the comfort dead-band on a dry-capable AC must be nudged
into ``dry``; a heat-only TRV (no ``dry`` mode) must never be — the capability
gate makes drying a no-op there.
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
    CONF_HUMIDITY_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)

_SENSORS = {
    "sensor.room_temp": ("22", {"device_class": "temperature"}),
    "sensor.rh": ("70", {"device_class": "humidity"}),
    "sensor.outdoor": ("18", {"device_class": "temperature"}),
    "sensor.trm": ("20", {"device_class": "temperature"}),
}


def _base_data(actuator: str) -> dict[str, Any]:
    return {
        CONF_NAME: "Zone",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: actuator,
        CONF_HUMIDITY_SENSOR: "sensor.rh",
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


async def test_dry_nudge_when_humid_and_idle(hass: HomeAssistant) -> None:
    """Room in the dead-band + high RH + a dry-capable AC -> set_hvac_mode(dry)."""
    async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    for eid, (state, attrs) in _SENSORS.items():
        hass.states.async_set(eid, state, attrs)
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "heat", "dry", "off"],
            "temperature": 24.0,
            "current_temperature": 22.0,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_base_data("climate.ac"),
        title="Zone",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    dry = [c for c in set_mode if c.data.get("hvac_mode") == "dry"]
    assert dry, "expected a set_hvac_mode('dry') nudge for the humid idle room"


async def test_no_dry_on_heat_only_device(hass: HomeAssistant) -> None:
    """A heat-only TRV (no 'dry' mode) never gets a dry nudge (capability gate)."""
    async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    for eid, (state, attrs) in _SENSORS.items():
        hass.states.async_set(eid, state, attrs)
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 22.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=_base_data("climate.trv"),
        title="Zone",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    dry = [c for c in set_mode if c.data.get("hvac_mode") == "dry"]
    assert not dry, "a heat-only TRV must never be nudged into dry"
