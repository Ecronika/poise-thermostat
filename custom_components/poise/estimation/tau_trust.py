"""τ-trust gate: may optimal-start / optimal-stop act on the learned τ? (ADR-0034 N1)

``identified`` (ADR-0024) only counts observations and checks the temperature
covariance — it says nothing about whether α = 1/τ has stopped moving. Field
traces (2026-10, all five zones of one flat) showed τ swinging daily between
~20 h and the 200 h cap, with the runtime recovery resetting it to the 6.7 h
prior after 50 pegged updates; ``identified`` stayed True throughout, so the
optimal-stop planner coasted whole comfort windows on a 200 h τ.

This gate is the conservative answer, pure and HA-free (ADR-0005/0011):

* **near a bound** — τ ≥ ``NEAR_BOUND_TAU_HIGH_H`` or ≤ ``NEAR_BOUND_TAU_LOW_H``
  is not a physical estimate, it is the filter running into its clamp;
* **freshly reset** — the recovery reset puts α back on the prior, which is a
  guess, not a learned value;
* **unstable** — over the last ``TRUST_WINDOW_H`` hours τ must stay within a
  factor ``TRUST_MAX_RATIO`` (max/min of hourly buckets).

Any near-bound sample or reset clears the window, so trust has to be re-earned
over a full window afterwards. Observation gaps (restart, missed ticks) are
capped per step and do not count as observed time. A missing persisted state
starts untrusted (conservative on upgrade).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

TRUST_WINDOW_H = 24.0  # stable time required before τ is trusted
TRUST_MAX_RATIO = 2.0  # max/min τ over the window at/under which τ is stable
NEAR_BOUND_TAU_HIGH_H = 150.0  # EKF cap is 200 h — 75 % of it counts as pegged
NEAR_BOUND_TAU_LOW_H = 1.0  # EKF floor is 0.5 h
_BUCKET_H = 1.0  # window resolution
_MAX_BUCKETS = int(TRUST_WINDOW_H / _BUCKET_H)
_MAX_STEP_H = 1.0 / 6.0  # a gap longer than 10 min is not observed time


def near_bound(tau_h: float) -> bool:
    """τ at/near the EKF clamp (or not finite) — not a physical estimate."""
    if not math.isfinite(tau_h):
        return True
    return tau_h >= NEAR_BOUND_TAU_HIGH_H or tau_h <= NEAR_BOUND_TAU_LOW_H


@dataclass(frozen=True, slots=True)
class TauTrust:
    """Rolling τ-stability record since the last near-bound sample / reset."""

    clean_h: float = 0.0  # observed time since the last near-bound / reset event
    bucket_h: float = 0.0  # time accumulated in the newest bucket
    window: tuple[tuple[float, float], ...] = ()  # (min τ, max τ) per bucket

    @property
    def spread_ratio(self) -> float:
        """max τ / min τ over the window; ``inf`` while empty."""
        if not self.window:
            return math.inf
        lo = min(b[0] for b in self.window)
        hi = max(b[1] for b in self.window)
        return hi / lo if lo > 0.0 else math.inf

    @property
    def trusted(self) -> bool:
        return self.clean_h >= TRUST_WINDOW_H and self.spread_ratio <= TRUST_MAX_RATIO

    def to_dict(self) -> dict[str, Any]:
        return {
            "clean_h": self.clean_h,
            "bucket_h": self.bucket_h,
            "window": [list(b) for b in self.window],
        }

    @classmethod
    def from_dict(cls, data: Any) -> TauTrust:
        """Restore; anything malformed falls back to an untrusted fresh record."""
        try:
            window = tuple((float(b[0]), float(b[1])) for b in data.get("window", []))[
                -_MAX_BUCKETS:
            ]
            clean_h = float(data.get("clean_h", 0.0))
            bucket_h = float(data.get("bucket_h", 0.0))
        except (AttributeError, TypeError, ValueError, IndexError):
            return cls()
        values = [clean_h, bucket_h, *(v for b in window for v in b)]
        if not all(math.isfinite(v) for v in values) or clean_h < 0.0:
            return cls()
        return cls(clean_h=clean_h, bucket_h=max(0.0, bucket_h), window=window)


def observe_tau(
    prev: TauTrust, *, tau_h: float, dt_h: float, reset: bool = False
) -> TauTrust:
    """Fold one post-update τ sample into the trust record."""
    if reset or near_bound(tau_h):
        return TauTrust()
    dt = min(max(0.0, dt_h), _MAX_STEP_H)
    window = list(prev.window)
    bucket_h = prev.bucket_h
    if not window or bucket_h >= _BUCKET_H:
        window.append((tau_h, tau_h))
        bucket_h = 0.0
    else:
        lo, hi = window[-1]
        window[-1] = (min(lo, tau_h), max(hi, tau_h))
    return TauTrust(
        clean_h=prev.clean_h + dt,
        bucket_h=bucket_h + dt,
        window=tuple(window[-_MAX_BUCKETS:]),
    )
