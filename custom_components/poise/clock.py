"""Injectable monotonic clock (ADR-0006).

All duration timers use a monotonic source; the clock is injected so ticks
are deterministic and testable (ADR-0014). Wall-clock anchors for restart-
persistent timers are handled separately in storage (ADR-0007).
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...


class MonotonicClock:
    """Production clock backed by :func:`time.monotonic`."""

    def monotonic(self) -> float:
        return time.monotonic()


class ManualClock:
    """Deterministic clock for tests and the replay harness (ADR-0011/0014)."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def monotonic(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds
