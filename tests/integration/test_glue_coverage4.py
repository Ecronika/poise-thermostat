"""Silver test-coverage batch 4: the remaining reachable glue clusters.

- ``__init__`` entry lifecycle: deleting the system hub switches its boiler off
  (review V2b), the zone/no-action/failure variants, and the card-registration
  guard that must never block setup (ADR-0040).
- the coordinator's weather-forecast fetch used by optimal-start (ADR-0025) and
  its degrade-to-fallback path.
- the small scalar read helpers (sensor age / capability / device-max / sun
  elevation) that a fresh tick does not otherwise reach.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise import async_remove_entry, async_setup
from custom_components.poise.const import (
    CONF_ACTUATOR,
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


def _actuator(hass: HomeAssistant, *, modes: list[str], state: str = "heat") -> None:
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": modes,
            "temperature": 15.0,
            "current_temperature": 19.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    hass.states.async_set("sensor.room_temp", "19.0", {"device_class": "temperature"})
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --- __init__: async_remove_entry (system-hub boiler OFF, V2b) ----------------


async def test_remove_system_hub_switches_boiler_off(hass: HomeAssistant) -> None:
    # F12: OFF fires on removal only when Poise was actuating (BOTH actions wired).
    turn_off = async_mock_service(hass, "switch", "turn_off")
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on",
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    await async_remove_entry(hass, hub)
    assert len(turn_off) == 1


async def test_remove_zone_entry_is_noop(hass: HomeAssistant) -> None:
    zone = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_base(), title="Z"
    )
    zone.add_to_hass(hass)
    await async_remove_entry(hass, zone)  # not a system hub -> early return


async def test_remove_hub_without_off_action_is_noop(hass: HomeAssistant) -> None:
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM},
        title="Poise System",
    )
    hub.add_to_hass(hass)
    await async_remove_entry(hass, hub)  # no OFF action parses -> return


async def test_remove_hub_swallows_off_failure(hass: HomeAssistant) -> None:
    async def _boom(call: ServiceCall) -> None:
        raise RuntimeError("boiler stuck on")

    hass.services.async_register("switch", "turn_off", _boom)
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    await async_remove_entry(hass, hub)  # OFF call raises -> best-effort, swallowed


# --- __init__: a card-registration failure must never block setup (ADR-0040) --


async def test_async_setup_swallows_card_registration_failure(
    hass: HomeAssistant,
) -> None:
    with patch(
        "custom_components.poise.frontend.async_register_card",
        side_effect=RuntimeError("frontend registration down"),
    ):
        assert await async_setup(hass, {}) is True


# --- coordinator: the weather-forecast fetch (ADR-0025) -----------------------


async def test_forecast_outdoor_fetches_hourly(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    now = dt_util.utcnow()
    forecast = [
        {"datetime": now.isoformat(), "temperature": 3.0},
        {"datetime": now.isoformat(), "temperature": 4.0},
    ]

    async def _get(call: ServiceCall) -> dict[str, Any]:
        return {"weather.home": {"forecast": forecast}}

    hass.services.async_register(
        "weather", "get_forecasts", _get, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("weather.home", "cloudy", {"temperature": 4.0})
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(hass, _base(**{CONF_WEATHER: "weather.home"}))
    coord = entry.runtime_data

    coord._forecast_at = None  # force a fresh fetch
    out = await coord._forecast_outdoor(120.0, 9.9)
    assert isinstance(out, float)

    # a zone without a weather entity degrades straight to the fallback
    coord._weather = None
    coord._forecast_at = None
    assert await coord._forecast_outdoor(60.0, 3.3) == 3.3


async def test_forecast_outdoor_degrades_on_failure(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    async def _boom(call: ServiceCall) -> dict[str, Any]:
        raise RuntimeError("weather integration down")

    hass.services.async_register(
        "weather", "get_forecasts", _boom, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("weather.home", "cloudy", {"temperature": 4.0})
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(hass, _base(**{CONF_WEATHER: "weather.home"}))
    coord = entry.runtime_data

    coord._forecast_at = None
    assert await coord._forecast_outdoor(120.0, 7.5) == 7.5  # fallback on failure


# --- coordinator: scalar read helpers -----------------------------------------


async def test_coordinator_scalar_read_helpers(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, modes=["heat", "off"])
    entry = await _setup(hass, _base())
    coord = entry.runtime_data

    # a missing sensor has no change-age
    assert coord._sensor_age("sensor.ghost") is None
    # an actuator that reports no hvac_modes/max_temp -> heat-only + default max
    coord._actuator = "climate.ghost"
    assert coord._capability() == (True, False)
    assert isinstance(coord._device_max(), float)
    # sun elevation attribute (present -> float, absent -> None)
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 30.0})
    assert coord._sun_elevation() == 30.0
    hass.states.async_set("sun.sun", "above_horizon", {})
    assert coord._sun_elevation() is None
