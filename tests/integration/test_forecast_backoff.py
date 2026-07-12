"""Review F10: a weather-forecast fetch failure must fall through to the last
successfully cached forecast (not hardcode ``fallback`` and throw away a still
plausibly-useful cache), and must back off before retrying (not re-attempt the
service call on every single tick for as long as the integration stays down).

Previously the ``except Exception:`` branch in ``_forecast_outdoor`` did
``return fallback`` directly, discarding ``self._forecast`` even when it held
a recent successful fetch, and left ``self._forecast_at`` untouched -- which
(for an integration that fails every time) meant the ``now - self._forecast_at
>= FORECAST_TTL_S`` staleness check kept re-triggering the failing service
call on every tick, with no backoff at all.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.util import dt as dt_util
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
    CONF_WEATHER,
    DOMAIN,
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


def _actuator(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 19.0,
            "current_temperature": 19.0,
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


async def test_failure_falls_back_to_last_good_cache_not_flat_fallback(
    hass: HomeAssistant,
) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    # a comfortably-future timestamp so it survives the real time elapsed
    # between building this fixture and the coordinator actually calling
    # ``forecast_samples_from_response`` (which filters out past entries).
    future = (dt_util.utcnow() + timedelta(hours=1)).isoformat()
    forecast = [{"datetime": future, "temperature": 30.0}]
    calls = {"n": 0}

    async def _flaky(call: ServiceCall) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            return {"weather.home": {"forecast": forecast}}
        raise RuntimeError("weather integration down")

    hass.services.async_register(
        "weather", "get_forecasts", _flaky, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("weather.home", "cloudy", {"temperature": 4.0})
    _actuator(hass)
    entry = await _setup(hass, _base(**{CONF_WEATHER: "weather.home"}))
    coord: Any = entry.runtime_data

    # first call succeeds and caches a forecast heavily biased toward 30.0 C.
    coord._forecast_at = None
    first = await coord._forecast_outdoor(120.0, 9.9)
    assert first > 15.0, f"expected the 30 C forecast sample, got {first!r}"

    # force the cache stale so the next call attempts a refetch, which fails.
    coord._forecast_at = coord._clock.monotonic() - 10_000.0
    second = await coord._forecast_outdoor(120.0, 9.9)
    # F10: falls through to the still-cached (now stale) forecast rather than
    # collapsing straight to the flat fallback (9.9).
    assert second == first, (
        f"a fetch failure should reuse the last-good cache ({first!r}), "
        f"not the flat fallback: got {second!r}"
    )


async def test_repeated_failures_back_off_instead_of_retrying_every_tick(
    hass: HomeAssistant,
) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    calls = {"n": 0}

    async def _boom(call: ServiceCall) -> dict[str, Any]:
        calls["n"] += 1
        raise RuntimeError("weather integration down")

    hass.services.async_register(
        "weather", "get_forecasts", _boom, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("weather.home", "cloudy", {"temperature": 4.0})
    _actuator(hass)
    entry = await _setup(hass, _base(**{CONF_WEATHER: "weather.home"}))
    coord: Any = entry.runtime_data

    coord._forecast_at = None
    await coord._forecast_outdoor(120.0, 7.5)
    assert calls["n"] == 1

    # immediately call again -- still within FORECAST_TTL_S of the failure.
    # F10: must not re-attempt the failing service call again this soon.
    await coord._forecast_outdoor(120.0, 7.5)
    assert calls["n"] == 1, "a failed fetch must back off, not retry every call"
