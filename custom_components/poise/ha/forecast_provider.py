"""Forecast fetch + TTL cache for optimal start/stop.

``ForecastProvider`` owns the forecast fetch and its cache state (``forecast``
/ ``forecast_at`` / ``fail_at``).  The fetch stays an ``await`` inside the
tick, under the coordinator lock, at the single predictive-gated call position;
decoupling it from the tick (prefetch/background refresh) is deferred to
F-FORECAST (phase 10).

This is the ONE ``blocking=True`` service call of the tick — and it is a READ
(``return_response=True``), not an effect write; every effect write
(``actuator_executor``) stays ``blocking=False``.

Semantics:

* A missing weather entity degrades straight to ``fallback`` — optimal start
  never depends on a forecast.
* The cached hourly forecast refreshes at most every ``FORECAST_TTL_S``; the
  fetch is bounded by ``_WEATHER_CALL_TIMEOUT_S`` (a hung call runs under the
  coordinator lock and must not stall the tick).
* A fetch failure falls through to the LAST GOOD cache via
  ``mean_forecast_outdoor`` (normally a better preheat estimate than a flat
  constant) and only an empty cache degrades to ``fallback``; a failure also
  starts a ``FORECAST_TTL_S`` backoff (``fail_at``) before the next retry
  instead of re-attempting the possibly slow/rate-limited call every tick.
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

# A hung weather.get_forecasts call must not stall the tick: it runs under the
# coordinator lock, so bound it and degrade to the constant outdoor.
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
        stale = self.forecast_at is None or (now - self.forecast_at) >= FORECAST_TTL_S
        backed_off = self.fail_at is not None and (now - self.fail_at) < FORECAST_TTL_S
        if stale and not backed_off:
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
                self._logger.debug(
                    "Poise: weather forecast unavailable; using stale cache"
                )
                self.fail_at = now
        return mean_forecast_outdoor(self.forecast, horizon_min, fallback)
