"""Phase-5A wiring: coordinator -> ActuatorExecutor / ForecastProvider.

Pins the glue this phase added to ``coordinator.py`` (the modules themselves
are pinned in ``test_phase5a_executor.py``):

* ``__init__`` constructs the two adapters (``_actuator_executor`` /
  ``_forecast_provider``);
* the forecast cache lives in the provider, and the coordinator's
  ``_forecast`` / ``_forecast_at`` / ``_forecast_fail_at`` property proxies
  forward BOTH ways — a test poke on the coordinator attribute must keep
  governing the provider's TTL/backoff decisions (test_forecast_backoff,
  test_glue_coverage2/4, test_phase0_forecast_gating poke/pin them);
* ``_forecast_outdoor`` delegates to ``ForecastProvider.mean_outdoor`` under
  the coordinator's LIVE clock: a test-swapped ``coord._clock`` governs the
  provider's staleness instants (the ``_ReaderClock`` forwarder pattern).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
from custom_components.poise.ha.actuator_executor import ActuatorExecutor
from custom_components.poise.ha.forecast_provider import ForecastProvider

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: False,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


async def _setup(hass: HomeAssistant) -> Any:
    hass.states.async_set(
        "sensor.room_temp",
        "20.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 20.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


async def test_init_constructs_the_two_adapters(hass: HomeAssistant) -> None:
    coord = await _setup(hass)
    assert isinstance(coord._actuator_executor, ActuatorExecutor)
    assert isinstance(coord._forecast_provider, ForecastProvider)


async def test_forecast_cache_proxies_forward_both_ways(hass: HomeAssistant) -> None:
    """The phase-4 proxy pattern: a coordinator poke governs the provider
    state and a provider mutation is what the coordinator attribute reads."""
    coord = await _setup(hass)
    prov = coord._forecast_provider

    # coordinator poke -> provider state (the direction the existing
    # forecast tests use to force/inhibit a fetch)
    coord._forecast = [(0.0, 1.5)]
    coord._forecast_at = 123.0
    coord._forecast_fail_at = 45.0
    assert prov.forecast == [(0.0, 1.5)]
    assert prov.forecast_at == 123.0
    assert prov.fail_at == 45.0

    # provider mutation -> coordinator read (what a tick's fetch updates)
    prov.forecast = [(5.0, 2.0)]
    prov.forecast_at = None
    prov.fail_at = None
    assert coord._forecast == [(5.0, 2.0)]
    assert coord._forecast_at is None
    assert coord._forecast_fail_at is None


async def test_forecast_outdoor_delegates_under_the_live_clock(
    hass: HomeAssistant,
) -> None:
    """``_forecast_outdoor`` -> provider cache, staleness under a test-swapped
    ``coord._clock``. With a FRESH cache no fetch is attempted at all (no
    weather service is registered here: an attempted call would fail and set
    the ``fail_at`` backoff — asserting it stays None proves the provider ran
    on the swapped clock, not a stale real-monotonic snapshot)."""
    coord = await _setup(hass)
    clock = _FakeClock(5000.0)
    coord._clock = clock
    coord._weather = "weather.home"
    coord._forecast = [(0.0, 4.0), (120.0, 4.0)]
    coord._forecast_at = 4900.0  # fresh under the fake clock (TTL 900 s)
    coord._forecast_fail_at = None

    assert await coord._forecast_outdoor(60.0, 99.9) == 4.0  # cache, not fallback
    assert coord._forecast_fail_at is None  # no fetch attempt was made
    assert coord._forecast_at == 4900.0  # cache instant untouched


async def test_forecast_failure_debug_stays_on_coordinator_channel(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Aequivalenz-Pin (5A-Abweichungsfix, Baseline l. 1191): nach der
    Kapselung emittiert der Forecast-Fehlerpfad seinen Debug-Record
    weiterhin vom Logger ``custom_components.poise.coordinator`` (das
    Coordinator-``_LOGGER`` wird in den Provider injiziert) — NICHT vom
    Provider-Modul-Kanal. Kanal-Identitaet ist beobachtbares Verhalten fuer
    per-Modul-Logger-Konfigurationen."""
    coord = await _setup(hass)

    async def _boom(call: ServiceCall) -> dict[str, Any]:
        raise RuntimeError("weather integration down")

    hass.services.async_register(
        "weather", "get_forecasts", _boom, supports_response=SupportsResponse.ONLY
    )
    coord._clock = _FakeClock(5000.0)
    coord._weather = "weather.home"
    coord._forecast = []
    coord._forecast_at = None  # stale -> Fetch-Versuch, der fehlschlaegt
    coord._forecast_fail_at = None

    # Auf dem PARENT-Logger capturen, damit Records beider Kandidaten-Kanaele
    # landen wuerden — der Exakt-Assert unten schliesst den Provider-Kanal aus.
    with caplog.at_level(logging.DEBUG, logger="custom_components.poise"):
        assert await coord._forecast_outdoor(60.0, 7.5) == 7.5  # leerer Cache

    records = [
        r
        for r in caplog.records
        if r.getMessage() == "Poise: weather forecast unavailable; using stale cache"
    ]
    assert [(r.name, r.levelno) for r in records] == [
        ("custom_components.poise.coordinator", logging.DEBUG)
    ]
    assert coord._forecast_fail_at == 5000.0  # F10-Backoff wie ALT gestartet
