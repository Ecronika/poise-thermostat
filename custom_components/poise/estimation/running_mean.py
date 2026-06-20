"""Running-mean outdoor temperature ``T_rm`` (EN 16798-1, Annex B).

``T_rm`` is the exponentially weighted mean of recent daily mean outdoor
temperatures; it is the basis of the adaptive comfort band (ADR-0010, charter
G2). The recommended decay constant is alpha = 0.8.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

ALPHA: float = 0.8  # EN 16798-1 recommended decay constant


def running_mean_recursive(
    prev_t_rm: float, t_od_yesterday: float, alpha: float = ALPHA
) -> float:
    """One-day recursive update (EN 16798-1 Eq. B.1)."""
    return (1.0 - alpha) * t_od_yesterday + alpha * prev_t_rm


def running_mean_from_days(daily_means: Sequence[float]) -> float:
    """Seven-day weighted approximation (EN 16798-1 / EN 15251).

    ``daily_means`` is most-recent-first: ``[T(d-1), T(d-2), ..., T(d-7)]``.
    Fewer than seven days are allowed (e.g. on cold start).
    """
    weights = (1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2)
    days = list(daily_means)[:7]
    if not days:
        raise ValueError("need at least one daily mean")
    used = weights[: len(days)]
    return sum(w * d for w, d in zip(used, days, strict=True)) / sum(used)


_RECENT_DAYS_CAP = 7


@dataclass
class RunningMeanTracker:
    """Stateful internal ``T_rm`` for when no external running-mean sensor exists.

    Accumulates the daily mean outdoor temperature tick-by-tick and, on each
    calendar-day rollover, advances ``T_rm`` with the EN 16798-1 recursion
    (Eq. B.1). On the very first observation ``T_rm`` is seeded with the current
    outdoor temperature so the comfort band is sane from the first tick; it then
    converges to the true exponentially weighted mean over the following days.
    Pure + serialisable so it can be persisted across restarts (ADR-0007).
    """

    alpha: float = ALPHA
    t_rm: float | None = None
    day: int | None = None  # ordinal of the day currently being accumulated
    day_sum: float = 0.0
    day_count: int = 0
    recent_days: list[float] = field(default_factory=list)  # most-recent-first

    def observe(self, t_out: float, day: int) -> None:
        """Feed one outdoor sample tagged with its calendar day (ordinal)."""
        if self.day is None:
            self.day = day
            if self.t_rm is None:
                self.t_rm = t_out  # cold-start seed
        elif day != self.day:
            if self.day_count > 0:
                self._finalize_day(self.day_sum / self.day_count)
            self.day = day
            self.day_sum = 0.0
            self.day_count = 0
        self.day_sum += t_out
        self.day_count += 1

    def _finalize_day(self, daily_mean: float) -> None:
        if self.t_rm is None:
            self.t_rm = daily_mean
        else:
            self.t_rm = running_mean_recursive(self.t_rm, daily_mean, self.alpha)
        self.recent_days.insert(0, daily_mean)
        del self.recent_days[_RECENT_DAYS_CAP:]

    @property
    def current(self) -> float | None:
        """The current running-mean estimate, or None before any observation."""
        return self.t_rm

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "t_rm": self.t_rm,
            "day": self.day,
            "day_sum": self.day_sum,
            "day_count": self.day_count,
            "recent_days": list(self.recent_days),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunningMeanTracker:
        return cls(
            alpha=float(data.get("alpha", ALPHA)),
            t_rm=data.get("t_rm"),
            day=data.get("day"),
            day_sum=float(data.get("day_sum", 0.0)),
            day_count=int(data.get("day_count", 0)),
            recent_days=[float(x) for x in data.get("recent_days", [])],
        )
