"""Season-invariant heating-rate prior (ThermoSmart Feat 2; charter G12, ADR-0004/0009).

Normalises the observed heat-up rate by the driving temperature difference
(``heat_rate / (target - outdoor)``) so a mild-October and a cold-January
observation become comparable, then pools observations with a Gaussian
outdoor-similarity kernel and a half-life forgetting weight (ThermoSmart:
σ_temp ≈ 5 K, 180-day half-life). The result is used ONLY as an EKF
cold-start prior / fallback — it never controls in parallel with the EKF
(Programmstrukturplan; charter G6). Shadow estimator (ADR-0026): it always
accumulates and is persisted, even while the EKF owns the live model.

Physics note: at the start of a heat-up the room rate dT/dt ≈ beta_h (the EKF
heating responsivity), because the loss term alpha·(T−T_out) is still small.
So the predicted heat-up rate doubles as a beta_h seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

HALF_LIFE_DAYS: float = 180.0  # ThermoSmart forgetting half-life (G12)
TEMP_SIGMA: float = 5.0  # outdoor-temperature similarity kernel σ [K]
MIN_DRIVE_K: float = 1.0  # ignore observations with a tiny driving ΔT
HISTORY_CAP: int = 200
_MATURE = 150  # learning-phase thresholds: <5 cold / <50 early / <150 learning


def normalized_rate(heat_rate: float, target: float, outdoor: float) -> float | None:
    """Season-invariant rate ``heat_rate / (target - outdoor)``; None if ΔT tiny."""
    drive = target - outdoor
    if drive < MIN_DRIVE_K:
        return None
    return heat_rate / drive


def gaussian_weight(delta: float, sigma: float) -> float:
    """Similarity weight ``exp(-½(Δ/σ)²)`` in (0, 1]."""
    if sigma <= 0.0:
        return 1.0 if delta == 0.0 else 0.0
    return math.exp(-0.5 * (delta / sigma) ** 2)


def half_life_weight(age_days: float, half_life: float = HALF_LIFE_DAYS) -> float:
    """Exponential forgetting weight; 1 at age 0, ½ at one half-life."""
    if age_days <= 0.0 or half_life <= 0.0:
        return 1.0
    return math.exp(-math.log(2.0) * age_days / half_life)


@dataclass
class _Obs:
    outdoor: float
    r_norm: float
    day: float


@dataclass
class SeasonlessRate:
    """Accumulates normalised heat-up rates and estimates a season-invariant prior."""

    temp_sigma: float = TEMP_SIGMA
    half_life_days: float = HALF_LIFE_DAYS
    obs: list[_Obs] = field(default_factory=list)

    def observe(
        self, heat_rate: float, target: float, outdoor: float, day: float
    ) -> None:
        """Record one heat-up observation (only when actively heating + rising)."""
        r = normalized_rate(heat_rate, target, outdoor)
        if r is None or r <= 0.0:
            return
        self.obs.append(_Obs(outdoor, r, day))
        if len(self.obs) > HISTORY_CAP:
            del self.obs[: len(self.obs) - HISTORY_CAP]

    @property
    def count(self) -> int:
        return len(self.obs)

    @property
    def mean_outdoor(self) -> float | None:
        return sum(o.outdoor for o in self.obs) / len(self.obs) if self.obs else None

    @property
    def phase(self) -> str:
        n = len(self.obs)
        if n >= _MATURE:
            return "mature"
        if n >= 50:
            return "learning"
        if n >= 5:
            return "early"
        return "cold"

    def estimate_norm(self, outdoor: float, now_day: float) -> float | None:
        """Kernel + half-life weighted normalised rate for ``outdoor``."""
        num = den = 0.0
        for o in self.obs:
            w = gaussian_weight(
                outdoor - o.outdoor, self.temp_sigma
            ) * half_life_weight(now_day - o.day, self.half_life_days)
            num += w * o.r_norm
            den += w
        return num / den if den > 0.0 else None

    def heat_rate_prior(
        self, target: float, outdoor: float, now_day: float
    ) -> float | None:
        """Expected heat-up rate for the given conditions (≈ a beta_h seed)."""
        r = self.estimate_norm(outdoor, now_day)
        if r is None:
            return None
        drive = target - outdoor
        if drive < MIN_DRIVE_K:
            return None
        return r * drive

    def to_dict(self) -> dict[str, Any]:
        return {
            "temp_sigma": self.temp_sigma,
            "half_life_days": self.half_life_days,
            "obs": [[o.outdoor, o.r_norm, o.day] for o in self.obs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeasonlessRate:
        obs = [
            _Obs(float(x[0]), float(x[1]), float(x[2]))
            for x in data.get("obs", [])
            if isinstance(x, (list, tuple)) and len(x) == 3
        ]
        return cls(
            temp_sigma=float(data.get("temp_sigma", TEMP_SIGMA)),
            half_life_days=float(data.get("half_life_days", HALF_LIFE_DAYS)),
            obs=obs,
        )
