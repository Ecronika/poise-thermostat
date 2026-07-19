"""Phase 0, Event-Reihenfolge (Befund 6) — Refactoring-Plan coordinator.py.

Friert die HEUTIGE chronologische Ordnung von ``poise_override_ended`` relativ
zu den Aktor-Writes eines Ticks ein (docs/Konzepte/
2026-07-18_Refactoring-Plan_coordinator.md, Phase-0-Punkt "Event-Reihenfolge-
Test (Befund 6): Expiry/Preheat-Hold-Ende vor den Aktor-Writes,
Frost-Rescue-Hold-Ende danach; set_override(None) feuert sofort").

Verankerte coordinator.py-Stellen (Zeilennummern Stand Plan-Datum):

* Expiry-Block 2248-2284: ``_expire_timed_states`` (777-813) laeuft frueh im
  Tick und feuert ein Hold-Ende (``_end_hold`` 765-775 ->
  ``_fire_override_ended`` 750-763) VOR dem Write-Pfad.
* Preheat-Hold-Ende 2315-2322 (``hold_ends_at_preheat``): ebenfalls VOR den
  Writes (Mode-Nudge 2942-2964, Setpoint-Write 3164-3190).
* Frost-Rescue 3270-3326: ``_end_hold('frost_rescue')`` steht bei 3324-3325
  NACH beiden Rescue-Write-Versuchen (Nudge 3287-3301, Floor-Write 3302-3319)
  und ist nur an ``_off_held`` gekoppelt, nicht an den Write-Erfolg (der
  Matrix-Aspekt liegt in der Frost-Rescue-Matrix; hier nur die Ordnung).
* ``set_override(None)`` bei aktivem Hold feuert das Event SOFORT im
  synchronen Aufruf (Z. 637-638), ganz ohne Tick.

Mechanik: eine gemeinsame Aufzeichnungsliste. Ein ``@callback``-Bus-Listener
auf ``poise_override_ended`` und eigene ``@callback``-Service-Handler fuer
``climate.set_temperature``/``set_hvac_mode`` appenden Marker in echter
Aufrufreihenfolge — HA 2024.12 fuehrt non-blocking Service-Calls eager aus
(``async_create_task_internal(..., eager_start=True)``), ein reiner Callback-
Handler laeuft also synchron innerhalb des ``await services.async_call`` und
Bus-Callbacks synchron innerhalb von ``async_fire``; die Marker-Reihenfolge
ist damit die tatsaechliche Ausfuehrungsreihenfolge.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import patch

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, ServiceCall, callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poise import coordinator as coordinator_mod
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
    CONF_OVERRIDE_POLICY,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    FROST_FLOOR_C,
    OVERRIDE_POLICY_SCHEDULE,
)


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
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        **extra,
    }


def _actuator(
    hass: HomeAssistant, *, state: str, sp: float, modes: list[str], room: float
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
            "hvac_modes": modes,
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, **extra: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_base(**extra), title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _arm_recorder(hass: HomeAssistant) -> list[tuple[Any, ...]]:
    """One chronological list: hold-ended events + climate writes, in call order.

    Registered AFTER setup: forwarding to the climate platform re-registers the
    real handlers, which would clobber a pre-setup registration (same re-arm
    rule as ``async_mock_service`` in the sibling suites).
    """
    order: list[tuple[Any, ...]] = []

    @callback
    def _on_ended(event: Any) -> None:
        order.append(("event", event.data.get("reason")))

    hass.bus.async_listen("poise_override_ended", _on_ended)

    def _recording_handler(service: str) -> Any:
        @callback
        def _handler(call: ServiceCall) -> None:
            order.append(("write", service, dict(call.data)))

        return _handler

    for svc in ("set_temperature", "set_hvac_mode"):
        hass.services.async_register("climate", svc, _recording_handler(svc))
    return order


def _event_idx(order: list[tuple[Any, ...]]) -> list[int]:
    return [i for i, m in enumerate(order) if m[0] == "event"]


def _write_idx(order: list[tuple[Any, ...]]) -> list[int]:
    return [
        i
        for i, m in enumerate(order)
        if m[0] == "write" and m[2].get("entity_id") == "climate.trv"
    ]


def _neutral_echo_baseline(coord: Any, device_sp: float) -> None:
    """Reset the setup tick's write stamps to a stable no-adoption baseline.

    The setup tick wrote via the real (pre-recorder) handlers and stamped
    ``_last_written_sp``/``_last_sp_write_ts`` with the real monotonic clock;
    after swapping in the FakeClock those stamps are meaningless. A stable
    ``_prev_device_sp == device_sp`` baseline keeps the adoption detector
    silent (stable-offset rule), so the test tick only exercises the ordering.
    """
    coord._last_written_sp = None
    coord._last_sp_write_ts = None
    coord._prev_device_sp = device_sp


async def test_expired_timed_hold_event_fires_before_actuator_writes(
    hass: HomeAssistant,
) -> None:
    """(1) Expiry-Block 2248-2284 liegt vor dem Write-Pfad: ein zum Tick-Start
    bereits abgelaufener timed Hold (wall-clock ``_override_expires_at`` in der
    Vergangenheit) feuert ``poise_override_ended`` BEVOR der Tick den
    Schedule-Setpoint zurueck auf den Aktor schreibt."""
    _actuator(hass, state="heat", sp=25.0, modes=["heat", "off"], room=18.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    coord._clock = _FakeClock(1000.0)
    _neutral_echo_baseline(coord, 25.0)

    coord.set_override(25.0)  # active hold, expiry announced at set-time
    assert coord._override == 25.0
    # wall-clock expiry in the past -> _expire_timed_states ends it on the tick
    coord._override_expires_at = dt_util.utcnow().timestamp() - 60.0
    order = _arm_recorder(hass)

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._override is None, "the expired hold must be gone after the tick"
    ev, wr = _event_idx(order), _write_idx(order)
    assert ev, f"no poise_override_ended fired: {order}"
    # always-comfort room -> no switchpoint -> the timer-fallback reason
    assert order[ev[0]][1] == "expired_timer"
    assert wr, (
        "the tick was expected to write the schedule target back onto the "
        f"device (sp 25.0 -> ~comfort): {order}"
    )
    assert ev[0] < wr[0], f"event must precede the actuator writes: {order}"


async def test_frost_rescue_hold_end_event_fires_after_rescue_writes(
    hass: HomeAssistant,
) -> None:
    """(2) Frost-Rescue 3270-3326: ``_end_hold('frost_rescue')`` (3324-3325)
    steht NACH beiden Rescue-Write-Versuchen — Mode-Nudge (3287) und
    Floor-Write (3302) landen zuerst in der Aufzeichnung, dann das Event."""
    # off-HELD zone is rescued only when the ROOM is at the frost floor (K2)
    _actuator(hass, state="off", sp=5.0, modes=["heat", "off"], room=5.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    coord._clock = _FakeClock(1000.0)

    # active user 'off' mode-hold with its announced (future) expiry; the tick
    # then routes through the disabled/frost-rescue branch (line 3241 else).
    coord._set_mode_override("off")
    assert coord._mode_override == "off"
    order = _arm_recorder(hass)

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._mode_override is None, "the rescue must have ended the off-hold"
    ev, wr = _event_idx(order), _write_idx(order)
    assert ev, f"no poise_override_ended fired: {order}"
    assert order[ev[0]][1] == "frost_rescue"
    # both rescue attempts happened: heat nudge + floor setpoint write
    nudges = [m for m in order if m[0] == "write" and m[1] == "set_hvac_mode"]
    floors = [m for m in order if m[0] == "write" and m[1] == "set_temperature"]
    assert nudges and nudges[0][2].get("hvac_mode") == "heat"
    floor_temps = [m[2]["temperature"] for m in floors]
    assert floors and all(t >= FROST_FLOOR_C for t in floor_temps)
    assert max(wr) < ev[0], f"event must come AFTER the rescue writes: {order}"


async def test_set_override_none_fires_immediately_outside_a_tick(
    hass: HomeAssistant,
) -> None:
    """(3) ``set_override(None)`` bei aktivem Hold (Z. 637-638): das Event
    feuert SOFORT im synchronen Aufruf — vor jedem ``await``, ohne Tick, und
    ohne dass irgendein Aktor-Write dazukommt."""
    _actuator(hass, state="heat", sp=21.0, modes=["heat", "off"], room=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    coord.set_override(24.0)
    assert coord._override == 24.0
    order = _arm_recorder(hass)

    coord.set_override(None)  # outside any tick; plain synchronous call

    # asserted BEFORE any await: the event is already on the record, alone
    assert order == [("event", "user_resume")]
    assert coord._override is None
    await hass.async_block_till_done()
    # ... and nothing trailing: no tick ran, no actuator writes were queued
    assert _write_idx(order) == []
    assert _event_idx(order) == [0]


async def test_preheat_hold_end_event_fires_before_actuator_writes(
    hass: HomeAssistant,
) -> None:
    """(4) Preheat-Kante 2315-2322: endet ein Schedule-Hold auf der steigenden
    Preheat-Flanke (``hold_ends_at_preheat`` -> ``_end_hold('schedule_point')``),
    feuert das Event VOR den Aktor-Writes des Ticks.

    Konstruktion: die echte Preheat-Flanke braucht ein identifiziertes
    EKF-Modell plus eine lauf-zeitabhaengige Schedule-Phase (flaky bei realer
    Wanduhr), deshalb wird eng injiziert: der echte ``plan_preheat`` laeuft,
    nur sein ``preheating``-Flag wird auf True gesetzt (Flanke, da
    ``_was_preheating`` False ist) und das ``expiry_is_switchpoint``-Gate
    geseedet (always-comfort kennt keinen Switchpoint). Die 'schedule'-Policy
    wird explizit konfiguriert — die ADR-0059-§7-Migration pinnt eine
    minor_version-1-Entry (MockConfigEntry-Default) sonst auf 'timer'. Der
    Held-Wert 18.0 liegt unter dem Preheat-Ziel 21.0.
    """
    _actuator(hass, state="heat", sp=18.0, modes=["heat", "off"], room=18.0)
    entry = await _setup(
        hass,
        **{CONF_OPTIMAL_START: True, CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_SCHEDULE},
    )
    coord: Any = entry.runtime_data
    coord._clock = _FakeClock(1000.0)
    _neutral_echo_baseline(coord, 18.0)

    coord.set_override(18.0)  # active hold below the preheat target
    assert coord._override == 18.0
    assert coord._override_policy == "schedule"  # explicitly configured above
    # always-comfort -> set_override computed a timer-fallback expiry; gate the
    # ADR-0059 §3 path by declaring it a real switchpoint expiry (seeded).
    coord._override_expiry_is_switchpoint = True
    assert not coord._was_preheating
    order = _arm_recorder(hass)

    real_plan = coordinator_mod.plan_preheat

    def _forced_preheat(**kwargs: Any) -> Any:
        return dataclasses.replace(
            real_plan(**kwargs), preheating=True, coasting=False
        )

    with patch.object(coordinator_mod, "plan_preheat", _forced_preheat):
        await coord.async_refresh()
        await hass.async_block_till_done()

    assert coord._override is None, "the hold must end at the preheat edge"
    ev, wr = _event_idx(order), _write_idx(order)
    assert ev, f"no poise_override_ended fired: {order}"
    assert order[ev[0]][1] == "schedule_point"
    assert wr, (
        "the tick was expected to write the preheat/comfort target "
        f"(sp 18.0 -> ~21): {order}"
    )
    assert ev[0] < wr[0], f"event must precede the actuator writes: {order}"
