"""Phase 0 — Health-Emission bei Mid-Tick-Exception (Refactoring-Plan
``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md``, Befund 13:
"Health-Emissions-Test: ein frueh im Tick gesetztes/geloeschtes Repair-Issue
bleibt auch dann emittiert, wenn ein spaeterer Pipeline-Schritt mit Exception
abbricht (heutiges Sofort-Emissionsverhalten); F12-Zaehlung/Re-Raise
unveraendert.").

Eingefrorenes Ist-Verhalten (coordinator.py, Zeilennummern Stand heute):

* ``_issue`` (Z. 1274-1296) schreibt SOFORT ins issue_registry (create/delete
  auf Transition) — es gibt keinen End-of-Tick-Commit. Ein frueh im Tick
  emittiertes Issue ueberlebt daher jeden spaeteren Abbruch des Ticks.
* Fruehe Emissionspunkte in ``_run_once``: window_sensor_unavailable
  (Z. 2093-2099, direkt nach ``_window_open``) und
  mould_protection_inactive (Z. 2216-2221).
* Spaete, NICHT try-gekapselte Schritte, die den Tick zum Scheitern bringen:
  ``comfort_decide`` (Z. 2402) und ``resolve_write_target`` (Z. 2494) — beide
  Modul-Attribute von ``custom_components.poise.coordinator`` und damit eng
  patchbar.
* F12-Wrapper ``_async_update_data`` (Z. 1814-1850): Exception aus
  ``_run_once`` inkrementiert ``_tick_failures`` (Z. 1828), raist
  ``tick_failing_{entry_id}`` ab 3 Fehlschlaegen in Folge (Z. 1829-1833),
  re-raist unveraendert; ein Erfolg setzt den Zaehler zurueck und loescht das
  Issue (Z. 1835-1838).

Ergaenzung zu ``tests/integration/test_tick_failing_issue.py`` (dort wird
``_run_once`` KOMPLETT ersetzt, es gibt also keine Partial-Emission): hier
schlaegt der Tick MITTEN im echten ``_run_once`` fehl, NACH der fruehen
Issue-Emission — gezeigt wird nur der Partial-Emission-Aspekt der
F12-Zaehlung, nicht erneut die Schwelle selbst.
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
    # Service-Recorder erst NACH dem Setup registrieren (Plattform-Forwarding
    # wuerde einen frueheren Mock ueberschreiben — Muster der Bestandstests).
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data
    coord._clock = _FakeClock(1000.0)
    return entry


def _issue_get(hass: HomeAssistant, issue_id: str) -> Any:
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def _failed_tick(hass: HomeAssistant, coord: Any) -> None:
    """One refresh that must end in a failed tick (exception re-raised into
    DataUpdateCoordinator, swallowed there into last_update_success=False)."""
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is False


async def test_window_issue_set_early_survives_midtick_exception(
    hass: HomeAssistant,
) -> None:
    """Das frueh im Tick (Z. 2093-2099) gesetzte window_sensor-Issue steht im
    Registry, obwohl derselbe Tick spaeter (comfort_decide, Z. 2402) crasht."""
    entry = await _setup(hass, **{CONF_WINDOW_SENSOR: WINDOW})
    coord: Any = entry.runtime_data
    issue_id = f"window_sensor_unavailable_{entry.entry_id}"
    assert _issue_get(hass, issue_id) is None  # healthy setup: no issue

    hass.states.async_set(WINDOW, "unavailable", {})
    with patch(
        "custom_components.poise.coordinator.comfort_decide",
        side_effect=RuntimeError("injected mid-tick failure"),
    ):
        await _failed_tick(hass, coord)

    # Sofort-Emission: das Issue wurde VOR dem Crash geschrieben und bleibt.
    assert _issue_get(hass, issue_id) is not None


async def test_window_issue_cleared_early_stays_cleared_despite_midtick_exception(
    hass: HomeAssistant,
) -> None:
    """Gegenrichtung des Sofort-Emissionsverhaltens: ein frueh im Tick
    GELOESCHTES Issue (Sensor wieder da) bleibt geloescht, auch wenn der Tick
    danach crasht — es gibt keinen Rollback auf den Vortick-Stand."""
    entry = await _setup(hass, **{CONF_WINDOW_SENSOR: WINDOW})
    coord: Any = entry.runtime_data
    issue_id = f"window_sensor_unavailable_{entry.entry_id}"

    # erst das Issue etablieren (fehlschlagender Tick genuegt dafuer — s. o.)
    hass.states.async_set(WINDOW, "unavailable", {})
    with patch(
        "custom_components.poise.coordinator.comfort_decide",
        side_effect=RuntimeError("injected mid-tick failure"),
    ):
        await _failed_tick(hass, coord)
        assert _issue_get(hass, issue_id) is not None

        # der Sensor kommt zurueck; der Tick scheitert weiterhin mid-tick
        hass.states.async_set(WINDOW, "off", {"device_class": "window"})
        await _failed_tick(hass, coord)

    assert _issue_get(hass, issue_id) is None  # early clear survives the crash


async def test_mould_issue_set_early_survives_midtick_exception(
    hass: HomeAssistant,
) -> None:
    """Zweiter frueher Emissionspunkt (Z. 2216-2221): humidity-Sensor faellt aus
    -> mould_protection_inactive; der Tick crasht spaeter in
    resolve_write_target (Z. 2494) — das Issue steht trotzdem im Registry."""
    entry = await _setup(hass, **{CONF_HUMIDITY_SENSOR: HUMIDITY})
    coord: Any = entry.runtime_data
    issue_id = f"mould_protection_inactive_{entry.entry_id}"
    assert _issue_get(hass, issue_id) is None  # healthy setup: no issue

    hass.states.async_set(HUMIDITY, "unavailable", {})
    with patch(
        "custom_components.poise.coordinator.resolve_write_target",
        side_effect=RuntimeError("injected mid-tick failure"),
    ):
        await _failed_tick(hass, coord)

    assert _issue_get(hass, issue_id) is not None


async def test_f12_counting_unchanged_under_partial_emission(
    hass: HomeAssistant,
) -> None:
    """F12-Zaehlung beim Mid-Tick-Crash (Ergaenzung zu
    test_tick_failing_issue.py, das _run_once komplett ersetzt): auch wenn der
    Tick erst NACH der fruehen Issue-Emission scheitert, zaehlt der Wrapper
    (Z. 1825-1838) jeden Fehlschlag — 3 in Folge => tick_failing erscheint und
    KOEXISTIERT mit dem frueh emittierten mould-Issue; EIN Erfolg loescht nur
    tick_failing, das weiterhin wahre Sensor-Issue bleibt.

    Bewusst der HUMIDITY-Sensor als fruehes Issue (nicht der Fenstersensor):
    Fenstersensoren sind reaktiv ueberwacht (coordinator.py Z. 1193 --
    ``async_track_state_change_event`` auf temp/windows/actuator loest ein
    debounced ``async_request_refresh`` aus), d. h. der Statuswechsel selbst
    wuerde einen ZUSAETZLICHEN (hier ebenfalls fehlschlagenden) Tick einspeisen
    und die Zaehlung um eins verschieben. Der Humidity-Sensor wird nicht
    ueberwacht, also ist die Tick-Anzahl exakt die der expliziten Refreshes."""
    entry = await _setup(hass, **{CONF_HUMIDITY_SENSOR: HUMIDITY})
    coord: Any = entry.runtime_data
    tick_issue = f"tick_failing_{entry.entry_id}"
    mould_issue = f"mould_protection_inactive_{entry.entry_id}"

    hass.states.async_set(HUMIDITY, "unavailable", {})
    with patch(
        "custom_components.poise.coordinator.comfort_decide",
        side_effect=RuntimeError("injected mid-tick failure"),
    ):
        for _ in range(2):
            await _failed_tick(hass, coord)
        # 2 Fehlschlaege: unter der N=3-Schwelle, aber das fruehe Issue steht
        assert _issue_get(hass, tick_issue) is None
        assert _issue_get(hass, mould_issue) is not None

        await _failed_tick(hass, coord)
        # 3. Fehlschlag in Folge: tick_failing erscheint, beide koexistieren
        assert _issue_get(hass, tick_issue) is not None
        assert _issue_get(hass, mould_issue) is not None

    # Patch weg, Humidity-Sensor weiterhin unavailable: der Tick laeuft durch
    # (Sensor-Ausfall allein laesst den Tick nicht scheitern) — der Erfolg
    # loescht NUR tick_failing; das Sensor-Issue bleibt, solange es wahr ist.
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    assert _issue_get(hass, tick_issue) is None
    assert _issue_get(hass, mould_issue) is not None

    # Sensor kommt zurueck: der naechste erfolgreiche Tick loescht auch das.
    hass.states.async_set(
        HUMIDITY, "55", {"device_class": "humidity", "unit_of_measurement": "%"}
    )
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert _issue_get(hass, mould_issue) is None
