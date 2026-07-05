"""Settle-based τ-confidence: trust the learned time constant τ = 1/α because α
has stopped moving, not merely because enough samples were counted.

The counter-based ``identified`` gate (ADR-0024) trusts τ once n_heating/n_cooling
reach a threshold; the covariance route was rejected (the α random-walk process
noise floors ``p[α][α]`` so it never shrinks — the v0.144 closed-loop finding).
This is the sound alternative: track α over a window of *learn-active* time (ticks
with heating/cooling excitation, where α can actually move) and measure its
relative spread. A converged α has a small spread → τ is settled/confident; an α
still drifting or pegged keeps the spread high → not confident.

Shadow-first: the coordinator surfaces this as a diagnostic and, later, uses it to
CLAMP the optimal-start preheat lead (not a binary gate) behind the ADR-0055 flip
gate. The relative-spread threshold is a conservative default here and gets tuned
offline against real α trajectories from the field traces. Pure and HA-free
(ADR-0005/0011).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

DEFAULT_HORIZON_MIN = 90.0  # EWMA time constant for the α mean/variance
DEFAULT_WARMUP_MIN = 60.0  # min learn-active time before τ may be "settled"
DEFAULT_REL_GATE = 0.04  # rel. spread (std/mean of α) at/under which τ is settled


@dataclass(frozen=True, slots=True)
class TauSettle:
    """EWMA settling estimate of α plus a "has it converged?" gate."""

    mean: float  # EWMA of α  [1/h]
    var: float  # EWMA variance of α around its running mean
    minutes: float  # accumulated learn-active observation time
    settled: bool  # spread small enough over enough learn-active time?

    @property
    def rel_spread(self) -> float:
        if self.mean <= 0.0:
            return math.inf
        return math.sqrt(max(0.0, self.var)) / self.mean

    def to_dict(self) -> dict[str, Any]:
        return {"mean": self.mean, "var": self.var, "minutes": self.minutes}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TauSettle:
        return cls(
            mean=float(data.get("mean", 0.0)),
            var=float(data.get("var", 0.0)),
            minutes=float(data.get("minutes", 0.0)),
            settled=False,  # conservative: re-derive on the next observation
        )


def update_settle(
    prev: TauSettle | None,
    *,
    alpha: float | None,
    dt_min: float,
    learn_active: bool = True,
    horizon_min: float = DEFAULT_HORIZON_MIN,
    warmup_min: float = DEFAULT_WARMUP_MIN,
    rel_gate: float = DEFAULT_REL_GATE,
) -> TauSettle | None:
    """Fold one α sample into the settle estimate.

    Only *learn-active* ticks (heating/cooling excitation present, where α can
    move) advance the window — during idle α is frozen and would look trivially
    settled without new information, so those ticks hold the prior unchanged. A
    missing or non-positive α also holds. ``settled`` requires BOTH a warm-up of
    learn-active time and a small relative spread of α.
    """
    if not learn_active or alpha is None or alpha <= 0.0:
        return prev
    if prev is None:
        return TauSettle(mean=alpha, var=0.0, minutes=max(0.0, dt_min), settled=False)
    dt = max(0.0, dt_min)
    a = 1.0 - math.exp(-dt / horizon_min) if horizon_min > 0 else 1.0
    diff = alpha - prev.mean
    incr = a * diff
    mean = prev.mean + incr
    var = (1.0 - a) * (prev.var + diff * incr)  # exp.-weighted variance (Finch)
    minutes = prev.minutes + dt
    settled = minutes >= warmup_min and (
        math.sqrt(max(0.0, var)) / mean <= rel_gate if mean > 0.0 else False
    )
    return TauSettle(mean=mean, var=var, minutes=minutes, settled=settled)


def settle_confidence(
    est: TauSettle | None,
    *,
    rel_gate: float = DEFAULT_REL_GATE,
    warmup_min: float = DEFAULT_WARMUP_MIN,
) -> float:
    """A [0, 1] confidence in τ from the settle estimate: 1 when α is perfectly
    steady, decaying linearly to 0 as the relative spread reaches ``2·rel_gate``;
    0 until the warm-up is met. Companion to the counter/covariance ``confidence``
    (ADR-0024)."""
    if est is None or est.minutes < warmup_min or est.mean <= 0.0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - est.rel_spread / (2.0 * rel_gate)))
