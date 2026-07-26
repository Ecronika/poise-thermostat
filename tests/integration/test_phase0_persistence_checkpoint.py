"""Phase 10 (F-SAVEPOINT): pin the NORMALISED position of the persistence
checkpoint relative to the rest of the tick.

Plan reference: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md,
Befund 12; ADR-0064.

Until phase 10 there were TWO checkpoint positions and both sat too early:

* the normal tick saved BEFORE ``finalize_tick``, so a save in tick N carried
  the PRE-tick state of ``multi_lifecycle`` / ``outcome_stats`` /
  ``hdh_savings`` / ``regulation_quality`` — the folds of the very tick that
  triggered the save landed on disk only one tick later;
* the unavailable tick flushed BEFORE the safe-state write, so that write's
  own ``has_actuated`` flip stayed pending.

F-SAVEPOINT collapsed both into ONE end-of-tick checkpoint. What is pinned
here now:

1. Normal tick: the save runs AFTER ``finalize_tick``, so its payload carries
   THIS tick's lifecycle fold and THIS tick's outcome/HDH/RegQ metrics.
2. ``has_actuated`` flow: a successful setpoint write still lands in the same
   tick's payload (it always preceded the checkpoint, and still does).
3. Unavailable tick: the dirty flush runs AFTER the safe-state write, so the
   user intent AND the safe write's ``has_actuated`` flip are persisted
   together — the tick leaves nothing pending.

Run (from the project root):
    ".venv-ha/Scripts/python.exe" -m pytest \
        tests/integration/test_phase0_persistence_checkpoint.py \
        -q --tb=short -p no:cacheprovider -o asyncio_mode=auto
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant, ServiceCall
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
    UNAVAILABLE_SAFE_AFTER_S,
)
from custom_components.poise.multi import lifecycle as lifecycle_mod
from custom_components.poise.multi.lifecycle import DeviceLifecycle

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
    """Deterministic monotonic clock (pattern: test_setpoint_adoption)."""

    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _set_room(
    hass: HomeAssistant,
    *,
    trv_state: str = "heat",
    setpoint: float = 20.0,
    room: float | str = 20.0,
    modes: list[str] | None = None,
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        trv_state,
        {
            "hvac_modes": modes or ["heat", "off"],
            "temperature": setpoint,
            "current_temperature": room if isinstance(room, float) else None,
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


def _capture_store_saves(coord: Any) -> list[dict[str, Any]]:
    """Record every payload handed to the per-room store, then delegate.

    Wraps ``coord._store.save`` (storage.PoiseStore.save) so ``_maybe_save``'s
    F6 semantics (clear ``_dirty`` only on success) stay exactly as in
    production — the real save still runs against the mocked hass storage.
    """
    saves: list[dict[str, Any]] = []
    orig = coord._store.save

    async def _recording_save(payload: dict[str, Any]) -> None:
        saves.append(copy.deepcopy(payload))
        await orig(payload)

    coord._store.save = _recording_save
    return saves


async def test_save_persists_this_tick_lifecycle_state(hass: HomeAssistant) -> None:
    """(1) Normal path, F-SAVEPOINT: the checkpoint runs AFTER
    ``finalize_tick``, so a dirty-triggered save in tick N persists the
    lifecycle state THIS tick folded — not the pre-tick one. The
    outcome/HDH/RegQ metrics come from the same finalize segment and are
    therefore consistent with it."""
    _set_room(hass, setpoint=20.0, room=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    # re-arm service recorders after setup (platform forwarding re-registers
    # the real handlers; harness finding 2026-07-02)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    coord.runtime.clock = _FakeClock(1000.0)
    coord._save_counter = 0

    pre_lifecycle = lifecycle_mod.to_dict(coord.runtime.compressor.multi_lifecycle)

    # the fold produces a recognisably NEW lifecycle state
    post_sentinel = DeviceLifecycle(last_mode="__post_fold_sentinel__")
    assert pre_lifecycle["last_mode"] != post_sentinel.last_mode

    def _sentinel_observe(state: DeviceLifecycle, **kwargs: Any) -> DeviceLifecycle:
        return post_sentinel

    saves = _capture_store_saves(coord)
    # a user-intent change marks the state dirty -> forces the tick's save
    coord.set_enabled(True)
    assert coord.runtime.dirty is True

    with patch.object(lifecycle_mod, "observe", _sentinel_observe):
        await coord.async_refresh()
        await hass.async_block_till_done()

    # the fold ran this tick and stored the new state on the coordinator...
    assert (
        coord.runtime.compressor.multi_lifecycle.last_mode == "__post_fold_sentinel__"
    )
    # ...and the save this same tick flushed carries exactly that state
    assert len(saves) >= 1
    payload = saves[0]
    assert payload["multi_lifecycle"]["last_mode"] == "__post_fold_sentinel__"
    assert payload["multi_lifecycle"] != pre_lifecycle
    # the metrics in the same payload are the post-finalize ones
    assert payload["outcome_stats"] == coord.runtime.diagnostics.outcome_stats.to_dict()
    assert payload["hdh_savings"] == coord.runtime.diagnostics.hdh.to_dict()
    assert payload["regulation_quality"] == coord.runtime.diagnostics.regq.to_dict()
    # the dirty flag was consumed by the successful save (F6)
    assert coord.runtime.dirty is False


async def test_first_successful_write_persists_has_actuated_same_tick(
    hass: HomeAssistant,
) -> None:
    """(2) has_actuated flow: the setpoint write's success stamp
    (``_mark_actuated`` flips ``dirty``) runs before the checkpoint — as it did
    before F-SAVEPOINT and still does now that the checkpoint moved to the end
    of the tick — so THIS tick's save payload already carries
    has_actuated=True."""
    _set_room(hass, setpoint=20.0, room=18.0)  # cold room -> a write is due
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    coord.runtime.clock = _FakeClock(1000.0)
    # rewind to the pre-first-actuation state (the setup tick already wrote):
    # this makes the next successful write the "first" one of the run again.
    coord.runtime.actuator.has_actuated = False
    coord.runtime.dirty = False
    coord._save_counter = 0
    saves = _capture_store_saves(coord)

    await coord.async_refresh()
    await hass.async_block_till_done()

    # a real setpoint write happened this tick and succeeded
    trv_writes = [c for c in set_temp if c.data.get("entity_id") == "climate.trv"]
    assert trv_writes, "expected a setpoint write this tick"
    assert coord.runtime.actuator.has_actuated is True
    # ``_mark_actuated`` (first flip) set dirty before the checkpoint, so the
    # SAME tick saved — and the payload already carries the flipped gate.
    assert len(saves) >= 1
    assert saves[0]["has_actuated"] is True
    assert coord.runtime.dirty is False  # flushed by this tick's save


async def test_unavailable_dirty_flush_follows_safe_state_write(
    hass: HomeAssistant,
) -> None:
    """(3) Unavailable path, F-SAVEPOINT: with a pending dirty flag and the
    safe-state timeout exceeded, ONE tick performs the safe-state write FIRST
    and flushes afterwards, so the payload carries both the user intent and the
    ``has_actuated`` flip that write produced. Nothing stays pending."""
    _set_room(hass, setpoint=20.0, room=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    coord.runtime.actuator.has_actuated = (
        False  # rewind: the safe write should be the 1st flip
    )
    coord.runtime.dirty = False
    coord._save_counter = 0

    # the device sits off @ 5.0 C -> resolve_safe_state will demand a heat
    # nudge AND the floor setpoint once the timeout lapses
    _set_room(hass, trv_state="off", setpoint=5.0, room="unavailable")
    hass.states.async_set("sensor.room_temp", "unavailable")

    # tick A: sensor loss starts the outage timer (no dirty, no timeout yet)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.data == {"available": False}
    assert coord.runtime.safety.unavailable_since == 1000.0

    # arm the SHARED ordered recorder: store saves, the safe-state write
    # (recorded at invocation time, so the order is deterministic even with
    # blocking=False service dispatch), and the climate service handlers.
    events: list[tuple[str, Any]] = []

    orig_save = coord._store.save

    async def _rec_save(payload: dict[str, Any]) -> None:
        events.append(("store_save", copy.deepcopy(payload)))
        await orig_save(payload)

    coord._store.save = _rec_save

    orig_safe = coord._write_unavailable_safe_state

    async def _rec_safe() -> None:
        events.append(("safe_state_write", None))
        await orig_safe()

    coord._write_unavailable_safe_state = _rec_safe

    async def _rec_climate(call: ServiceCall) -> None:
        events.append(("climate", call.service))

    hass.services.async_register("climate", "set_hvac_mode", _rec_climate)
    hass.services.async_register("climate", "set_temperature", _rec_climate)

    # tick B: timeout exceeded AND a pending user intent (set_enabled -> dirty)
    clock.t = 1000.0 + UNAVAILABLE_SAFE_AFTER_S + 1.0
    coord.set_enabled(True)
    assert coord.runtime.dirty is True

    await coord.async_refresh()
    await hass.async_block_till_done()

    kinds = [k for k, _ in events]
    # exactly ONE save this tick: the end-of-tick dirty flush
    assert kinds.count("store_save") == 1
    save_idx = kinds.index("store_save")
    safe_idx = kinds.index("safe_state_write")
    climate_idxs = [i for i, k in enumerate(kinds) if k == "climate"]
    # ordering: safe-state write + its calls FIRST, then the flush
    assert safe_idx < save_idx, f"the safe write must precede the flush: {kinds}"
    assert climate_idxs, "the safe-state write dispatched no climate calls"
    assert all(i < save_idx for i in climate_idxs), f"order violated: {kinds}"
    # the safe write really nudged heat and wrote the floor
    climate_services = [v for k, v in events if k == "climate"]
    assert "set_hvac_mode" in climate_services
    assert "set_temperature" in climate_services

    # the flushed payload is the POST-safe-write state: the intent AND the
    # has_actuated flip the safe write produced go to disk together
    payload = events[save_idx][1]
    assert payload["enabled"] is True
    assert payload["has_actuated"] is True
    assert coord.runtime.actuator.has_actuated is True
    assert coord.runtime.dirty is False  # nothing left pending
    # the unavailable-safe tick still reports the minimal payload
    assert coord.data == {"available": False, "unavailable_safe": True}
