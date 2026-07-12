"""Review F4a/F4b: a configured window sensor that drops off
(unavailable/unknown) must not be silently read as "closed" forever. Per
ADR-0041 §5 the failsafe is "heizen wie ohne Sensor" (fall back to the
slope/auto detector) plus a repair issue -- while a *healthy* sensor still
takes exclusive precedence over the heuristic (ADR-0041 §2, unchanged).

Previously ``_window_open()`` could not distinguish "unavailable" from
"closed" (neither is ``state == "on"``), so a dead window contact silently
pinned the zone to "window closed" forever with no signal and no warning --
and ``_observe_window_auto`` unconditionally skipped itself whenever a
sensor was configured, so there was no fallback signal to fail over to even
if the coordinator had noticed.
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
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
)
from custom_components.poise.control.window_auto import WindowAutoState

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


def _states(
    hass: HomeAssistant, *, room: float, sp: float, window_state: str = "off"
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    attrs = {} if window_state == "unavailable" else {"device_class": "window"}
    hass.states.async_set("binary_sensor.window", window_state, attrs)
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


async def test_healthy_sensor_keeps_slope_detector_cold(hass: HomeAssistant) -> None:
    """ADR-0041 §2 exclusivity: with a reporting sensor, the heuristic stays
    off (sensor beats heuristic) -- unchanged by the F4a/F4b failsafe fix."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=18.0, sp=20.0, window_state="off")
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    await coord.async_refresh()
    await hass.async_block_till_done()
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._wa_prev_mono is None
    issue_id = f"window_sensor_unavailable_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_unavailable_sensor_raises_issue_and_falls_back_to_slope(
    hass: HomeAssistant,
) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=18.0, sp=20.0, window_state="off")
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    issue_id = f"window_sensor_unavailable_{entry.entry_id}"

    # sensor drops off the network.
    hass.states.async_set("binary_sensor.window", "unavailable", {})
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    # the slope/auto detector is now the only signal available and must be
    # live (F4b), not permanently skipped just because a sensor is configured.
    assert coord._wa_prev_mono is not None
    # a dead sensor never reports "on" -> effective_window_open falls through
    # entirely to the (freshly-seeded, not-yet-triggered) auto signal, so the
    # zone is not incorrectly force-closed nor force-opened by the dropout
    # itself.
    assert coord.data is not None
    assert coord.data["window_open"] is False

    # sensor recovers -> issue clears, exclusivity resumes.
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_recovered_sensor_clears_a_latched_auto_open(
    hass: HomeAssistant,
) -> None:
    """F4b follow-up: an ``open=True`` latched by the slope detector during a
    PRIOR sensor dropout (the §5 failsafe) must not survive the sensor coming
    back healthy -- ``_observe_window_auto`` stops stepping once a configured
    sensor reports again, so ``step_window_auto``'s own anti-stick timer never
    gets another chance to fire; left alone, ``effective_window_open``'s OR
    would pin the room "window open" forever even though the real, healthy
    sensor correctly reports closed."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=18.0, sp=20.0, window_state="off")
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # simulate a slope-detected "open" latched while the sensor was previously
    # unavailable (rather than relying on many ticks of a real temperature
    # drop to trigger it organically).
    coord._window_auto = WindowAutoState(
        ema_slope=10.0, n_points=5, open=True, minutes_open=12.0
    )

    # the sensor is healthy and reports closed.
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data is not None
    assert coord.data["window_open"] is False, (
        "a stale auto-detected open must not outlive a healthy, closed sensor"
    )
    assert coord._window_auto.open is False
    assert coord.data["window_auto_detected"] is False
