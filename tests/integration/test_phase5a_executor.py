"""Phase 5A — ``ha/actuator_executor`` + ``ha/forecast_provider`` (Befunde 5+11).

Plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md, Abschnitt 6
Phase 5A. In 5A wandern NUR die Call-Primitiven bzw. der Forecast-Cache in
``ha/``; Try-Grenzen, Log-Texte und Stempel bleiben im Coordinator (5B). Es
gibt noch keine Verdrahtung — die Klassen werden hier direkt gegen die
HA-Test-Runtime exerziert:

* ``ActuatorExecutor``: jede Primitive dispatcht ZEICHENGENAU die heutige
  Payload mit ``blocking=False`` und heutiger Context-Form (Mode/Setpoint:
  ``context``-kwarg, default ``None``; Select/Feed: KEIN ``context``-kwarg —
  F-CONTEXT erst Phase 10). Synchrone Dispatch-Fehler (``ServiceNotFound``)
  werden unverändert WEITERgeworfen (kein eigenes try); Handler-Exceptions
  eines registrierten Services propagieren bei ``blocking=False`` NIE
  (Phase-0-Ist-Befund — HA fängt sie im Hintergrund-Task). Der Setpoint-Pfad
  dispatcht über das Modul-Attribut ``actuator_mod.write`` und erhält damit
  die ``patch.object``-Injektionsfläche von test_phase0_attempt_success.
* ``ForecastProvider``: ``_forecast_outdoor``-Semantik 1:1 hinter der neuen
  Schnittstelle — Payload ``{"type": "hourly", "entity_id": ...}``, TTL-Cache,
  F10 (Fehler -> letzter guter Cache statt flachem Fallback; Backoff vor dem
  Retry), leerer Cache -> Fallback (Muster: test_forecast_backoff).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import (
    Context,
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_mock_service

import custom_components.poise.actuator as actuator_mod
from custom_components.poise.const import FORECAST_TTL_S
from custom_components.poise.contracts import ActuatorCommand, ActuatorPath
from custom_components.poise.ha.actuator_executor import ActuatorExecutor
from custom_components.poise.ha.forecast_provider import ForecastProvider

TRV = "climate.trv"
SELECT = "select.trv_sensor_mode"
EXT = "number.trv_external_temperature"
WEATHER = "weather.home"

# 5A-Aequivalenz (Abweichungsfix): der Provider loggt ueber den INJIZIERTEN
# Logger — der Coordinator reicht sein Modul-``_LOGGER`` durch, damit der
# Failure-Debug-Record den Baseline-Logger-NAMEN behaelt
# (``custom_components.poise.coordinator``, Baseline l. 1191). Die
# Direktkonstruktionen hier spiegeln die Produktionsverdrahtung.
_COORD_LOGGER = logging.getLogger("custom_components.poise.coordinator")


class _FakeClock:
    """A monotonic clock whose value the test advances by hand."""

    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _cmd(value: float, *, reason: str = "tick") -> ActuatorCommand:
    return ActuatorCommand(
        actuator_id=TRV,
        path=ActuatorPath.SETPOINT,
        value=value,
        hvac_mode="heat",
        reason=reason,
    )


def _dispatch_spy(hass: HomeAssistant) -> Any:
    """Spy auf ``ServiceRegistry.async_call`` — auf KLASSEN-Ebene, weil das
    Instanz-Attribut slots-read-only ist. ``autospec`` zeichnet die exakte
    Dispatch-Form auf (``self`` als erstes Positionsargument), ``side_effect``
    delegiert unveraendert an das Original."""
    cls = type(hass.services)
    return patch.object(cls, "async_call", autospec=True, side_effect=cls.async_call)


# --- ActuatorExecutor: Payload / blocking / Context-Form ----------------------


async def test_set_hvac_mode_dispatches_exact_payload_blocking_false(
    hass: HomeAssistant,
) -> None:
    """Heutige Mode-Write-Form (Z. 1681/2686/3037): exakt die Payload
    ``{"entity_id", "hvac_mode"}``, ``blocking=False``, Context-kwarg
    vorhanden und default ``None`` (entspricht dem heute weggelassenen
    kwarg der Safe-State-/Rescue-Sites)."""
    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    ex = ActuatorExecutor(hass)
    with _dispatch_spy(hass) as spy:
        await ex.set_hvac_mode(TRV, "heat")
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert dict(calls[0].data) == {"entity_id": TRV, "hvac_mode": "heat"}
    assert spy.call_args.args == (
        hass.services,
        "climate",
        "set_hvac_mode",
        {"entity_id": TRV, "hvac_mode": "heat"},
    )
    assert spy.call_args.kwargs == {"blocking": False, "context": None}


async def test_set_hvac_mode_passes_caller_context_through(
    hass: HomeAssistant,
) -> None:
    """V2-Sites (Mode-Nudge Z. 2686): ein vom Aufrufer erzeugter Context wird
    IDENTISCH durchgereicht — die PRIMITIVE erzeugt selbst keinen (seit 5B
    erzeugen die Sequenz-Methoden den Context und reichen ihn genau so
    hierher durch; die Registrierung der ID übernimmt ``commit_execution``)."""
    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    ex = ActuatorExecutor(hass)
    ctx = Context()
    await ex.set_hvac_mode(TRV, "cool", context=ctx)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].context is ctx


async def test_set_hvac_mode_raises_service_not_found_synchronously(
    hass: HomeAssistant,
) -> None:
    """Fehlender Service -> ``ServiceNotFound`` direkt aus dem Dispatch —
    genau der Fehler, den die Coordinator-Grenzen heute sehen (Phase-0-
    Injektionsmuster: Service entfernen statt werfender Handler)."""
    assert not hass.services.has_service("climate", "set_hvac_mode")
    ex = ActuatorExecutor(hass)
    with pytest.raises(ServiceNotFound):
        await ex.set_hvac_mode(TRV, "heat")


async def test_blocking_false_handler_exceptions_never_propagate(
    hass: HomeAssistant,
) -> None:
    """Phase-0-Ist-Befund: bei ``blocking=False`` fängt HA Handler-Exceptions
    im Hintergrund-Task — KEINE Primitive darf sie zum Aufrufer tragen (die
    per-Effekt-Grenzen sehen nur synchrone Dispatch-Fehler)."""

    async def _boom(call: ServiceCall) -> None:
        raise RuntimeError("handler failure")

    hass.services.async_register("climate", "set_hvac_mode", _boom)
    hass.services.async_register("climate", "set_temperature", _boom)
    hass.services.async_register("select", "select_option", _boom)
    hass.services.async_register("number", "set_value", _boom)
    ex = ActuatorExecutor(hass)

    await ex.set_hvac_mode(TRV, "heat")
    await ex.write_setpoint(_cmd(20.0))
    await ex.select_option(SELECT, "external")
    await ex.set_number(EXT, 20.3)
    await hass.async_block_till_done()


async def test_write_setpoint_dispatches_raw_value(hass: HomeAssistant) -> None:
    """Setpoint-Payload (actuator.service_call_for): ``{"entity_id",
    "temperature"}`` mit dem ROHEN Wert (nicht gesnappt — snap_to_step ist
    Echo-Baseline-Stempeln im Coordinator); ``hvac_mode``/``reason`` werden
    NICHT gesendet. ``blocking=False`` hartkodiert in actuator.write."""
    calls = async_mock_service(hass, "climate", "set_temperature")
    ex = ActuatorExecutor(hass)
    with _dispatch_spy(hass) as spy:
        await ex.write_setpoint(_cmd(20.3))  # 20.3: bewusst kein 0.5er-Step
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert dict(calls[0].data) == {"entity_id": TRV, "temperature": 20.3}
    assert spy.call_args.args == (
        hass.services,
        "climate",
        "set_temperature",
        {"entity_id": TRV, "temperature": 20.3},
    )
    assert spy.call_args.kwargs == {"blocking": False, "context": None}


async def test_write_setpoint_keeps_actuator_module_patch_surface(
    hass: HomeAssistant,
) -> None:
    """test_phase0_attempt_success patcht ``actuator_mod.write`` über den
    Modul-Alias — die 5A-Primitive dispatcht durch DIESES Modul-Attribut,
    der Patch greift also weiterhin; der injizierte Fehler propagiert
    unverändert (kein try im Executor), Context und Command identisch."""
    ex = ActuatorExecutor(hass)
    cmd = _cmd(21.0)
    ctx = Context()
    with (
        patch.object(
            actuator_mod, "write", side_effect=HomeAssistantError("injected")
        ) as mock_write,
        pytest.raises(HomeAssistantError, match="injected"),
    ):
        await ex.write_setpoint(cmd, context=ctx)

    assert mock_write.call_count == 1
    assert mock_write.call_args.args == (hass, cmd)
    assert mock_write.call_args.kwargs == {"context": ctx}


async def test_write_setpoint_raises_service_not_found_synchronously(
    hass: HomeAssistant,
) -> None:
    assert not hass.services.has_service("climate", "set_temperature")
    ex = ActuatorExecutor(hass)
    with pytest.raises(ServiceNotFound):
        await ex.write_setpoint(_cmd(20.0))


async def test_select_option_dispatches_payload_without_context_kwarg(
    hass: HomeAssistant,
) -> None:
    """Select-Switch (Z. 2950): exakte Payload, ``blocking=False`` und KEIN
    ``context``-kwarg (F-CONTEXT erst Phase 10) — die Primitive bietet
    bewusst keinen Context-Parameter an."""
    calls = async_mock_service(hass, "select", "select_option")
    ex = ActuatorExecutor(hass)
    with _dispatch_spy(hass) as spy:
        await ex.select_option(SELECT, "external")
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert dict(calls[0].data) == {"entity_id": SELECT, "option": "external"}
    assert spy.call_args.args == (
        hass.services,
        "select",
        "select_option",
        {"entity_id": SELECT, "option": "external"},
    )
    assert spy.call_args.kwargs == {"blocking": False}  # kein context-kwarg


async def test_select_option_raises_service_not_found_synchronously(
    hass: HomeAssistant,
) -> None:
    """Das Phase-0-Injektionsmuster (Select-Service nie registriert) trifft
    die Primitive genauso: der Dispatch selbst wirft."""
    assert not hass.services.has_service("select", "select_option")
    ex = ActuatorExecutor(hass)
    with pytest.raises(ServiceNotFound):
        await ex.select_option(SELECT, "external")


async def test_set_number_dispatches_payload_without_context_kwarg(
    hass: HomeAssistant,
) -> None:
    """Ext-Temp-Feed (Z. 2978): exakte Payload mit dem bereits gerundeten
    Feed-Wert, ``blocking=False``, KEIN ``context``-kwarg."""
    calls = async_mock_service(hass, "number", "set_value")
    ex = ActuatorExecutor(hass)
    with _dispatch_spy(hass) as spy:
        await ex.set_number(EXT, 20.3)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert dict(calls[0].data) == {"entity_id": EXT, "value": 20.3}
    assert spy.call_args.args == (
        hass.services,
        "number",
        "set_value",
        {"entity_id": EXT, "value": 20.3},
    )
    assert spy.call_args.kwargs == {"blocking": False}  # kein context-kwarg


async def test_set_number_raises_service_not_found_synchronously(
    hass: HomeAssistant,
) -> None:
    assert not hass.services.has_service("number", "set_value")
    ex = ActuatorExecutor(hass)
    with pytest.raises(ServiceNotFound):
        await ex.set_number(EXT, 20.3)


# --- ForecastProvider: Payload-Pin, TTL-Cache, F10-Backoff --------------------


def _future_iso(hours: float = 1.0) -> str:
    """Komfortabel in der Zukunft, damit ``forecast_samples_from_response``
    (filtert Vergangenheits-Eintraege) das Sample sicher behaelt."""
    return (dt_util.utcnow() + timedelta(hours=hours)).isoformat()


async def test_forecast_missing_weather_entity_returns_fallback_without_call(
    hass: HomeAssistant,
) -> None:
    """Kein Weather-Entity -> sofort Fallback, NULL Service-Calls (Z. 1166)."""
    calls = {"n": 0}

    async def _handler(call: ServiceCall) -> dict[str, Any]:
        calls["n"] += 1
        return {}

    hass.services.async_register(
        "weather", "get_forecasts", _handler, supports_response=SupportsResponse.ONLY
    )
    provider = ForecastProvider(hass, _FakeClock(1000.0), _COORD_LOGGER)

    assert await provider.mean_outdoor(None, 120.0, 7.5) == 7.5
    assert await provider.mean_outdoor("", 120.0, 7.5) == 7.5
    assert calls["n"] == 0


async def test_forecast_fetch_pins_payload_and_serves_cache_within_ttl(
    hass: HomeAssistant,
) -> None:
    """Erster Call fetcht mit exakt der heutigen Payload (``type``/
    ``entity_id`` — der Horizont ist NICHT Teil der Payload); innerhalb der
    TTL bedient der Cache (kein zweiter Call); nach Ablauf wird refetcht
    (Muster test_phase0_forecast_gating)."""
    payloads: list[dict[str, Any]] = []

    async def _handler(call: ServiceCall) -> dict[str, Any]:
        payloads.append(dict(call.data))
        return {
            WEATHER: {"forecast": [{"datetime": _future_iso(), "temperature": 30.0}]}
        }

    hass.services.async_register(
        "weather", "get_forecasts", _handler, supports_response=SupportsResponse.ONLY
    )
    clock = _FakeClock(1000.0)
    provider = ForecastProvider(hass, clock, _COORD_LOGGER)

    first = await provider.mean_outdoor(WEATHER, 120.0, 9.9)
    assert first == pytest.approx(30.0)  # das 30-C-Sample dominiert den Horizont
    assert payloads == [{"type": "hourly", "entity_id": WEATHER}]
    assert provider.forecast_at == 1000.0
    assert provider.fail_at is None

    clock.t = 1000.0 + FORECAST_TTL_S - 1.0  # noch innerhalb der TTL
    assert await provider.mean_outdoor(WEATHER, 120.0, 9.9) == first
    assert len(payloads) == 1, "within the TTL the cache must serve"

    clock.t = 1000.0 + FORECAST_TTL_S  # abgelaufen -> Refetch
    assert await provider.mean_outdoor(WEATHER, 120.0, 9.9) == first
    assert len(payloads) == 2
    assert provider.forecast_at == clock.t


async def test_forecast_failure_falls_back_to_last_good_cache_then_recovers(
    hass: HomeAssistant,
) -> None:
    """F10 (Muster test_forecast_backoff): ein Fetch-Fehler faellt auf den
    letzten guten Cache zurueck (nicht auf den flachen Fallback) und startet
    den Backoff; nach Ablauf des Backoffs heilt ein erfolgreicher Fetch den
    Zustand (``fail_at`` wieder None)."""
    calls = {"n": 0}

    async def _flaky(call: ServiceCall) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("weather integration down")
        temp = 30.0 if calls["n"] == 1 else 10.0
        return {
            WEATHER: {"forecast": [{"datetime": _future_iso(), "temperature": temp}]}
        }

    hass.services.async_register(
        "weather", "get_forecasts", _flaky, supports_response=SupportsResponse.ONLY
    )
    clock = _FakeClock(1000.0)
    provider = ForecastProvider(hass, clock, _COORD_LOGGER)

    first = await provider.mean_outdoor(WEATHER, 120.0, 9.9)
    assert first == pytest.approx(30.0)

    clock.t = 1000.0 + FORECAST_TTL_S  # Cache stale -> Refetch, der fehlschlaegt
    second = await provider.mean_outdoor(WEATHER, 120.0, 9.9)
    assert calls["n"] == 2
    assert second == first, "a fetch failure must reuse the last-good cache"
    assert provider.fail_at == clock.t  # Backoff gestartet

    # sofort nochmal: Backoff aktiv -> kein weiterer Service-Call.
    assert await provider.mean_outdoor(WEATHER, 120.0, 9.9) == first
    assert calls["n"] == 2

    clock.t += FORECAST_TTL_S  # Backoff abgelaufen -> Retry, diesmal Erfolg
    third = await provider.mean_outdoor(WEATHER, 120.0, 9.9)
    assert calls["n"] == 3
    assert third == pytest.approx(10.0)
    assert provider.fail_at is None
    assert provider.forecast_at == clock.t


async def test_forecast_repeated_failures_back_off_and_empty_cache_falls_back(
    hass: HomeAssistant,
) -> None:
    """F10-Gegenstueck mit leerem Cache: jeder Fehlversuch degradiert zum
    Fallback, ein zweiter Call innerhalb der TTL retryt NICHT, nach Ablauf
    genau EIN neuer Versuch."""
    calls = {"n": 0}

    async def _boom(call: ServiceCall) -> dict[str, Any]:
        calls["n"] += 1
        raise RuntimeError("weather integration down")

    hass.services.async_register(
        "weather", "get_forecasts", _boom, supports_response=SupportsResponse.ONLY
    )
    clock = _FakeClock(1000.0)
    provider = ForecastProvider(hass, clock, _COORD_LOGGER)

    assert await provider.mean_outdoor(WEATHER, 120.0, 7.5) == 7.5
    assert calls["n"] == 1
    assert provider.fail_at == 1000.0
    assert provider.forecast == []

    # sofort nochmal -- innerhalb FORECAST_TTL_S nach dem Fehler: kein Retry.
    assert await provider.mean_outdoor(WEATHER, 120.0, 7.5) == 7.5
    assert calls["n"] == 1, "a failed fetch must back off, not retry every call"

    clock.t = 1000.0 + FORECAST_TTL_S  # Backoff vorbei -> genau ein Retry
    assert await provider.mean_outdoor(WEATHER, 120.0, 7.5) == 7.5
    assert calls["n"] == 2
    assert provider.fail_at == clock.t  # Backoff neu gestartet


async def test_forecast_failure_debug_uses_injected_logger_channel(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Aequivalenz-Pin (5A-Abweichungsfix): der Failure-Debug-Record laeuft
    ueber den INJIZIERTEN Logger — Name (Coordinator-Kanal, Baseline l. 1191),
    Level und Text exakt wie ALT; KEIN Record auf einem eigenen
    ``forecast_provider``-Modul-Kanal."""

    async def _boom(call: ServiceCall) -> dict[str, Any]:
        raise RuntimeError("weather integration down")

    hass.services.async_register(
        "weather", "get_forecasts", _boom, supports_response=SupportsResponse.ONLY
    )
    provider = ForecastProvider(hass, _FakeClock(1000.0), _COORD_LOGGER)
    # Auf dem PARENT-Logger capturen: Records BEIDER Kandidaten-Kanaele
    # (coordinator wie ha.forecast_provider) wuerden hier landen — das macht
    # den Negativ-Assert unten beweiskraeftig.
    with caplog.at_level(logging.DEBUG, logger="custom_components.poise"):
        assert await provider.mean_outdoor(WEATHER, 120.0, 7.5) == 7.5

    records = [
        r
        for r in caplog.records
        if r.getMessage() == "Poise: weather forecast unavailable; using stale cache"
    ]
    assert [(r.name, r.levelno) for r in records] == [
        ("custom_components.poise.coordinator", logging.DEBUG)
    ]
