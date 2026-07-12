"""Review F5: a fully unavailable room sensor must drop the same
learning/window-auto anchors as the existing open-window/frozen-sensor pause
(V5) -- otherwise the eventual reconnect re-anchors across the whole outage
and the EKF (or the slope-based window-auto detector) integrates a
real-looking interval it never actually observed.

Previously the ``air is None`` early return in ``_run_once`` skipped straight
to ``{"available": False}`` without touching ``_last_mono``, ``_prev_room``,
``_prev_room_mono``, ``_heatup_acc``, or the window-auto ``_wa_*`` anchors, so
a multi-tick sensor dropout was invisible to every one of those pause
mechanisms even though it is at least as untrustworthy as an open window.
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


async def test_sensor_dropout_drops_learning_and_window_auto_anchors(
    hass: HomeAssistant,
) -> None:
    _actuator(hass, sp=19.0, room=18.0)
    entry = await _setup(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data

    # two good ticks: anchor both the EKF/seasonless clock and the window-auto
    # slope reference point.
    await coord.async_refresh()
    await hass.async_block_till_done()
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._last_mono is not None
    assert coord._prev_room_mono is not None
    assert coord._wa_ref_mono is not None
    assert coord._wa_prev_mono is not None

    # the room sensor drops off the network entirely.
    hass.states.async_set("sensor.room_temp", "unavailable", {})
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data is not None
    assert coord.data.get("available") is False
    assert coord._last_mono is None
    assert coord._prev_room is None
    assert coord._prev_room_mono is None
    assert coord._wa_ref_room is None
    assert coord._wa_ref_mono is None
    assert coord._wa_prev_mono is None
