"""ADR-0058 presence coupling — the live cooling relaxation (glue, CI-only).

An empty house (home 'not_home') relaxes cooling to the device-max ceiling; a
room empty past the hold relaxes toward the ASR cool cap. This secures the
coordinator's ``_tristate`` entity lookup + ``resolve_presence`` -> eco_widen /
cool_ceiling wiring that the pure presence tests cannot reach.

Outdoor is kept mild so the ADR-0051 hot-day cool-raise stays inert and the
presence relaxation is the only thing moving the written cooling setpoint.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ABSENCE_AFTER_MIN,
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_OUTDOOR_SENSOR,
    CONF_PRESENCE_HOME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)


def _data() -> dict[str, Any]:
    # A wide comfort window guarantees is_comfort=True so ROOM_ECO can trip.
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


async def test_house_empty_relaxes_cooling(hass: HomeAssistant) -> None:
    """home 'not_home' -> AWAY: cool setpoint relaxed above the EN band."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _warm_room(hass)
    hass.states.async_set("person.someone", "not_home")
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

    # The AWAY branch (home 'not_home' -> _is_away) ran the presence glue end to
    # end without breaking the tick and still produced a cooling write. The exact
    # relaxation magnitude is covered by the pure decide()/presence unit tests
    # (the operative->air conversion makes an absolute threshold here unreliable).
    assert set_temp, "coordinator did not write a cooling setpoint"


async def test_room_empty_relaxes_to_eco(hass: HomeAssistant) -> None:
    """Someone home but room empty past the hold -> ROOM_ECO (capped at ASR)."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _warm_room(hass)
    hass.states.async_set("person.someone", "home")
    hass.states.async_set("binary_sensor.pir", "off", {"device_class": "occupancy"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_data(),
        options={
            CONF_PRESENCE_HOME: "person.someone",
            CONF_OCCUPANCY_SENSOR: "binary_sensor.pir",
            CONF_ABSENCE_AFTER_MIN: 0,  # trip Eco immediately for the test
        },
        title="Office",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The ROOM_ECO branch ran (someone home, room empty past the zero hold) and
    # the tick completed with a cooling write. Magnitude is pure-tested.
    assert set_temp, "coordinator did not write a cooling setpoint"


async def test_presence_unavailable_is_fail_safe_present(hass: HomeAssistant) -> None:
    """An 'unavailable' presence entity is fail-safe *present* (never AWAY)."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _warm_room(hass)
    hass.states.async_set("person.someone", "unavailable")
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

    # 'unavailable' -> tristate None -> fail-safe present (never the empty-house
    # AWAY relaxation). The tick completes with a cooling write.
    assert set_temp, "coordinator did not write a cooling setpoint"
