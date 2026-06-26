"""Integration tests pinning the P0 fixes from the external v0.83 review.

H1 — a cooling-capable actuator must be nudged into ``cool`` (not ``heat``) and
     receive the cool setpoint when Poise decides to cool.
H3 — the system hub must drop a zone whose coordinator's last update failed
     (``last_update_success`` is False) instead of calling for heat on stale data.
H2 — with an identified model and optimal-stop enabled, the comfort-phase coast
     branch is reachable (a model is built during comfort, not only during setback).
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
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)


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


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --------------------------------------------------------------------------- H1
async def test_cooling_nudges_cool_not_heat(hass: HomeAssistant) -> None:
    """H1: when Poise cools, it commands set_hvac_mode('cool'), never 'heat'."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    # hot room + warm outside (clears the cool>=16 °C outdoor lockout) + a
    # cool-capable TRV left in 'off' so the mode nudge fires.
    hass.states.async_set("sensor.room_temp", "33.0", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "30.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "off",
        {
            "hvac_modes": ["heat", "cool", "off"],
            "temperature": 24.0,
            "current_temperature": 33.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 35,
        },
    )
    await _setup(
        hass,
        _base(
            **{CONF_CLIMATE_MODE: "cool_only", CONF_OUTDOOR_SENSOR: "sensor.outdoor"}
        ),
    )

    cool_nudges = [c for c in set_hvac if c.data.get("hvac_mode") == "cool"]
    heat_nudges = [c for c in set_hvac if c.data.get("hvac_mode") == "heat"]
    assert cool_nudges, "cooling did not nudge the actuator into 'cool'"
    assert not heat_nudges, "cooling wrongly nudged the actuator into 'heat'"
    assert set_temp, "no setpoint written while cooling"
    # the cool setpoint is below the hot room, not floored up to a heat target
    assert set_temp[-1].data["temperature"] < 33.0


# --------------------------------------------------------------------------- H3
async def test_hub_drops_zone_with_failed_update(hass: HomeAssistant) -> None:
    """H3: a zone whose last coordinator update failed is excluded from the hub."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "16.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 16.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    zone = await _setup(hass, _base(**{CONF_CONTROLS_BOILER: True}))

    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    # cold room → the healthy zone calls for heat and the hub counts it
    await hub.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hub.runtime_data.data["controlling_zones"] >= 1

    # now the zone's coordinator update fails (sensor/actuator glitch): the hub
    # must NOT keep calling for heat on the stale snapshot
    zone.runtime_data.last_update_success = False
    await hub.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hub.runtime_data.data["controlling_zones"] == 0


# --------------------------------------------------------------------------- H2
async def test_optimal_stop_coast_reachable_in_comfort(hass: HomeAssistant) -> None:
    """H2: an identified EKF builds a model during comfort, enabling the coast path.

    Before the fix the model was only built during setback, so the comfort-phase
    coast branch (optimal-stop) was dead. We force identification and assert the
    coordinator computes a coast decision (``coasting`` present) without error.
    """
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "22.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 22.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = await _setup(hass, _base())
    coord = entry.runtime_data

    # force the EKF past its identification gate (as the closed-loop harness does)
    ekf = coord._ekf
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.p[0][0] = 0.01
    assert ekf.identified is True

    await coord.async_refresh()
    await hass.async_block_till_done()

    # the comfort tick reached the coast logic and produced a boolean decision
    assert coord.data.get("coasting") in (True, False)
    assert coord.data.get("available") is True
