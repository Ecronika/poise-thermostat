"""Best-effort JSONL field-trace writer (glue for ``trace.schema``; ADR-0011).

Since F-TRACEIO (phase 10) the tick only ENQUEUES its line and returns; a
background task drains the queue and appends on the executor.  The file I/O
therefore no longer counts into ``tick_ms`` and a slow or hung disk can no
longer stretch a tick that holds the coordinator lock.

What the decoupling preserves:

* **Order** — exactly ONE drain task at a time over a FIFO queue, so the file
  keeps the tick order the golden-file replay depends on.
* **File content and rotation** — the executor still appends line by line and
  re-checks the size cap before each one, so on-disk bytes are identical to the
  pre-phase-10 writer (two generations, ~2x the cap).
* **Never disturb control** (ADR-0026) — every error is swallowed, and the
  queue is BOUNDED: if the disk stalls, the oldest lines are dropped (with one
  warning) instead of growing memory without bound.

The unload path calls :meth:`flush_on_unload` so the last ticks of a session
reach the file before the entry goes away.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from contextlib import suppress
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# ~8.5 h of queued ticks at the 60 s cadence. Only ever reached when the drain
# cannot keep up (a stalled disk); a healthy drain empties the queue in one
# batch right after the tick returns.
MAX_QUEUED_LINES = 512


class TraceRecorder:
    """Owns one zone's rolling trace file and drains a queue to it off-tick."""

    def __init__(self, hass: HomeAssistant, path: str | Path, max_bytes: int) -> None:
        self._hass = hass
        self._path = Path(path)
        self._max_bytes = max_bytes
        self._queue: deque[str] = deque()
        self._drain: asyncio.Task[None] | None = None
        self._dropped = 0

    def enqueue(self, line: str) -> None:
        """Queue one line and make sure a drain task is running.

        SYNCHRONOUS by contract: this runs under the coordinator lock and must
        not await — that is the whole point of F-TRACEIO. It also must not
        raise; the caller's swallow boundary is the backstop, but nothing here
        touches the filesystem.
        """
        if len(self._queue) >= MAX_QUEUED_LINES:
            self._queue.popleft()
            self._dropped += 1
            if self._dropped == 1:
                _LOGGER.warning(
                    "Poise trace queue for %s hit %d lines; dropping the oldest "
                    "records. Trace capture is pure observation and never "
                    "blocks the tick (ADR-0026) — check the disk if this "
                    "persists",
                    self._path,
                    MAX_QUEUED_LINES,
                )
        self._queue.append(line)
        if self._drain is None or self._drain.done():
            # A TRACKED task, not a background one: the write should still
            # complete rather than be cancelled at shutdown, and it makes the
            # drain deterministic under ``hass.async_block_till_done()`` in the
            # glue tests. ``eager_start=False`` keeps the whole thing out of
            # the tick — nothing of the drain body runs inside this call.
            self._drain = self._hass.async_create_task(
                self._drain_queue(),
                f"poise-trace-{self._path.name}",
                eager_start=False,
            )

    async def _drain_queue(self) -> None:
        """Write whatever is queued, in batches, until the queue runs dry.

        Re-checking the queue after every executor round-trip means lines that
        arrive mid-drain are picked up by the SAME task, which is what keeps a
        single writer (and therefore the file order) even under back-pressure.
        """
        while self._queue:
            batch = list(self._queue)
            self._queue.clear()
            await self._hass.async_add_executor_job(self._write, batch)

    async def flush_on_unload(self) -> None:
        """Write out everything still queued — the unload checkpoint.

        Awaits the running drain (a cancelled one is not an error here) and
        then writes any remainder inline, so no trace line is lost just because
        the entry was unloaded between a tick and its drain.
        """
        task, self._drain = self._drain, None
        if task is not None and not task.done():
            with suppress(asyncio.CancelledError):
                await task
        await self._drain_queue()

    def _write(self, lines: list[str]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            for line in lines:
                if self._path.exists() and self._path.stat().st_size >= self._max_bytes:
                    # 2-file rotation: keep exactly one previous generation.
                    self._path.replace(self._path.with_name(self._path.name + ".1"))
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError:
            _LOGGER.debug("Poise trace write failed for %s", self._path, exc_info=True)
