"""Review F3 regression: an implausible raw room-temperature sample must
degrade down the ADR-0012 ladder (measured -> derived -> default), not skip
straight past the "derived" rung to the hardcoded 20.0 °C default -- and a
non-measured reading must never be fed to the EKF as if it were a real
observation of the thermal plant (ADR-0012 / ADR-0026).

Previously ``_run_once`` called ``ingest_temperature([RawSample(air, now)],
now=now)`` with no ``last_good``, so ANY implausible raw sample (a Zigbee
glitch, a misread °F number, ...) fell all the way to the ``default`` rung
even with a perfectly good previous reading on hand, and that fabricated
20.0 °C constant was then both regulated on and taught to the EKF as if the
room had truly stopped moving.
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
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
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


def _actuator(hass: HomeAssistant, *, sp: float = 19.0, room: float = 18.0) -> None:
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


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ekf_updates(coord: Any) -> int:
    ekf = coord._ekf
    return ekf.n_idle + ekf.n_heating + ekf.n_cooling


async def test_implausible_sample_derives_from_last_good_and_is_not_learned(
    hass: HomeAssistant,
) -> None:
    _actuator(hass, sp=19.0, room=18.0)
    entry = await _setup(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data

    # two good ticks: anchor _prev_room and let the EKF take at least one real
    # predict/update step.
    await coord.async_refresh()
    await hass.async_block_till_done()
    await coord.async_refresh()
    await hass.async_block_till_done()

    updates_before = _ekf_updates(coord)
    assert coord.data is not None
    assert coord.data["current_temperature"] == 18.0

    # a glitchy raw sample, e.g. a misread °F number reported as °C -- well
    # outside TEMP_PLAUSIBLE_MIN_C/MAX_C.
    hass.states.async_set(
        "sensor.room_temp",
        "500",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    await coord.async_refresh()
    await hass.async_block_till_done()

    # derived rung: falls back to the last known-good reading, not the
    # hardcoded 20.0 °C default.
    assert coord.data["current_temperature"] == 18.0
    # the fabricated/derived sample must not be taught to the EKF as a real
    # observation of the thermal plant.
    assert _ekf_updates(coord) == updates_before


async def test_implausible_sample_with_no_history_hits_default_rung(
    hass: HomeAssistant,
) -> None:
    # implausible from the very first tick: no last-good value exists yet, so
    # the ladder has nowhere to derive from and must fall all the way to the
    # reasoned default -- which is then flagged as untrustworthy, per F3.
    _actuator(hass, sp=19.0, room=18.0)
    hass.states.async_set(
        "sensor.room_temp",
        "-999",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    entry = await _setup(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data is not None
    assert coord.data["current_temperature"] == 20.0
    # a DEFAULT-source reading must never be learned from.
    assert _ekf_updates(coord) == 0
