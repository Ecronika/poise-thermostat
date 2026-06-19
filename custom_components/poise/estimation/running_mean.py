"""Running-mean outdoor temperature ``T_rm`` (EN 16798-1, Annex B).

``T_rm`` is the exponentially weighted mean of recent daily mean outdoor
temperatures; it is the basis of the adaptive comfort band (ADR-0010, charter
G2). The recommended decay constant is alpha = 0.8.
"""

from __future__ import annotations

from collections.abc import Sequence

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
