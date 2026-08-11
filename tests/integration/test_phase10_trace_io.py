"""Phase 10 — F-TRACEIO: the trace append left the tick lock (CI-only).

Refactoring plan ``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md``
Befund 5 / phase 10; ADR-0063.

Until phase 10 ``await self._trace_recorder.append(...)`` was the LAST
observable statement of the tick, executed under the coordinator lock — so its
I/O duration counted into ``tick_ms`` and a stalled disk stretched the tick.
Now the tick only ENQUEUES the finished line; a background task drains the
queue onto the executor. These tests pin the four properties that decoupling
has to keep: the tick no longer pays for the write, the file still gets every
line in tick order, the queue is bounded, and the unload flushes what is left.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
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
)
from custom_components.poise.trace.recorder import MAX_QUEUED_LINES, TraceRecorder

# How long the faked disk write blocks. Comfortably above any plausible
# control-path tick time, so "did the tick wait for it" is unambiguous.
_SLOW_WRITE_S = 0.4
_SLOW_WRITE_MS = _SLOW_WRITE_S * 1000.0

_ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Trace Zone",
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


def _states(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "20.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 20.0,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_ROOM_DATA, title="Trace Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    return entry


async def test_slow_disk_no_longer_inflates_tick_ms(hass: HomeAssistant) -> None:
    """F-TRACEIO: with the write blocking for 400 ms, the published ``tick_ms``
    must stay a control-path number. Before phase 10 the append was awaited
    under the lock and inside the measured span, so this tick would have
    reported >= 400 ms."""
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    coord._trace_enabled = True

    real_write = TraceRecorder._write

    def slow_write(self: TraceRecorder, lines: list[str]) -> None:
        time.sleep(_SLOW_WRITE_S)
        real_write(self, lines)

    with patch.object(TraceRecorder, "_write", slow_write):
        await coord.async_refresh()
        tick_ms = (coord.data or {})["tick_ms"]
        # the drain is a TRACKED task, so this deterministically awaits it
        await hass.async_block_till_done()

    assert coord.last_update_success is True
    assert tick_ms < _SLOW_WRITE_MS / 2, (
        f"tick_ms={tick_ms} — the tick still waited for the trace write"
    )
    # non-vacuous: the write really did happen (and really was slow)
    path = Path(hass.config.path("poise_traces", f"{entry.entry_id}.jsonl"))
    assert path.exists()
    assert path.read_text(encoding="utf-8").splitlines()


async def test_queue_preserves_order_and_flushes_on_unload(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """The drain is a single FIFO writer: lines reach the file in enqueue
    order, and ``flush_on_unload`` writes out whatever is still queued (the
    unload checkpoint the coordinator calls)."""
    target = tmp_path / "zone.jsonl"
    rec = TraceRecorder(hass, target, 1_000_000)

    for i in range(5):
        rec.enqueue(f"line-{i}")
    # nothing has been written yet — the enqueue is synchronous and I/O-free
    assert not target.exists()

    await rec.flush_on_unload()
    assert target.read_text(encoding="utf-8").splitlines() == [
        f"line-{i}" for i in range(5)
    ]

    # a second round through the already-drained recorder keeps appending
    rec.enqueue("line-5")
    await rec.flush_on_unload()
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "line-5"


async def test_queue_is_bounded_and_drops_the_oldest(
    hass: HomeAssistant, tmp_path: Path, caplog: Any
) -> None:
    """A stalled disk must not grow memory without bound: the queue caps at
    ``MAX_QUEUED_LINES`` and drops the OLDEST lines, warning exactly once."""
    caplog.set_level(logging.WARNING, logger="custom_components.poise.trace.recorder")
    target = tmp_path / "zone.jsonl"
    rec = TraceRecorder(hass, target, 1_000_000)

    overflow = 3
    for i in range(MAX_QUEUED_LINES + overflow):
        rec.enqueue(f"line-{i}")

    await rec.flush_on_unload()
    written = target.read_text(encoding="utf-8").splitlines()
    assert len(written) == MAX_QUEUED_LINES
    # the survivors are the NEWEST ones, still in order
    assert written[0] == f"line-{overflow}"
    assert written[-1] == f"line-{MAX_QUEUED_LINES + overflow - 1}"
    # one warning for the whole overflow episode, not one per dropped line
    warnings = [
        r for r in caplog.records if r.levelno == logging.WARNING and "queue" in r.msg
    ]
    assert len(warnings) == 1


async def test_write_errors_are_swallowed(
    hass: HomeAssistant, tmp_path: Path, caplog: Any
) -> None:
    """ADR-0026: trace capture is pure observation. An OSError on the drain
    path is swallowed at DEBUG — it must never surface as a task exception."""
    caplog.set_level(logging.DEBUG, logger="custom_components.poise.trace.recorder")
    rec = TraceRecorder(hass, tmp_path / "zone.jsonl", 1_000_000)
    rec.enqueue("line")
    with patch.object(Path, "open", side_effect=OSError("disk gone")):
        await rec.flush_on_unload()
    assert "trace write failed" in caplog.text
