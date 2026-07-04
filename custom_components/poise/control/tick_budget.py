"""Per-tick compute-time budget tracker (ADR-0020 performance budget).

The coordinator times each tick's compute and feeds the duration here; this pure
accumulator keeps a smoothed average, a session maximum, and an over-budget
counter against the documented budget, so the real per-zone cost is observable in
the field *before* the Phase-4 flip adds control work. Over-budget is a signal for
zone staggering (ADR-0020 §5), never a hard limit. Transient by design — a restart
re-measures; the current cost is what matters. Pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass

# Target compute time per zone per tick. Generous vs the real cost (a few ms):
# it flags a genuine regression / scaling wall, not normal jitter. At 60 s ticks
# this leaves ample headroom for many zones before staggering is needed.
DEFAULT_TICK_BUDGET_MS: float = 50.0


@dataclass
class TickBudget:
    """Rolling tick compute-time stats against a budget (ADR-0020)."""

    budget_ms: float = DEFAULT_TICK_BUDGET_MS
    ewma_alpha: float = 0.1
    last_ms: float = 0.0
    ewma_ms: float = 0.0
    max_ms: float = 0.0
    n: int = 0
    over_count: int = 0

    def observe(self, duration_ms: float) -> None:
        """Fold one tick's measured compute time [ms] into the stats."""
        d = max(0.0, duration_ms)
        self.last_ms = d
        self.ewma_ms = (
            d
            if self.n == 0
            else (1.0 - self.ewma_alpha) * self.ewma_ms + self.ewma_alpha * d
        )
        if d > self.max_ms:
            self.max_ms = d
        self.n += 1
        if d > self.budget_ms:
            self.over_count += 1

    @property
    def over_budget(self) -> bool:
        """Whether the most recent tick exceeded the budget."""
        return self.n > 0 and self.last_ms > self.budget_ms
