"""Phase 0 (Refactoring-Plan coordinator.py 2026-07-18, Befund 12): pin the
POSITION of the persistence checkpoint relative to the rest of the tick.

Plan reference: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md,
Abschnitt 6 Phase 0, "Persistence-Checkpoint-Test (Befund 12)".

What is frozen here (coordinator.py line numbers, verified against the 3,827-line
file):

1. Normal (available) tick: the ``_maybe_save`` checkpoint at line 3327 runs
   BEFORE the compressor-lifecycle fold (``_lifecycle.observe``, lines
   3416-3457, call at 3443) and before the Outcome/HDH/RegQ folds (3516+).
   A save triggered in tick N therefore persists the PRE-tick (tick N-1)
   state of ``multi_lifecycle`` / ``outcome_stats`` / ``hdh_savings`` /
   ``regulation_quality`` — never the state this same tick is about to fold in.

2. ``has_actuated`` flow: a SUCCESSFUL setpoint write earlier in the same tick
   stamps its success state at lines 3183-3186, including ``_mark_actuated``
   (1738-1750: first flip sets ``_dirty``). Because that happens BEFORE the
   line-3327 checkpoint, the very tick of the first successful write already
   persists ``has_actuated=True``.

3. Unavailable tick (room sensor lost, safe-state timeout exceeded, lines
   1996-2040): the pending-dirty flush (2018-2019) runs BEFORE the safe-state
   write (``_write_unavailable_safe_state`` 1929-1986, called at 2038). The
   safe-state write's own ``_mark_actuated`` (line 1984) happens AFTER that
   flush and the branch returns immediately (minimal payload, 2039-2040), so
   the ``has_actuated`` flip from the safe-state write is NOT persisted in this
   tick — it stays pending as ``_dirty=True`` for a later save.

Phase-0 rule: these tests freeze TODAY's behaviour; they must be adapted to the
observed behaviour, never the production code.

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


async def test_save_persists_pre_tick_lifecycle_state(hass: HomeAssistant) -> None:
    """(1) Normal path: the line-3327 checkpoint runs BEFORE the lifecycle fold
    (line 3443), so a dirty-triggered save in tick N persists the PRE-tick
    ``multi_lifecycle`` state — even though the same tick then folds a
    recognisably NEW lifecycle state in. Outcome/HDH/RegQ are pinned the same
    way via pre-tick snapshots (their folds sit at 3516+, after the save)."""
    _set_room(hass, setpoint=20.0, room=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    # re-arm service recorders after setup (platform forwarding re-registers
    # the real handlers; harness finding 2026-07-02)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    coord._clock = _FakeClock(1000.0)
    coord._save_counter = 0

    # pre-tick snapshots of everything the plan says the save must see
    pre_lifecycle = lifecycle_mod.to_dict(coord._multi_lifecycle)
    pre_outcome = coord._outcome_stats.to_dict()
    pre_hdh = coord._hdh.to_dict()
    pre_regq = coord._regq.to_dict()

    # the fold (line 3443) will produce a recognisably NEW lifecycle state
    post_sentinel = DeviceLifecycle(last_mode="__post_fold_sentinel__")
    assert pre_lifecycle["last_mode"] != post_sentinel.last_mode

    def _sentinel_observe(state: DeviceLifecycle, **kwargs: Any) -> DeviceLifecycle:
        return post_sentinel

    saves = _capture_store_saves(coord)
    # a user-intent change marks the state dirty -> forces the tick's save
    coord.set_enabled(True)
    assert coord._dirty is True

    with patch.object(lifecycle_mod, "observe", _sentinel_observe):
        await coord.async_refresh()
        await hass.async_block_till_done()

    # the fold DID run this tick and stored the new state on the coordinator...
    assert coord._multi_lifecycle.last_mode == "__post_fold_sentinel__"
    # ...but the save that this same tick flushed carries the PRE-tick state:
    assert len(saves) >= 1
    payload = saves[0]
    assert payload["multi_lifecycle"] == pre_lifecycle
    assert payload["multi_lifecycle"]["last_mode"] != "__post_fold_sentinel__"
    # Outcome/HDH/RegQ folds also sit after the checkpoint -> pre-tick stands
    assert payload["outcome_stats"] == pre_outcome
    assert payload["hdh_savings"] == pre_hdh
    assert payload["regulation_quality"] == pre_regq
    # the dirty flag was consumed by the successful save (F6)
    assert coord._dirty is False


async def test_first_successful_write_persists_has_actuated_same_tick(
    hass: HomeAssistant,
) -> None:
    """(2) has_actuated flow: the setpoint write's success stamp (3183-3186,
    ``_mark_actuated`` at 3186 flips ``_dirty``) runs BEFORE the line-3327
    checkpoint, so THIS tick's save payload already carries has_actuated=True."""
    _set_room(hass, setpoint=20.0, room=18.0)  # cold room -> a write is due
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    coord._clock = _FakeClock(1000.0)
    # rewind to the pre-first-actuation state (the setup tick already wrote):
    # this makes the next successful write the "first" one of the run again.
    coord._has_actuated = False
    coord._dirty = False
    coord._save_counter = 0
    saves = _capture_store_saves(coord)

    await coord.async_refresh()
    await hass.async_block_till_done()

    # a real setpoint write happened this tick and succeeded
    trv_writes = [c for c in set_temp if c.data.get("entity_id") == "climate.trv"]
    assert trv_writes, "expected a setpoint write this tick"
    assert coord._has_actuated is True
    # ``_mark_actuated`` (first flip) set _dirty BEFORE the checkpoint, so the
    # SAME tick saved — and the payload already carries the flipped gate.
    assert len(saves) >= 1
    assert saves[0]["has_actuated"] is True
    assert coord._dirty is False  # flushed by this tick's save


