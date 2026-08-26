"""Phase 10 — F-FORECAST: the weather fetch left the tick lock (CI-only).

Refactoring plan ``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md``
Befund 5 / phase 10; ADR-0063.

Until phase 10 every stale-cache predictive tick awaited
``weather.get_forecasts`` under the coordinator lock, so a slow weather
integration stretched the tick by up to the 10 s call timeout. The chosen gate
variant keeps ONE deliberate exception and moves everything else off the tick:

* **cold start** (no cache at all) still awaits — that tick decides a preheat
  edge after a restart and must not fall back to the flat constant outdoor;
* **warm cache** serves this tick and refreshes in the background;
* the refresh is **single-flight**, snapshots **atomically** and is
  **cancelled** on unload.

The gating/payload/TTL/backoff pins live in test_phase0_forecast_gating and
test_phase5a_executor; this module pins the decoupling itself.
"""

from __future__ import annotations

import asyncio
import time
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
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WEATHER,
    DOMAIN,
    FORECAST_TTL_S,
)
from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.ha.forecast_provider import ForecastProvider

_SLOW_FETCH_S = 0.4
_SLOW_FETCH_MS = _SLOW_FETCH_S * 1000.0
_WEATHER = "weather.home"
_COORD_LOGGER = __import__("logging").getLogger("custom_components.poise.coordinator")


class _FakeClock:
    """Seeded from ``time.monotonic()`` for continuity with the real-clock
    setup tick (same reason as test_phase0_forecast_gating: a fixed literal
    seed makes the EKF-learn dt host-dependent and can de-identify the model
    mid-tick, which would close the predictive gate)."""

    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


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
        # P2.1: a real comfort window so the schedule has an edge -- an
        # edgeless (always-comfort) zone deliberately requests no forecast.
        CONF_COMFORT_START: "00:00",
        CONF_COMFORT_END: "23:59",
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        CONF_WEATHER: _WEATHER,
        **extra,
    }


def _room_and_actuator(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "18.5", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 17.0,
            "current_temperature": 18.5,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set(_WEATHER, "cloudy", {"temperature": 4.0})


def _make_identified(ekf: ThermalEKF) -> None:
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.n_cooling = 1000
    ekf._n_uc = 1000
    ekf._n_qocc = 1000
    ekf.p[0][0] = 0.01
    assert ekf.identified


def _register_weather(hass: HomeAssistant, *, delay: float = 0.0) -> list[ServiceCall]:
    calls: list[ServiceCall] = []
    future = (dt_util.utcnow() + timedelta(hours=1)).isoformat()

    async def _handler(call: ServiceCall) -> dict[str, Any]:
        calls.append(call)
        if delay:
            await asyncio.sleep(delay)
        return {_WEATHER: {"forecast": [{"datetime": future, "temperature": 4.0}]}}

    hass.services.async_register(
        "weather", "get_forecasts", _handler, supports_response=SupportsResponse.ONLY
    )
    return calls


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_base(), title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_slow_weather_no_longer_inflates_tick_ms(hass: HomeAssistant) -> None:
    """A 400 ms weather integration on a STALE-but-warm cache must not show up
    in ``tick_ms``. Before phase 10 the fetch was awaited inside the measured
    span, so this tick would have reported >= 400 ms."""
    _room_and_actuator(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    calls = _register_weather(hass, delay=_SLOW_FETCH_S)
    clock = _FakeClock(time.monotonic())
    coord.runtime.clock = clock
    _make_identified(coord.runtime.learning.ekf)

    # tick 1 primes the cache — the deliberate cold-start await
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert coord.forecast_provider.forecast, "cold start must fill the cache"
    cold_ms = (coord.data or {})["tick_ms"]
    assert cold_ms >= _SLOW_FETCH_MS, (
        f"cold start is supposed to await the fetch, tick_ms={cold_ms}"
    )

    # tick 2: stale cache, but warm -> background refresh. The staleness is
    # induced by back-dating the cache stamp, NOT by jumping the clock a full
    # TTL: a 900 s tick dt inflates the EKF covariance enough to de-identify
    # the model, which would close the predictive gate and fetch nothing.
    clock.t += 60.0
    coord.forecast_provider.forecast_at = clock.t - FORECAST_TTL_S - 1.0
    _make_identified(coord.runtime.learning.ekf)
    await coord.async_refresh()
    warm_ms = (coord.data or {})["tick_ms"]
    await hass.async_block_till_done()

    assert coord.last_update_success is True
    assert warm_ms < _SLOW_FETCH_MS / 2, (
        f"tick_ms={warm_ms} — the tick still waited for the forecast"
    )
    assert len(calls) == 2, "the refresh must still happen, just off the tick"


async def test_single_flight_and_atomic_snapshot(hass: HomeAssistant) -> None:
    """Two stale reads while a refresh is in flight start exactly ONE call, and
    both see a complete cache (never a half-written one)."""
    calls = _register_weather(hass, delay=_SLOW_FETCH_S)
    clock = _FakeClock(1000.0)
    provider = ForecastProvider(hass, clock, _COORD_LOGGER)

    first = await provider.mean_outdoor(_WEATHER, 120.0, 9.9)  # cold, awaited
    assert len(calls) == 1
    assert first != 9.9

    clock.t += FORECAST_TTL_S  # stale -> background refresh
    assert await provider.mean_outdoor(_WEATHER, 120.0, 9.9) == first
    # a second read while the first refresh is still in flight
    assert await provider.mean_outdoor(_WEATHER, 120.0, 9.9) == first
    await hass.async_block_till_done()
    assert len(calls) == 2, "single-flight: the second read must not fetch again"


async def test_async_close_cancels_an_in_flight_refresh(hass: HomeAssistant) -> None:
    """No task may outlive the config entry: ``async_close`` cancels the
    in-flight refresh (the coordinator calls it from the unload path)."""
    _register_weather(hass, delay=_SLOW_FETCH_S)
    clock = _FakeClock(1000.0)
    provider = ForecastProvider(hass, clock, _COORD_LOGGER)

    await provider.mean_outdoor(_WEATHER, 120.0, 9.9)
    clock.t += FORECAST_TTL_S
    await provider.mean_outdoor(_WEATHER, 120.0, 9.9)
    task = provider._refresh
    assert task is not None and not task.done()

    await provider.async_close()
    assert task.cancelled()
    assert provider._refresh is None
    # idempotent: a second close on a closed provider is a no-op
    await provider.async_close()


async def test_unload_closes_the_provider(hass: HomeAssistant) -> None:
    """End-to-end: unloading the entry leaves no forecast task behind."""
    _room_and_actuator(hass)
    _register_weather(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert coord.forecast_provider._refresh is None
