"""Phase 0 — forecast demand gating (CI-only).

Refactoring plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md,
Befund 5 / Phase-0 checklist item "Forecast-Bedarfs-Test (Befund 5): kein
Weather-Call, wenn ``predictive=False``; genau ein Call ... wenn
``predictive=True``". These tests freeze TODAY's gating of the one
``weather.get_forecasts`` I/O inside the tick, in ``coordinator.py``:

* the predictive gate 2232-2236: ``predictive = can_heat and
  self._ekf.identified and (self._optimal_start or self._optimal_stop)``
  (``_optimal_stop`` mirrors ``_optimal_start``, line 560);
* the single in-tick await 2243: ``await self._forecast_outdoor(...)`` —
  the ONLY ``_forecast_outdoor`` call site in ``_run_once``;
* ``_forecast_outdoor`` 1440-1482 with the service call 1466-1473
  (payload ``{"type": "hourly", "entity_id": self._weather}``) and the
  FORECAST_TTL_S (900 s) cache-staleness check at 1459.

Frozen behaviour: no predictive prerequisites -> ZERO weather service calls
per tick; predictive zone -> EXACTLY ONE call, and a second tick within the
TTL serves from the cache (no further call); past the TTL it refetches.

The horizon (``lead_minutes``, 2238-2242) is NOT part of the service-call
payload — it is applied locally in ``mean_forecast_outdoor`` (1482) — so it
cannot be asserted from the recorded calls; only ``type``/``entity_id`` are.
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
    FORECAST_TTL_S,
)
from custom_components.poise.estimation.thermal_ekf import ThermalEKF


class _FakeClock:
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
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        CONF_WEATHER: "weather.home",
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
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set("weather.home", "cloudy", {"temperature": 4.0})


def _make_identified(ekf: ThermalEKF) -> None:
    """Force the EKF past every maturity gate (test_identified_shadow pattern)."""
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.n_cooling = 1000
    ekf._n_uc = 1000
    ekf._n_qocc = 1000
    ekf.p[0][0] = 0.01  # temperature_std = 0.1 K, well under the 0.5 K gate
    assert ekf.identified


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _register_forecast_counter(hass: HomeAssistant) -> list[ServiceCall]:
    """A counting ``weather.get_forecasts`` handler returning a valid response
    (test_forecast_backoff pattern). The future timestamp survives the
    past-entry filter in ``forecast_samples_from_response``."""
    calls: list[ServiceCall] = []
    future = (dt_util.utcnow() + timedelta(hours=1)).isoformat()

    async def _handler(call: ServiceCall) -> dict[str, Any]:
        calls.append(call)
        forecast = [{"datetime": future, "temperature": 4.0}]
        return {"weather.home": {"forecast": forecast}}

    hass.services.async_register(
        "weather", "get_forecasts", _handler, supports_response=SupportsResponse.ONLY
    )
    return calls


async def test_unidentified_ekf_makes_zero_forecast_calls(
    hass: HomeAssistant,
) -> None:
    """optimal_start ON + weather configured, but the EKF is fresh (not
    identified) -> ``predictive`` (2232-2236) is False -> the forecast await
    at 2243 is never reached: ZERO weather service calls, tick fully healthy."""
    _room_and_actuator(hass)
    entry = await _setup(hass, _base())
    coord: Any = entry.runtime_data
    # re-arm the climate recorders AFTER setup (platform forward re-registers)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    calls = _register_forecast_counter(hass)
    coord._clock = _FakeClock(10_000.0)
    assert not coord._ekf.identified

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.last_update_success is True
    assert (coord.data or {}).get("available") is True
    assert calls == [], "an unidentified model must not trigger a weather fetch"


async def test_optimal_start_off_makes_zero_forecast_calls(
    hass: HomeAssistant,
) -> None:
    """EKF identified + weather configured, but optimal_start OFF (which also
    forces ``_optimal_stop`` off, coordinator.py:560) -> ``predictive`` False
    -> ZERO weather service calls."""
    _room_and_actuator(hass)
    entry = await _setup(hass, _base(**{CONF_OPTIMAL_START: False}))
    coord: Any = entry.runtime_data
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    calls = _register_forecast_counter(hass)
    coord._clock = _FakeClock(10_000.0)
    _make_identified(coord._ekf)
    assert coord._optimal_start is False
    assert coord._optimal_stop is False  # mirrors optimal_start (line 560)

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.last_update_success is True
    assert (coord.data or {}).get("available") is True
    assert calls == [], "optimal_start off must not trigger a weather fetch"


async def test_predictive_zone_makes_exactly_one_call_then_serves_from_cache(
    hass: HomeAssistant,
) -> None:
    """Predictive zone (identified EKF + optimal_start + weather entity):

    * tick 1 -> EXACTLY ONE ``weather.get_forecasts`` call, with today's
      payload ``{"type": "hourly", "entity_id": "weather.home"}`` (1470);
    * tick 2 within FORECAST_TTL_S -> NO further call (cache, 1459);
    * a tick past the TTL -> exactly one refetch (staleness re-arms).

    A fresh coordinator instance (this test's own entry) plus a FakeClock
    keeps the TTL arithmetic deterministic: setup's first refresh runs with
    an unidentified EKF, so ``_forecast_at`` is still None here."""
    _room_and_actuator(hass)
    entry = await _setup(hass, _base())
    coord: Any = entry.runtime_data
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    calls = _register_forecast_counter(hass)
    clock = _FakeClock(10_000.0)
    coord._clock = clock
    _make_identified(coord._ekf)
    assert coord._forecast_at is None  # nothing fetched during setup's refresh

    # tick 1 — predictive: exactly one fetch
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    assert (coord.data or {}).get("available") is True
    assert len(calls) == 1, f"expected exactly one weather call, got {len(calls)}"
    assert calls[0].data.get("type") == "hourly"
    assert calls[0].data.get("entity_id") == "weather.home"
    # NOTE: the horizon (lead_minutes) is not part of the payload — it is
    # applied locally in mean_forecast_outdoor — so it cannot be asserted here.

    # tick 2 — 60 s later, well inside the 900 s TTL: served from the cache
    clock.t += 60.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    assert len(calls) == 1, "a second tick within the TTL must reuse the cache"

    # tick 3 — past the TTL: the staleness check (1459) re-arms one refetch
    clock.t += FORECAST_TTL_S
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    assert len(calls) == 2, "past the TTL exactly one refetch is expected"
