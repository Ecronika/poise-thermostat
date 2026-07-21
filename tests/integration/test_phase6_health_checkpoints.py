"""Phase 6a (S4) — HealthUpdate-Checkpoints + ``TickStageError``-Transport
(Refactoring-Plan ``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md``,
Befund 13).

Ergaenzung zu ``test_phase0_health_emission.py``: dort crasht der Tick NACH
den sammelnden Stages (comfort_decide/resolve_write_target) — die
Stage-End-Checkpoints haben dann bereits emittiert und die Phase-0-Pins
beweisen genau das. HIER bricht der Tick IN einer sammelnden Stage ab,
NACH der Update-Sammlung und VOR dem Stage-End-Checkpoint: die Stage muss
die bereits faelligen Updates per ``TickStageError(cause,
pending_health_updates)`` heraustransportieren, ``_run_once`` emittiert sie
am Abbruch-Checkpoint und re-raist die ORIGINAL-Exception — die
F12-Zaehlung in ``_async_update_data`` und der DataUpdateCoordinator sehen
die unveraenderte Klasse (``coordinator.last_exception``).

Injektionspunkte (Modul-Attribute von ``custom_components.poise.
coordinator``, gleiche Technik wie die Phase-0-Pins):

* ``effective_window_open`` — in ``_stage_observe`` NACH der Sammlung von
  window_sensor_unavailable -> Transport-Pfad der Observe-Stage.
* ``ingest_temperature`` — in ``_stage_ingest`` NACH der Sammlung der
  sieben Geraete-Health-Updates -> Transport-Pfad der Ingest-Stage.
* ``psychro_dewpoint`` — in ``_stage_safety_floors`` VOR der Sammlung von
  mould_protection_inactive -> leerer Pending-Puffer, der Abbruch muss
  BARE propagieren (byte-identischer Fehlerpfad, kein Transport-Wrap).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

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
    CONF_HUMIDITY_SENSOR,
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
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}

WINDOW = "binary_sensor.window"
HUMIDITY = "sensor.room_rh"


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _healthy_states(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "18.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 19.0,
            "current_temperature": 18.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, **extra: Any) -> MockConfigEntry:
    """Set up with every configured sensor healthy so the first tick succeeds."""
    _healthy_states(hass)
    data = {**ROOM_DATA, **extra}
    if CONF_WINDOW_SENSOR in data:
        hass.states.async_set(WINDOW, "off", {"device_class": "window"})
    if CONF_HUMIDITY_SENSOR in data:
        hass.states.async_set(
            HUMIDITY, "55", {"device_class": "humidity", "unit_of_measurement": "%"}
        )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data
    coord._clock = _FakeClock(1000.0)
    return entry


def _issue_get(hass: HomeAssistant, issue_id: str) -> Any:
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def _failed_tick(hass: HomeAssistant, coord: Any) -> None:
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is False


async def test_observe_midstage_abort_transports_set_direction(
    hass: HomeAssistant,
) -> None:
    """Abbruch IN ``_stage_observe`` (effective_window_open), nach der
    Sammlung von window_sensor_unavailable: das Update erreicht das Registry
    ueber den Transport-Pfad, und der Coordinator re-raist die ORIGINAL-
    Exception (nicht ``TickStageError``)."""
    entry = await _setup(hass, **{CONF_WINDOW_SENSOR: WINDOW})
    coord: Any = entry.runtime_data
    issue_id = f"window_sensor_unavailable_{entry.entry_id}"
    assert _issue_get(hass, issue_id) is None

    hass.states.async_set(WINDOW, "unavailable", {})
    with patch(
        "custom_components.poise.coordinator.effective_window_open",
        side_effect=RuntimeError("injected in-stage failure"),
    ):
        await _failed_tick(hass, coord)

    # Transport: heute (inline) war das Issue vor dem Crash geschrieben;
    # mit Checkpoint-Emission MUSS der TickStageError-Pfad es liefern.
    assert _issue_get(hass, issue_id) is not None
    # Re-Raise des Originals: F12/DataUpdateCoordinator sehen RuntimeError.
    assert isinstance(coord.last_exception, RuntimeError)
    assert "injected in-stage failure" in str(coord.last_exception)


async def test_observe_midstage_abort_transports_clear_direction(
    hass: HomeAssistant,
) -> None:
    """Loesch-Richtung durch den Transport: der Sensor kommt zurueck, die
    Stage bricht weiterhin ab — das frueh gesammelte Clear-Update wird am
    Abbruch-Checkpoint emittiert (kein Rollback auf den Vortick-Stand)."""
    entry = await _setup(hass, **{CONF_WINDOW_SENSOR: WINDOW})
    coord: Any = entry.runtime_data
    issue_id = f"window_sensor_unavailable_{entry.entry_id}"

    hass.states.async_set(WINDOW, "unavailable", {})
    with patch(
        "custom_components.poise.coordinator.effective_window_open",
        side_effect=RuntimeError("injected in-stage failure"),
    ):
        await _failed_tick(hass, coord)
        assert _issue_get(hass, issue_id) is not None

        hass.states.async_set(WINDOW, "off", {"device_class": "window"})
        await _failed_tick(hass, coord)

    assert _issue_get(hass, issue_id) is None


async def test_ingest_midstage_abort_transports_guard_updates(
    hass: HomeAssistant,
) -> None:
    """Abbruch IN ``_stage_ingest`` (ingest_temperature), nach der Sammlung
    der sieben Geraete-Health-Updates: actuator_unavailable erreicht das
    Registry ueber den Transport-Pfad der Ingest-Stage."""
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    issue_id = f"actuator_unavailable_{entry.entry_id}"
    assert _issue_get(hass, issue_id) is None

    hass.states.async_set("climate.trv", "unavailable", {})
    with patch(
        "custom_components.poise.coordinator.ingest_temperature",
        side_effect=RuntimeError("injected ingest failure"),
    ):
        await _failed_tick(hass, coord)

    assert _issue_get(hass, issue_id) is not None
    assert isinstance(coord.last_exception, RuntimeError)


async def test_empty_pending_abort_propagates_bare(hass: HomeAssistant) -> None:
    """Abbruch VOR der ersten Sammlung einer Stage (psychro_dewpoint in
    ``_stage_safety_floors``): nichts pending -> die Stage propagiert die
    Original-Exception BARE (kein Transport-Wrap, byte-identischer
    Fehlerpfad); es wird nichts emittiert — exakt wie das alte Inline-
    Verhalten, wo die Emission ebenfalls nach dem Taupunkt-Aufruf sass."""
    entry = await _setup(hass, **{CONF_HUMIDITY_SENSOR: HUMIDITY})
    coord: Any = entry.runtime_data
    issue_id = f"mould_protection_inactive_{entry.entry_id}"

    with patch(
        "custom_components.poise.coordinator.psychro_dewpoint",
        side_effect=RuntimeError("injected dewpoint failure"),
    ):
        await _failed_tick(hass, coord)

    assert _issue_get(hass, issue_id) is None
    assert isinstance(coord.last_exception, RuntimeError)
    assert "injected dewpoint failure" in str(coord.last_exception)
