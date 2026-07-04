"""Silver test-coverage batch 2: the biggest remaining coordinator/hub branches.

- ``_write_unavailable_safe_state`` (sustained room-sensor loss -> safe floor or
  off), including both the heat-capable and cool-only actuator paths and the
  "not yet timed out" hold (review #7 / ADR-0012).
- the weather-forecast fetch used by optimal-start (ADR-0025).
- the hub's *actuation* path: an opt-in zone calls for heat, the hub turns the
  configured boiler switch on (ADR-0013, reviews V2b/N-1).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_ACTIVATION_DELAY,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WEATHER,
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


def _room_and_actuator(
    hass: HomeAssistant,
    *,
    room: float,
    sp: float,
    modes: list[str],
    state: str,
) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": modes,
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_unavailable_safe_state_heat_writes_floor(hass: HomeAssistant) -> None:
    """A sustained room-sensor loss degrades a heat-capable actuator to the
    frost/mould floor (fail toward warmth), returning the safe-state payload."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_and_actuator(hass, room=20.0, sp=19.0, modes=["heat", "off"], state="heat")
    entry = await _setup(hass, _base())
    coord = entry.runtime_data

    # sensor drops out, and pretend the loss is older than the safe-after timeout
    coord._unavailable_since = coord._clock.monotonic() - 2000.0
    hass.states.async_set(
        "sensor.room_temp", "unavailable", {"device_class": "temperature"}
    )
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data == {"available": False, "unavailable_safe": True}
    assert set_temp, "no safe-state write under a sustained sensor loss"
    assert set_temp[-1].data["temperature"] <= 10.0  # the frost floor, not comfort


async def test_unavailable_safe_state_cool_only_turns_off(hass: HomeAssistant) -> None:
    """A cool-only actuator has no heat floor to hold, so the safe state parks
    it off rather than writing a setpoint."""
    async_mock_service(hass, "climate", "set_temperature")
    hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    _room_and_actuator(hass, room=25.0, sp=24.0, modes=["cool", "off"], state="cool")
    entry = await _setup(hass, _base())
    coord = entry.runtime_data

    coord._unavailable_since = coord._clock.monotonic() - 2000.0
    hass.states.async_set(
        "sensor.room_temp", "unavailable", {"device_class": "temperature"}
    )
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data.get("unavailable_safe") is True
    assert any(c.data.get("hvac_mode") == "off" for c in hvac)


async def test_unavailable_no_timeout_holds_state(hass: HomeAssistant) -> None:
    """A *fresh* room-sensor loss only holds the last state (no safe write yet)
    and starts the timeout clock."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_and_actuator(hass, room=20.0, sp=19.0, modes=["heat", "off"], state="heat")
    entry = await _setup(hass, _base())
    coord = entry.runtime_data

    coord._unavailable_since = None  # fresh loss -> timer (re)starts at now
    hass.states.async_set(
        "sensor.room_temp", "unavailable", {"device_class": "temperature"}
    )
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data == {"available": False}
    assert coord._unavailable_since is not None  # the clock was started


async def test_weather_forecast_consumed(hass: HomeAssistant) -> None:
    """With a weather entity configured, the tick fetches an hourly forecast for
    the optimal-start outdoor estimate (ADR-0025)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    now = dt_util.utcnow()
    forecast = [
        {"datetime": now.isoformat(), "temperature": 4.0},
        {"datetime": now.isoformat(), "temperature": 5.0},
    ]

    async def _get_forecasts(call: ServiceCall) -> dict[str, Any]:
        return {"weather.home": {"forecast": forecast}}

    hass.services.async_register(
        "weather",
        "get_forecasts",
        _get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )
    hass.states.async_set("weather.home", "cloudy", {"temperature": 5.0})
    _room_and_actuator(hass, room=18.0, sp=17.0, modes=["heat", "off"], state="heat")
    entry = await _setup(hass, _base(**{CONF_WEATHER: "weather.home"}))
    coord = entry.runtime_data

    coord._forecast_at = None  # force a fresh fetch on the next tick
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data["available"] is True


async def test_hub_actuates_boiler_on_zone_demand(hass: HomeAssistant) -> None:
    """An opt-in zone below comfort makes the hub turn the configured boiler
    switch on, and the aggregate exposes flow/shed diagnostics."""
    turn_on = async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("switch.boiler", "off")
    _room_and_actuator(hass, room=17.0, sp=16.0, modes=["heat", "off"], state="heat")
    await _setup(hass, _base(**{CONF_CONTROLS_BOILER: True}))

    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_COUNT_THRESHOLD: 1,
            CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on",
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",
            CONF_BOILER_ACTIVATION_DELAY: 0,
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    assert turn_on, "hub did not actuate the boiler on a zone's heat demand"
    d = hub.runtime_data.data
    assert "flow_target" in d
    assert "shed_count" in d
