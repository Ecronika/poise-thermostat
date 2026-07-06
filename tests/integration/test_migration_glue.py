"""V1 -> V2 config-entry store migration, end to end (glue, CI-only).

An old V1 entry (everything in ``data``, single-id pickers) must migrate on setup
to the V2 split (structural ``data`` + hot-applyable ``options``) with the
window/presence/occupancy ids normalized to lists — and the coordinator must then
read that list-form presence without breaking the tick. Outdoor is mild so the
ADR-0051 hot-day cool-raise stays inert; the empty-house (person 'not_home') AWAY
relaxation is the only thing moving the written cooling setpoint.
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
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_NAME,
    CONF_OUTDOOR_SENSOR,
    CONF_PRESENCE_HOME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
)


def _v1_data() -> dict[str, Any]:
    # V1 layout: every field lived in entry.data and the pickers were single ids.
    # A wide comfort window guarantees is_comfort=True.
    return {
        CONF_NAME: "Office",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_START: "00:00:00",
        CONF_COMFORT_END: "23:59:00",
        CONF_SETBACK_DELTA: 3.0,
        CONF_PRESENCE_HOME: "person.a",  # single id -> list on migrate
        CONF_WINDOW_SENSOR: "binary_sensor.win",  # single id -> list on migrate
    }


def _warm_room(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "29",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("sensor.outdoor", "20", {"device_class": "temperature"})
    hass.states.async_set("sensor.trm", "22", {"device_class": "temperature"})
    hass.states.async_set("binary_sensor.win", "off", {"device_class": "window"})
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "heat", "off"],
            "temperature": 24.0,
            "current_temperature": 29.0,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )


async def test_v1_entry_migrates_and_runs_list_presence(hass: HomeAssistant) -> None:
    """A V1 entry migrates to the V2 split; the tick reads the list-form presence."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _warm_room(hass)
    hass.states.async_set("person.a", "not_home")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_v1_data(),
        version=1,
        title="Office",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # migrated to V2
    assert entry.version == 2
    # tuning moved out of data into options; structural inputs stayed in data
    assert CONF_COMFORT_BASE not in entry.data
    assert entry.options[CONF_COMFORT_BASE] == 21.0
    assert CONF_TEMP_SENSOR in entry.data
    # single-id pickers normalized to one-element lists
    assert entry.options[CONF_PRESENCE_HOME] == ["person.a"]  # hot-applied set
    assert entry.data[CONF_WINDOW_SENSOR] == ["binary_sensor.win"]  # structural set
    # the coordinator read the list-form presence: person 'not_home' -> AWAY
    # relaxation wrote a cooling setpoint without breaking the tick.
    assert set_temp, "coordinator did not write a cooling setpoint after migration"
