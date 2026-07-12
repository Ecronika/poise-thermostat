"""Review F8: a ``person``/``device_tracker`` reporting a named zone ("Work",
"Gym", ...) is a resolved, confident "not home" -- not a sensor failure.

``_tristate()`` previously fell through to ``None`` (unresolved) for any state
other than the literal home/not_home/on/off/true/false/away tokens, and
``any_present``'s fail-safe (unresolved -> present, so a dead tracker never
closes the house gate) then misread a person *confirmed* to be away at a
custom zone as still "home" -- the opposite of the fail-safe philosophy the
resolver documents (a genuinely unresolved state should fail toward present;
a genuinely resolved "elsewhere" state should not).
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
    DOMAIN,
)


def _data() -> dict[str, Any]:
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
    }


def _warm_room(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "29",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("sensor.outdoor", "20", {"device_class": "temperature"})
    hass.states.async_set("sensor.trm", "22", {"device_class": "temperature"})
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


async def test_person_at_named_zone_resolves_away_not_fail_safe_present(
    hass: HomeAssistant,
) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _warm_room(hass)
    # a person integration reports the zone *name* as state when the tracked
    # person is in a custom (non-home) zone -- a resolved location, not a
    # dropout.
    hass.states.async_set("person.someone", "Work")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_data(),
        options={CONF_PRESENCE_HOME: "person.someone"},
        title="Office",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coord: Any = entry.runtime_data
    assert coord.data is not None
    assert coord.data.get("presence_level") == "away"
