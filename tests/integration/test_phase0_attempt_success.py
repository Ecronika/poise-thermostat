"""Phase 0 (Refactoring-Plan coordinator, Befund 9): Attempt- vs. Success-Stempel
des Setpoint-Writes, eingefroren am HEUTIGEN Verhalten.

Plan: ``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md`` — Phase-0-Punkt
"Attempt-vs-Success-State-Tests (Befund 9)": ein fehlgeschlagener Setpoint-Write
aktualisiert ``pre_write_sp`` und registriert die Context-ID, aber NICHT
``last_written_sp``/``last_sp_write_ts``/``has_actuated``; mehrere Aktionen pro
Tick committen in Ausführungsreihenfolge (Mode vor Setpoint).

Verankerte ``coordinator.py``-Stellen (Zeilennummern Stand Phase 0):

* 3164–3190 — Setpoint-Write-Block. Attempt-Stempel VOR dem ``await``:
  ``_pre_write_sp = actual_sp`` (Z. 3179) und die Context-ID via ``_own_ctx()``
  (Z. 3182, Registrierung Z. 1661–1662). Success-Stempel NUR nach erfolgreichem
  ``await``: ``_last_written_mode``/``_last_sp_write_ts``/``_last_written_sp``/
  ``_mark_actuated`` (Z. 3183–3186).
* 3187 — ``except Exception``: "never let actuator I/O kill the tick" — der Tick
  bleibt erfolgreich (``last_update_success`` True), der Fehler wird nur geloggt.
* 2942–2964 — Mode-Nudge-Servicecall; er steht im Code VOR dem Setpoint-Write,
  also müssen aufgezeichnete Calls eines Ticks ``set_hvac_mode`` VOR
  ``set_temperature`` zeigen (Reihenfolge-Invariante für das künftige geordnete
  ``ExecutionReport``, Plan Phase 5B).
* 1738–1750 / 1721–1736 — ``_mark_actuated`` setzt beim ERSTEN Flip ``_dirty``;
  der ``_maybe_save``-Checkpoint desselben Ticks (Z. 3327–3328) flusht das
  Payload-Feld ``has_actuated`` (Befund 12-Querbezug).

Fehler-Injektion: ``unittest.mock.patch.object`` auf ``actuator_mod.write``
(Modul-Alias des Coordinators, Import Z. 31). Ein via ``async_register``
registrierter werfender ``climate.set_temperature``-Handler kann diesen Pfad
NICHT treffen: der Coordinator ruft mit ``blocking=False``, Handler-Exceptions
laufen dann in einem fire-and-forget-Task und erreichen das ``except`` Z. 3187
nie — deshalb die enge Injektion direkt auf der awaiteten Write-Funktion.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

import custom_components.poise.actuator as actuator_mod
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
    SETPOINT_ADOPT_ECHO_WINDOW_S,
)
from custom_components.poise.control.tick_resolve import snap_to_step

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


def _set_trv(
    hass: HomeAssistant,
    *,
    state: str = "heat",
    setpoint: float = 20.0,
    room: float = 20.0,
    modes: list[str] | None = None,
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": modes or ["heat", "off"],
            "temperature": setpoint,
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


def _seed_written_baseline(coord: Any, *, device_sp: float) -> _FakeClock:
    """Deterministic post-setup baseline: Poise 'commanded' ``device_sp`` long ago.

    Device == last command -> the adoption detector sees no external change, the
    echo window is closed, and the ~1 K gap to the schedule target creates the
    write need (deadband 0.2 exceeded). Success-side stamps are reset so both the
    failure and the success case can prove whether the tick under test advanced
    them.
    """
    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_written_sp = device_sp
    coord._last_sp_write_ts = 1000.0
    coord._prev_device_sp = device_sp
    coord._pre_write_sp = 15.0  # sentinel: proves the attempt stamp of THIS tick
    coord._has_actuated = False  # reset the success-side gate (setup tick wrote)
    coord._dirty = False
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0  # echo window closed
    return clock


async def test_failed_write_stamps_attempt_but_not_success(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Fall A: der Actuator-Write wirft -> Attempt-Stempel (``_pre_write_sp``,
    Context-ID) sind gesetzt, die Success-Stempel (Z. 3183–3186) NICHT, und der
    Tick selbst bleibt erfolgreich (Z. 3187)."""
    _set_trv(hass, setpoint=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    # re-arm after setup (platform forwarding re-registers the real handlers)
    nudges = async_mock_service(hass, "climate", "set_hvac_mode")

    clock = _seed_written_baseline(coord, device_sp=20.0)
    mode_before = coord._last_written_mode
    ctx_before = len(coord._own_write_ctx_ids)

    with patch.object(
        actuator_mod, "write", side_effect=HomeAssistantError("injected write failure")
    ) as mock_write:
        await coord.async_refresh()
        await hass.async_block_till_done()

    # the injected failure actually travelled the setpoint-write path
    assert mock_write.call_count == 1
    assert "actuator write failed" in caplog.text  # the Z. 3188 log site

    # Attempt stamps: taken BEFORE the await, so they survive the failure.
    assert coord._pre_write_sp == 20.0  # Z. 3179 (was 15.0 sentinel)
    assert nudges == []  # device already 'heat' -> no mode nudge this tick ...
    # ... so exactly the failed write registered its Context-ID (Z. 1661–1662)
    assert len(coord._own_write_ctx_ids) == ctx_before + 1

    # Success stamps: NOT advanced by the failed write (Z. 3183–3186 skipped).
    assert coord._last_written_sp == 20.0  # unchanged seed, not snap(target)
    assert coord._last_sp_write_ts == 1000.0  # not re-stamped to clock.t
    assert coord._last_written_mode == mode_before
    assert coord._has_actuated is False

    # Z. 3187: never let actuator I/O kill the tick.
    assert coord.last_update_success is True
    assert clock.t == coord._clock.monotonic()  # tick ran under the fake clock


async def test_successful_write_stamps_success_and_flushes_dirty(
    hass: HomeAssistant,
) -> None:
    """Fall B: erfolgreicher Write -> alle Success-Stempel gesetzt
    (``_last_written_sp == snap_to_step(target)``, ``_last_sp_write_ts == now``,
    ``_has_actuated`` True) und das ``_mark_actuated``-Dirty wird vom
    ``_maybe_save``-Checkpoint DESSELBEN Ticks geflusht (Z. 3327–3328)."""
    _set_trv(hass, setpoint=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    setpoints = async_mock_service(hass, "climate", "set_temperature")  # after setup
    nudges = async_mock_service(hass, "climate", "set_hvac_mode")

    clock = _seed_written_baseline(coord, device_sp=20.0)
    coord._last_written_mode = None  # sentinel: success must stamp final_mode
    ctx_before = len(coord._own_write_ctx_ids)

    # spy on the store to observe the same-tick dirty flush (behaviour untouched)
    orig_save = coord._store.save
    saves: list[dict[str, Any]] = []

    async def _spy_save(payload: dict[str, Any]) -> None:
        saves.append(payload)
        await orig_save(payload)

    with patch.object(coord._store, "save", new=_spy_save):
        await coord.async_refresh()
        await hass.async_block_till_done()

    trv_writes = [c for c in setpoints if c.data.get("entity_id") == "climate.trv"]
    assert len(trv_writes) == 1, f"expected exactly one write: {setpoints}"
    written = trv_writes[0].data["temperature"]
    assert isinstance(written, float)

    # Attempt stamps are taken on the success path too.
    assert coord._pre_write_sp == 20.0  # Z. 3179 (was 15.0 sentinel)
    assert nudges == []  # no mode nudge -> the write owns the single new ctx id
    assert len(coord._own_write_ctx_ids) == ctx_before + 1

    # Success stamps (Z. 3183–3186): the raw target goes on the wire, the
    # SNAPPED target (device step 0.5) becomes the echo baseline.
    assert coord._last_written_sp == snap_to_step(written, 0.5)
    assert coord._last_sp_write_ts == clock.t
    assert coord._last_written_mode is not None
    assert coord._has_actuated is True
    assert coord.last_update_success is True

    # _mark_actuated (Z. 1738–1750) set _dirty on the first flip; the same tick's
    # _maybe_save checkpoint (Z. 3327–3328) flushed it with has_actuated=True.
    assert any(p.get("has_actuated") is True for p in saves), (
        f"no same-tick flush of has_actuated: {[list(p) for p in saves]}"
    )
    assert coord._dirty is False


async def test_mode_nudge_call_precedes_setpoint_write(hass: HomeAssistant) -> None:
    """Fall C: ein Tick mit Mode-Nudge (Z. 2942–2964) UND Setpoint-Write
    (Z. 3164–3190) dispatcht ``set_hvac_mode`` VOR ``set_temperature`` — die
    Reihenfolge, die das geordnete ``ExecutionReport`` (Plan Phase 5B) exakt
    erhalten muss."""
    # heat-capable device sitting in 'off' on an enabled zone: desired 'heat'
    # -> nudge; setpoint 15.0 vs. schedule target -> deadband exceeded -> write.
    # (First tick never adopts 'off' as a K2 hold: no commanded-mode baseline,
    # detect_external_mode 'No baseline' guard; the post-setup tick is inside
    # the mode echo window, so it is not adopted either.)
    _set_trv(hass, state="off", setpoint=15.0, room=18.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # one shared recorder for BOTH climate services, so ordering is observable
    order: list[tuple[str, dict[str, Any]]] = []

    async def _rec_mode(call: ServiceCall) -> None:
        order.append(("set_hvac_mode", dict(call.data)))

    async def _rec_temp(call: ServiceCall) -> None:
        order.append(("set_temperature", dict(call.data)))

    hass.services.async_register("climate", "set_hvac_mode", _rec_mode)
    hass.services.async_register("climate", "set_temperature", _rec_temp)

    assert coord._mode_override is None  # 'off' was not grabbed as a K2 hold
    await coord.async_refresh()
    await hass.async_block_till_done()

    names = [n for n, _ in order]
    assert "set_hvac_mode" in names, f"no mode nudge recorded: {order}"
    assert "set_temperature" in names, f"no setpoint write recorded: {order}"
    assert names.index("set_hvac_mode") < names.index("set_temperature"), (
        f"mode nudge must be dispatched before the setpoint write: {order}"
    )
    by_name = dict(order[::-1])  # first occurrence wins after reversal
    assert by_name["set_hvac_mode"]["hvac_mode"] == "heat"
    assert by_name["set_hvac_mode"]["entity_id"] == "climate.trv"
    assert by_name["set_temperature"]["entity_id"] == "climate.trv"