async def test_unavailable_dirty_flush_precedes_safe_state_write(
    hass: HomeAssistant,
) -> None:
    """(3) Unavailable path: with a pending dirty flag and the safe-state
    timeout exceeded, ONE tick performs the dirty flush (2018-2019) BEFORE the
    safe-state write (2038). The ``has_actuated`` flip caused by that safe-state
    write (line 1984 -> ``_mark_actuated``) is NOT saved again in this tick
    (early return with the minimal payload, 2039-2040) — it stays pending."""
    _set_room(hass, setpoint=20.0, room=20.0)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._has_actuated = False  # rewind: the safe write should be the 1st flip
    coord._dirty = False
    coord._save_counter = 0

    # the device sits off @ 5.0 C -> resolve_safe_state will demand a heat
    # nudge AND the floor setpoint once the timeout lapses
    _set_room(hass, trv_state="off", setpoint=5.0, room="unavailable")
    hass.states.async_set("sensor.room_temp", "unavailable")

    # tick A: sensor loss starts the outage timer (no dirty, no timeout yet)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.data == {"available": False}
    assert coord._unavailable_since == 1000.0

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
    assert coord._dirty is True

    await coord.async_refresh()
    await hass.async_block_till_done()

    kinds = [k for k, _ in events]
    # exactly ONE save this tick: the pre-safe-write dirty flush
    assert kinds.count("store_save") == 1
    save_idx = kinds.index("store_save")
    safe_idx = kinds.index("safe_state_write")
    climate_idxs = [i for i, k in enumerate(kinds) if k == "climate"]
    # ordering: dirty flush FIRST, then the safe-state write + its calls
    assert save_idx < safe_idx, f"flush must precede the safe write: {kinds}"
    assert climate_idxs, "the safe-state write dispatched no climate calls"
    assert all(save_idx < i for i in climate_idxs), f"order violated: {kinds}"
    # the safe write really nudged heat and wrote the floor
    climate_services = [v for k, v in events if k == "climate"]
    assert "set_hvac_mode" in climate_services
    assert "set_temperature" in climate_services

    # the flushed payload is the PRE-safe-write state: intent persisted,
    # has_actuated still False
    payload = events[save_idx][1]
    assert payload["enabled"] is True
    assert payload["has_actuated"] is False
    # the safe write's flip happened AFTER the flush and is NOT yet persisted:
    assert coord._has_actuated is True
    assert coord._dirty is True  # pending for a later tick's save
    # the unavailable-safe tick reports the minimal payload (2039-2040)
    assert coord.data == {"available": False, "unavailable_safe": True}
