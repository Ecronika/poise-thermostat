"""Home Assistant coordinator — thin wrapper around the pure pipeline (ADR-0006).

Responsibilities kept here (HA-specific):
  * serialise ticks with an ``asyncio.Lock`` + pending flag (event-coalescing),
  * schedule the periodic tick and accept event-driven refreshes,
  * restore persisted state *before* the first tick (ADR-0007 bootstrap).

All control logic lives in ``pipeline.run_tick`` and stays HA-free/testable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .clock import MonotonicClock
from .const import DOMAIN, TICK_INTERVAL_S
from .controller import BangBangController

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class PoiseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Drives one atomic tick per interval; one writer per actuator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_S),
        )
        self._entry = entry
        self._clock = MonotonicClock()
        self._controller = BangBangController()
        self._lock = asyncio.Lock()
        self._pending = False
        self._restored = False

    async def async_bootstrap(self) -> None:
        """Restore persisted state before the first control tick (ADR-0007)."""
        # Phase 0: nothing persisted yet. Storage skeleton lands in Phase 2.
        self._restored = True

    async def _async_update_data(self) -> dict[str, Any]:
        """Serialised, atomic tick. Overlapping scheduled ticks coalesce."""
        if self._lock.locked():
            self._pending = True
            return self.data or {}
        async with self._lock:
            result = await self._run_once()
            while self._pending:
                self._pending = False
                result = await self._run_once()
            return result

    async def _run_once(self) -> dict[str, Any]:
        if not self._restored:
            await self.async_bootstrap()
        # Phase 0: zone assembly + actuator writes are wired in Phase 3/5.
        # The pure tick is unit-tested directly; see tests/test_pipeline.py.
        return self.data or {}
