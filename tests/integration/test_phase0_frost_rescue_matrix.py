"""Phase 0 — Frost-Rescue-Post-Action-Matrix (Befunde 6+9).

Plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md, Abschnitt 6
Phase 0, Punkt "Frost-Rescue-Post-Action-Matrix (Befunde 6+9): alle vier
Kombinationen (Nudge Ok/Fehler x Write Ok/Fehler) -> Hold-State geloescht,
``dirty=True``, ``OverrideEnded('frost_rescue')`` nach den Write-Versuchen —
nie an ``execution.success`` gekoppelt".

Eingefrorenes Ist-Verhalten (coordinator.py, Zeilennummern Stand 2026-07-18):

* Z. 3270-3326: der Disabled/Off-Hold-Rescue-Pfad hat ZWEI GETRENNTE
  Try-Bloecke — Mode-Nudge (Z. 3287-3301) und Floor-Write (Z. 3302-3319).
  Ein Nudge-Fehler ueberspringt den Floor-Write nicht (Befund 11).
* Z. 3324-3325: ``_end_hold('frost_rescue')`` steht AUSSERHALB beider
  Try-Bloecke und ist NUR an ``_off_held`` gekoppelt, nie an den Erfolg der
  Writes: der Hold endet in allen vier Matrix-Zellen.
* ``_end_hold`` (Z. 765-775) loescht die komplette Hold-Lifecycle
  (``_mode_override``/``_override_expires_at``/...), setzt ``_dirty = True``
  und feuert ``poise_override_ended`` (reason='frost_rescue') via
  ``_fire_override_ended`` (Z. 750-763) — also NACH den Write-Versuchen
  (Event-Reihenfolge, Befund 6).
* Rescue-Vorbedingungen (Z. 3253-3279): ``_off_held`` (Z. 2807) UND ein
  Rescue-Target (Raum <= FROST_FLOOR_C fuer eine off-gehaltene Zone,
  Z. 3253-3257; Geraet inaktiv/unter dem Floor, tick_resolve Z. 354-378)
  UND ``_actuator_online`` (Z. 2434, 3279).

Fehler-Injektion: eigene ``climate.set_hvac_mode``/``set_temperature``-Handler,
die je nach Matrix-Zelle werfen. Beide Rescue-Calls laufen mit
``blocking=False`` (Z. 3292, actuator.py Z. 56); HA startet den Handler eager
(synchron bis zum ersten echten Suspend, core.py ``eager_start=True``), d. h.
die Aufzeichnung in der gemeinsamen Liste passiert deterministisch WAEHREND
des jeweiligen ``await`` im Koordinator — vor dem Event. Ein werfender
Handler wird dabei von HAs ``_run_service_call_catch_exceptions`` geschluckt
und geloggt; die Except-Zweige des Koordinators (Z. 3298/3316) fangen nur
synchrone Dispatch-Fehler. Fuer die Matrix ist genau das das Ist-Verhalten:
der Hold endet unabhaengig vom Schicksal beider Calls.

Konventionen wie tests/integration/test_mode_adoption.py /
test_frost_rescue_disabled.py: MockConfigEntry + async_setup, Recorder NACH
dem Setup registriert (die Climate-Plattform ersetzt frueher registrierte
Mocks), deterministische Zeit via FakeClock, ``async_refresh`` = ein Tick.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
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
    DOMAIN,
    FROST_FLOOR_C,
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
    CONF_OPTIMAL_START: False,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _set_states(hass: HomeAssistant, *, room: float, sp: float, state: str) -> None:
    """Room sensor + heat-capable TRV (mock states, kein echtes Geraet)."""
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        state,
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


@pytest.mark.parametrize(
    ("nudge_fails", "write_fails"),
    [(False, False), (False, True), (True, False), (True, True)],
    ids=["both_ok", "write_fails", "nudge_fails", "both_fail"],
)
async def test_frost_rescue_ends_off_hold_in_all_four_write_outcome_cells(
    hass: HomeAssistant, nudge_fails: bool, write_fails: bool
) -> None:
    """Off-Hold + Raum unter dem Frost-Floor: der Rescue-Tick versucht IMMER
    Nudge UND Floor-Write (zwei getrennte Trys) und beendet den Hold DANACH —
    unabhaengig davon, ob einer der beiden Calls (oder beide) fehlschlaegt."""
    # Setup-Tick mit Standard-Mocks (die Plattform-Registrierung wuerde frueher
    # registrierte Handler ersetzen — Injektion daher erst NACH dem Setup).
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_states(hass, room=5.0, sp=5.0, state="off")
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock

    # Aktiver Off-Mode-Hold mit echter Hold-Lifecycle (wie test_mode_adoption:
    # ueber den Produktionspfad, damit die Wall-Clock-Expiry real ist und der
    # Tick-Start-Expiry-Check den Hold nicht vorab loescht).
    coord._set_mode_override("off")
    assert coord._mode_override == "off"
    assert coord._override_expires_at is not None
    # ``_set_mode_override`` setzt selbst ``_dirty`` — zuruecksetzen, damit der
    # Dirty-Check unten das Hold-Ende dieses Ticks misst, nicht das Seeding.
    coord._dirty = False

    # Gemeinsame Aufzeichnungsliste: Service-Handler UND Bus-Listener appenden
    # hinein — die Reihenfolge der Eintraege IST die beobachtete Reihenfolge
    # (Calls laufen eager-synchron im jeweiligen await, das Event synchron in
    # ``_end_hold``).
    log: list[tuple[Any, ...]] = []

    async def _hvac_handler(call: ServiceCall) -> None:
        log.append(("call", "set_hvac_mode", call.data.get("hvac_mode")))
        if nudge_fails:
            raise HomeAssistantError("injected: set_hvac_mode backend failure")

    async def _temp_handler(call: ServiceCall) -> None:
        log.append(("call", "set_temperature", call.data.get("temperature")))
        if write_fails:
            raise HomeAssistantError("injected: set_temperature backend failure")

    # Re-Arm nach dem Setup: ueberschreibt die Plattform-Handler der Domain.
    hass.services.async_register("climate", "set_hvac_mode", _hvac_handler)
    hass.services.async_register("climate", "set_temperature", _temp_handler)

    @callback
    def _on_override_ended(event: Any) -> None:
        # ``_dirty`` hier festhalten: direkt nach dem Event laeuft
        # ``_maybe_save`` (Z. 3327) und setzt das Flag bei Erfolg zurueck.
        log.append(("event", event.data.get("reason"), coord._dirty))

    unsub = hass.bus.async_listen("poise_override_ended", _on_override_ended)

    # Der Rescue-Tick: Zone enabled, Off-Hold aktiv, Raum 5.0 < FROST_FLOOR_C,
    # Geraet off/unter dem Floor, Aktor online ("off" != "unavailable").
    clock.t += 60.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    unsub()

    # 1) Hold-State in ALLEN vier Zellen geloescht (Z. 3324-3325 + _end_hold).
    assert coord._mode_override is None
    assert coord._override is None
    assert coord._override_expires_at is None
    assert coord._override_set_wall is None
    assert coord._override_reason is None

    # 2) Genau ein 'poise_override_ended' mit reason='frost_rescue', und
    #    ``_dirty`` war zum Event-Zeitpunkt True (Befund 6: _end_hold markiert
    #    den Flush, der Checkpoint Z. 3327 persistiert ihn direkt danach).
    events = [e for e in log if e[0] == "event"]
    assert events == [("event", "frost_rescue", True)], f"log={log!r}"

    # 3) Beide Write-Versuche fanden statt — der Nudge-Fehler ueberspringt den
    #    Floor-Write nicht (zwei getrennte Trys, Befund 11) — und zwar VOR dem
    #    Event (Reihenfolge ueber die gemeinsame Liste).
    calls = [e for e in log if e[0] == "call"]
    assert ("call", "set_hvac_mode", "heat") in calls, f"log={log!r}"
    assert ("call", "set_temperature", FROST_FLOOR_C) in calls, f"log={log!r}"
    assert len(calls) == 2, f"unerwartete Zusatz-Calls: {log!r}"
    event_idx = log.index(events[0])
    call_idxs = [i for i, e in enumerate(log) if e[0] == "call"]
    assert all(i < event_idx for i in call_idxs), (
        f"Hold-Ende feuerte vor einem Write-Versuch: log={log!r}"
    )
    # Nudge vor Setpoint-Write (Ausfuehrungsreihenfolge Z. 3287 vor Z. 3302).
    assert [e[1] for e in calls] == ["set_hvac_mode", "set_temperature"]
