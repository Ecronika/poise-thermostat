"""Best-effort JSONL field-trace writer (glue for ``trace.schema``; ADR-0011).

Appends one line per tick on the executor (never blocks the event loop) and
rotates at a size cap (two generations, so on-disk stays bounded at ~2x the cap).
Every error is swallowed — trace capture is pure observation and must never
disturb control (ADR-0026).
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class TraceRecorder:
    """Owns one zone's rolling trace file and appends to it via the executor."""

    def __init__(self, hass: HomeAssistant, path: str | Path, max_bytes: int) -> None:
        self._hass = hass
        self._path = Path(path)
        self._max_bytes = max_bytes

    async def append(self, line: str) -> None:
        await self._hass.async_add_executor_job(self._write, line)

    def _write(self, line: str) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists() and self._path.stat().st_size >= self._max_bytes:
                # 2-file rotation: keep exactly one previous generation.
                self._path.replace(self._path.with_name(self._path.name + ".1"))
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            _LOGGER.debug("Poise trace write failed for %s", self._path, exc_info=True)
