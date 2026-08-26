"""Comfort schedule: cyclic week timeline + night setback (ADR-0025, plan P2).

A per-zone schedule of comfort windows on a CYCLIC WEEK timeline. Each window
is a daily half-open interval ``[start_min, end_min)`` plus a weekday bitmask
(bit 0 = Monday, i.e. ISO weekday - 1); the schedule expands every window onto
minutes-of-week ``[0, WEEK_MINUTES)`` and takes the SET UNION, so overlapping
windows from different days/masks merge instead of shadowing each other.
Inside the union the zone targets the full comfort base; outside it is in
*setback* and the comfort base is lowered by ``setback_delta`` K. The schedule
also reports the minutes until the next comfort start/end, which the
optimal-start advisor (``control.optimal_start``) turns into preheat/coast
lead times.

Transitions that DO NOT EXIST are ``None``, never a sentinel (plan §0.4 p.5,
§0.5 p.5): ``minutes_to_comfort`` feeds the forecast request directly as
``horizon_min`` (a 10080 sentinel would ask the provider for a 7-day
forecast), and ``minutes_to_switchpoint`` treats every number as a real
switchpoint while already owning a ``None`` = "no switchpoint" path — so the
honest encoding is ``None`` and a guard at each consumer, not a magic number.

Pure module: no Home Assistant imports, fully unit-tested. ``minute`` is
minutes since local midnight; ``state_at`` wraps any integer into [0, 1440)
(the pre-week semantics, kept). ``weekday`` is mandatory and validated —
a caller that forgot the week dimension must fail loudly, not default.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

DAY_MINUTES = 1440
WEEK_MINUTES = 7 * DAY_MINUTES
ALL_DAYS = 0b1111111  # bit 0 = Monday .. bit 6 = Sunday (ISO weekday - 1)

# The expanded union covering the whole week collapses to exactly this one
# interval (touching intervals merge), which is behaviourally always-comfort.
_FULL_WEEK = ((0, WEEK_MINUTES),)


@dataclass(frozen=True, slots=True)
class ComfortWindow:
    """A daily half-open interval [start_min, end_min) on the masked days.

    ``days`` defaults to ``ALL_DAYS`` — the config parser produces maskless
    windows until P2.3, and the default absorbs that unchanged. ``days == 0``
    keeps the window *configured* but never active (always-setback rule in
    ``ComfortSchedule.from_windows``).
    """

    start_min: int
    end_min: int
    days: int = ALL_DAYS


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """The schedule's verdict for one instant.

    ``None`` = "this transition does not exist" (always-comfort has no next
    comfort start, always-setback no next comfort end). Inside the regular
    week union the 0-conventions are unchanged: ``minutes_to_comfort == 0``
    while in comfort, ``minutes_to_setback == 0`` while in setback.
    """

    is_comfort: bool  # inside a comfort window now
    minutes_to_comfort: int | None  # 0 in comfort; None = no next comfort start
    setback_offset: float  # 0.0 in comfort; -setback_delta during setback
    minutes_to_setback: int | None = 0  # 0 in setback; None = no next comfort end


def _normalize(windows: Iterable[ComfortWindow]) -> tuple[ComfortWindow, ...]:
    """Clamp to one day, drop empty intervals, merge same-mask overlaps.

    ``start == end`` is dropped as EMPTY (never a 24-h window) and does not
    count as "configured". Overnight windows (end < start) pass through as
    wrap windows; the week expansion resolves them. Merging here is purely
    representational (config round-trip/display) — membership and distances
    come from the expanded week union — so it stays conservative: only
    adjacent same-day windows with an IDENTICAL day mask merge.
    """
    clean: list[ComfortWindow] = []
    for w in windows:
        start = max(0, min(int(w.start_min), DAY_MINUTES))
        end = max(0, min(int(w.end_min), DAY_MINUTES))
        if end != start:  # drop empty; keep overnight (end < start) as wrap
            clean.append(ComfortWindow(start, end, int(w.days) & ALL_DAYS))
    nonwrap = sorted(
        (w for w in clean if w.end_min > w.start_min), key=lambda w: w.start_min
    )
    wrap = [w for w in clean if w.end_min < w.start_min]
    merged: list[ComfortWindow] = []
    for w in nonwrap:
        prev = merged[-1] if merged else None
        if prev is not None and w.days == prev.days and w.start_min <= prev.end_min:
            merged[-1] = ComfortWindow(
                prev.start_min, max(prev.end_min, w.end_min), prev.days
            )
        else:
            merged.append(w)
    return tuple(merged + wrap)


def _expand(windows: Iterable[ComfortWindow]) -> tuple[tuple[int, int], ...]:
    """Expand windows onto the week axis and take the sorted, merged union.

    Per window, per set day ``d``: non-overnight becomes
    ``[d*1440 + start, d*1440 + end)``; overnight (end < start — ``end ==
    start`` was already dropped, so ``<`` is the whole overnight class)
    becomes ``[d*1440 + start, (d+1)*1440 + end)``; a Sunday overnight
    exceeds ``WEEK_MINUTES`` and is split modulo into
    ``[6*1440 + start, WEEK_MINUTES)`` + ``[0, end)``.

    After the plain merge (overlapping/touching), the CYCLIC seam is closed:
    if the first interval starts at 0 and the last ends at ``WEEK_MINUTES``,
    they are one comfort block across the Sunday->Monday boundary and merge
    into a single WRAP interval ``(last.start, WEEK_MINUTES + first.end)`` —
    the one representation whose ``end - probe`` distance is seam-correct
    (Sunday 23:00 inside SO 22-06 is 420 minutes from the end, not 60).
    Membership then probes both ``wm`` and ``wm + WEEK_MINUTES``.

    A zero-width raw interval can appear here even though ``_normalize``
    already drops ``start == end`` at the daily level: a window clamped to
    ``start_min == DAY_MINUTES`` (1440) with an overnight ``end_min == 0``
    expands to ``s == e`` exactly at a day boundary (or at ``WEEK_MINUTES``
    for a Sunday roll). Such a phantom interval carries no width but would
    still contribute its ``start`` to the to-next-comfort distance below, so
    it is filtered before the merge/seam step, never after.
    """
    raw: list[tuple[int, int]] = []
    for w in windows:
        overnight = w.end_min < w.start_min
        for d in range(7):
            if not w.days & (1 << d):
                continue
            s = d * DAY_MINUTES + w.start_min
            e = (d + (1 if overnight else 0)) * DAY_MINUTES + w.end_min
            if e > WEEK_MINUTES:  # Sunday overnight spills into Monday
                raw.append((s, WEEK_MINUTES))
                raw.append((0, e - WEEK_MINUTES))
            else:
                raw.append((s, e))
    raw = [(s, e) for s, e in raw if e > s]  # drop phantom zero-width intervals
    raw.sort()
    merged: list[tuple[int, int]] = []
    for s, e in raw:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    if len(merged) >= 2 and merged[0][0] == 0 and merged[-1][1] == WEEK_MINUTES:
        wrap = (merged[-1][0], WEEK_MINUTES + merged[0][1])
        merged = [*merged[1:-1], wrap]
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class ComfortSchedule:
    """Normalized comfort windows + the setback depth in kelvin.

    Three construction states (plan P2.1):

    1. no windows at all            -> always-comfort (no transitions)
    2. windows configured, but the
       week expansion is empty
       (every mask ``days == 0``)   -> always-setback (no transitions)
    3. otherwise                    -> the cyclic week union

    ``_intervals`` is the derived week union (see ``_expand``); it is
    recomputed in ``__post_init__`` so every construction path carries it,
    and excluded from equality — it is a pure function of ``windows``.
    """

    windows: tuple[ComfortWindow, ...] = field(default_factory=tuple)
    setback_delta: float = 3.0
    _intervals: tuple[tuple[int, int], ...] = field(
        init=False, repr=False, compare=False, default=()
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "_intervals", _expand(self.windows))

    @classmethod
    def from_windows(
        cls, windows: Sequence[ComfortWindow], setback_delta: float = 3.0
    ) -> ComfortSchedule:
        return cls(_normalize(windows), float(setback_delta))

    @classmethod
    def always_comfort(cls) -> ComfortSchedule:
        """An empty schedule: comfort all week, never any setback."""
        return cls((), 0.0)

    def state_at(self, minute: int, weekday: int) -> ScheduleState:
        """Comfort/setback verdict + minutes to the next comfort start/end.

        Both arguments are MANDATORY: ``weekday`` (0 = Monday .. 6 = Sunday)
        is validated so a caller that forgot the week dimension fails loudly
        instead of silently reading Monday. ``minute`` wraps into [0, 1440)
        (the any-int semantics of the daily model, kept — F8).
        """
        if not 0 <= weekday <= 6:
            raise ValueError(f"weekday must be 0..6 (Monday=0), got {weekday}")
        if not self.windows:  # state 1: always comfort, no transitions
            return ScheduleState(True, None, 0.0, None)
        intervals = self._intervals
        if not intervals:  # state 2: configured but never active
            return ScheduleState(False, None, -self.setback_delta, None)
        if intervals == _FULL_WEEK:  # union covers the week == always comfort
            return ScheduleState(True, None, 0.0, None)
        wm = weekday * DAY_MINUTES + minute % DAY_MINUTES
        for start, end in intervals:
            # Only the closing wrap interval has end > WEEK_MINUTES; the
            # second probe is how a Monday-morning minute lands inside it.
            for probe in (wm, wm + WEEK_MINUTES):
                if start <= probe < end:
                    return ScheduleState(True, 0, 0.0, end - probe)
        to_next = min((start - wm) % WEEK_MINUTES for start, _ in intervals)
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
