"""Forecast fetch + TTL cache for optimal start/stop.

``ForecastProvider`` owns the forecast fetch and its cache state (``forecast``
/ ``forecast_at`` / ``fail_at``).

The refresh runs as a background task and the tick reads the cache
(ADR-0063), so a slow weather integration cannot stretch the tick by up to
``_WEATHER_CALL_TIMEOUT_S``.  The ONE exception is deliberate:

* **Cold start** (no cache at all — fresh restart, or every usable sample
  expired) AWAITS the fetch.  A cold predictive tick would otherwise fall
  back to the flat constant outdoor temperature, and that is exactly the tick
  that decides a preheat start edge after a nightly restart.  It is bounded by
  the same timeout, happens at most once per ``FORECAST_TTL_S`` (the failure
  backoff covers the rest), and is the only await left in the tick that can
  block on a third-party integration.
* **Warm cache** — a stale-but-present cache serves this tick and a background
  refresh is kicked off for the next one.  Worst case, optimal start uses a
  forecast that is one tick older than before; the samples are hourly, so that
  is far inside the model's own resolution.

Concurrency contract:

* **Single-flight** — at most one in-flight refresh per zone; a second stale
  tick does not start a second call.
* **Atomic snapshot** — the refresh REPLACES ``forecast`` with a new list and
  never mutates it in place, and the reader snapshots the reference into a
  local, so a tick can never see a half-written cache.
* **Cancel** — ``async_close`` (called from the coordinator's unload path)
  cancels an in-flight refresh so no task outlives the config entry.

This is the only ``blocking=True`` service call in the TICK path — and it is
a READ (``return_response=True``), not an effect write; every effect write
(``actuator_executor``) stays ``blocking=False``.  The remaining
``blocking=True`` calls live outside the tick (``__init__.py`` teardown,
``hub_coordinator`` boiler actions).

Semantics (unchanged by the decoupling):

* A missing weather entity degrades straight to ``fallback`` — optimal start
  never depends on a forecast.
* The cached hourly forecast refreshes at most every ``FORECAST_TTL_S``; the
  fetch is bounded by ``_WEATHER_CALL_TIMEOUT_S``.
* A fetch failure keeps the LAST GOOD cache (normally a better preheat estimate
  than a flat constant) and starts a ``FORECAST_TTL_S`` backoff (``fail_at``)
  before the next retry instead of re-attempting the possibly slow/rate-limited
  call every tick.
* The horizon is NOT part of the service payload — the payload is exactly
  ``{"type": "hourly", "entity_id": <weather>}`` (pinned by
  test_phase0_forecast_gating).

Wiring: the provider takes its clock and logger as parameters.  Pass a live
clock forwarder so a test-swapped coordinator clock keeps governing the
TTL/backoff instants, and pass the COORDINATOR's module logger: the
failure-path debug record ("Poise: weather forecast unavailable; using stale
cache") is emitted on the ``custom_components.poise.coordinator`` channel, and
the record's logger NAME is observable behavior.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ..const import FORECAST_TTL_S
from ..control.optimal_start import (
    forecast_samples_from_response,
    mean_forecast_outdoor,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..clock import Clock

# A hung weather.get_forecasts call must not stall the tick: on the cold-start
# path it still runs under the coordinator lock, so bound it and degrade to the
# constant outdoor.
_WEATHER_CALL_TIMEOUT_S = 10.0


class ForecastProvider:
    """Owns the hourly-forecast cache + the one blocking READ of the tick.

    The cache fields are plain public attributes so the coordinator can proxy
    them and existing tests can keep poking them.
    """

    def __init__(
        self, hass: HomeAssistant, clock: Clock, logger: logging.Logger
    ) -> None:
        self._hass = hass
        self._clock = clock
        # Injected (not a module logger): the failure-path debug record must
        # keep the CALLER's logger name.  The coordinator passes its own module
        # logger so the record stays on the coordinator channel; the record's
        # logger name is observable behavior.
        self._logger = logger
        # Cache state.
        self.forecast: list[tuple[float, float]] = []
        self.forecast_at: float | None = None
        self.fail_at: float | None = None  # backoff after a failure
        # Single-flight handle for the background refresh (F-FORECAST).
        self._refresh: asyncio.Task[None] | None = None

    async def mean_outdoor(
        self, weather_entity: str | None, horizon_min: float, fallback: float
    ) -> float:
        """Mean forecast outdoor temp over the preheat window (ADR-0025).

        The weather entity is a parameter so the coordinator call stays a
        one-liner.  ALWAYS ends in ``mean_forecast_outdoor`` on the cached
        samples — the failure path reuses the last good cache and only an
        empty/unusable cache returns ``fallback``.
        """
        if not weather_entity:
            return fallback
        now = self._clock.monotonic()
        if self._due(now):
            if self.forecast:
                # Warm cache: serve it now, refresh for the next tick.
                self._start_refresh(weather_entity, now)
            else:
                # Cold start: the only remaining await in the tick.
                await self._fetch(weather_entity, now)
        # Atomic snapshot: the refresh rebinds the attribute, never mutates.
        return mean_forecast_outdoor(self.forecast, horizon_min, fallback)

    def _due(self, now: float) -> bool:
        """Stale enough to refetch, and not inside the failure backoff."""
        stale = self.forecast_at is None or (now - self.forecast_at) >= FORECAST_TTL_S
        backed_off = self.fail_at is not None and (now - self.fail_at) < FORECAST_TTL_S
        return stale and not backed_off

    def _start_refresh(self, weather_entity: str, now: float) -> None:
        """Kick off the background refresh unless one is already in flight.

        A TRACKED task (not a background one): the fetch should complete rather
        than be cancelled at shutdown, and it makes the refresh deterministic
        under ``hass.async_block_till_done()`` in the glue tests. Unload cancels
        it explicitly via :meth:`async_close`.
        """
        if self._refresh is not None and not self._refresh.done():
            return
        self._refresh = self._hass.async_create_task(
            self._fetch(weather_entity, now),
            "poise-forecast-refresh",
            eager_start=False,
        )

    async def _fetch(self, weather_entity: str, now: float) -> None:
        """One ``weather.get_forecasts`` round-trip into the cache.

        ``now`` is the instant the refresh became due, not the instant it
        finished: stamping the START keeps a slow fetch from silently extending
        the TTL. Failures are swallowed into the backoff — never re-raised,
        because this also runs detached as a task.
        """
        try:
            async with asyncio.timeout(_WEATHER_CALL_TIMEOUT_S):
                resp = await self._hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"type": "hourly", "entity_id": weather_entity},
                    blocking=True,
                    return_response=True,
                )
            self.forecast = forecast_samples_from_response(
                resp, weather_entity, dt_util.utcnow()
            )
            self.forecast_at = now
            self.fail_at = None
        except Exception:  # noqa: BLE001 - forecast must never break the tick
            self._logger.debug("Poise: weather forecast unavailable; using stale cache")
            self.fail_at = now

    async def async_close(self) -> None:
        """Cancel an in-flight refresh so no task outlives the config entry."""
        task, self._refresh = self._refresh, None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
