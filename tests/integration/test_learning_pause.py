"""Review V5: while learning is paused (open window / frozen sensor) the EKF and
seasonless time anchors are dropped, so the first learning step after resumption
re-anchors from that tick instead of integrating the whole contaminated interval
(a short Stoßlüften would otherwise poison the model). Glue, CI-only.

Socket-safe ROOM_DATA config (no outdoor / TRM) so the multi-refresh stays offline.
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
    CONF_WINDOW_SENSOR,
    DOMAIN,
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
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


def _states(hass: HomeAssistant, *, room: float, sp: float) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
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


async def test_open_window_drops_learning_anchor(hass: HomeAssistant) -> None:
    """Open window pauses learning -> EKF + seasonless time anchors are dropped, so
    the resumed step cannot integrate the ventilation interval as its dt (V5)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=18.0, sp=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # a learning tick with the window closed anchors both clocks
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._last_mono is not None
    assert coord._prev_room_mono is not None

    # window opens -> learning paused -> both anchors dropped (no contaminated dt)
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._last_mono is None
    assert coord._prev_room_mono is None
