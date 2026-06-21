"""Comfort schedule: night setback + optimal-start deadline (ADR-0025).

A per-zone daily schedule of comfort windows. Inside a window the zone targets
the full comfort base; outside (night/away) it is in *setback* and the comfort
base is lowered by ``setback_delta`` K. The schedule also reports the minutes
until the next comfort window begins, which the optimal-start advisor
(``control.optimal_start``) turns into a preheat lead time.

Pure module: no Home Assistant imports, fully unit-tested. Times are minutes
since local midnight in [0, 1440); ``state_at`` accepts any integer and wraps.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

DAY_MINUTES = 1440


@dataclass(frozen=True, slots=True)
class ComfortWindow:
    """A daily half-open interval [start_min, end_min) at comfort temperature."""

    start_min: int
    end_min: int


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """The schedule's verdict for one instant."""

    is_comfort: bool  # inside a comfort window now
    minutes_to_comfort: int  # 0 while in comfort; else minutes to the next start
    setback_offset: float  # 0.0 in comfort; -setback_delta during setback
    minutes_to_setback: int = 0  # minutes until the current window ends; 0 in setback


def _normalize(windows: Iterable[ComfortWindow]) -> tuple[ComfortWindow, ...]:
    """Clamp to one day, drop empty intervals, merge same-day overlaps; overnight
    windows (end < start, e.g. 22:00-06:00) are kept as wrap windows."""
    clean: list[ComfortWindow] = []
    for w in windows:
        start = max(0, min(int(w.start_min), DAY_MINUTES))
        end = max(0, min(int(w.end_min), DAY_MINUTES))
        if end != start:  # drop empty; keep overnight (end < start) as a wrap window
            clean.append(ComfortWindow(start, end))
    # merge only same-day windows; pass wrap windows (overnight) through untouched
    nonwrap = sorted(
        (w for w in clean if w.end_min > w.start_min), key=lambda w: w.start_min
    )
    wrap = [w for w in clean if w.end_min < w.start_min]
    merged: list[ComfortWindow] = []
    for w in nonwrap:
        if merged and w.start_min <= merged[-1].end_min:
            prev = merged[-1]
            merged[-1] = ComfortWindow(prev.start_min, max(prev.end_min, w.end_min))
        else:
            merged.append(w)
    return tuple(merged + wrap)


@dataclass(frozen=True, slots=True)
class ComfortSchedule:
    """Normalized daily comfort windows + the setback depth in kelvin."""

    windows: tuple[ComfortWindow, ...] = field(default_factory=tuple)
    setback_delta: float = 3.0

    @classmethod
    def from_windows(
        cls, windows: Sequence[ComfortWindow], setback_delta: float = 3.0
    ) -> ComfortSchedule:
        return cls(_normalize(windows), float(setback_delta))

    @classmethod
    def always_comfort(cls) -> ComfortSchedule:
        """An empty schedule: comfort all day, never any setback."""
        return cls((), 0.0)

    def state_at(self, minute: int) -> ScheduleState:
        """Comfort/setback verdict and minutes to the next comfort start."""
        if not self.windows:  # no windows => always comfort, no setback
            return ScheduleState(True, 0, 0.0, 0)
        m = minute % DAY_MINUTES
        for w in self.windows:
            wrap = w.end_min <= w.start_min  # overnight window crossing midnight
            inside = (
                (m >= w.start_min or m < w.end_min)
                if wrap
                else (w.start_min <= m < w.end_min)
            )
            if inside:
                # minutes until this window ends, accounting for the midnight wrap
                end = w.end_min + (DAY_MINUTES if wrap and m >= w.start_min else 0)
                return ScheduleState(True, 0, 0.0, end - m)
        to_next = min((w.start_min - m) % DAY_MINUTES for w in self.windows)
        return ScheduleState(False, to_next, -self.setback_delta, 0)


def parse_hhmm(value: str | None) -> int | None:
    """Parse "HH:MM" or "HH:MM:SS" to minutes since midnight; None if invalid."""
    if not value:
        return None
    parts = str(value).split(":")
    if len(parts) < 2:
        return None
    try:
        minutes = int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None
    return minutes if 0 <= minutes < DAY_MINUTES else None
