"""Review degradation glue (P3-18): an actuator dropping out then recovering
resumes writes, and a humidity sensor drop-out surfaces the
``mould_protection_inactive`` repair issue (mould protection silently disabled).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
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
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)


def _room_data(**extra: Any) -> dict[str, Any]:
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


def _actuator(hass: HomeAssistant, *, sp: float, room: float) -> None:
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


async def _setup(hass: HomeAssistant, *, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_p3_18a_actuator_dropout_then_recovery_resumes_writes(
    hass: HomeAssistant,
) -> None:
    """P3-18(a): an actuator going unavailable is not written to; once it comes
    back the coordinator resumes writing setpoints to it."""
    hass.states.async_set(
        "sensor.room_temp",
        "18.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    _actuator(hass, sp=10.0, room=18.0)  # parked low -> a write is due
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    # the device drops off the network.
    hass.states.async_set("climate.trv", "unavailable", {})
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    for _ in range(2):
        await coord.async_refresh()
        await hass.async_block_till_done()
    assert not set_temp, "a dead actuator must not be written to"

    # the device recovers -> writes resume.
    _actuator(hass, sp=10.0, room=18.0)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert set_temp, "writes must resume once the actuator is back"
    assert set_temp[-1].data["entity_id"] == "climate.trv"


async def test_p3_18b_humidity_dropout_disables_mould_protection(
    hass: HomeAssistant,
) -> None:
    """P3-18(b): a configured humidity sensor dropping out (no RH -> no mould
    floor) raises ``mould_protection_inactive``, which clears on recovery."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(
        "sensor.room_temp",
        "21.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "sensor.room_rh",
        "60",
        {"device_class": "humidity", "unit_of_measurement": "%"},
    )
    _actuator(hass, sp=21.0, room=21.0)
    entry = await _setup(
        hass, data=_room_data(**{CONF_HUMIDITY_SENSOR: "sensor.room_rh"})
    )
    coord: Any = entry.runtime_data
    issue_id = f"mould_protection_inactive_{entry.entry_id}"

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    # the humidity sensor drops off -> mould protection can't compute a floor.
    hass.states.async_set("sensor.room_rh", "unavailable", {})
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # recovery clears the issue.
    hass.states.async_set(
        "sensor.room_rh",
        "60",
        {"device_class": "humidity", "unit_of_measurement": "%"},
    )
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
