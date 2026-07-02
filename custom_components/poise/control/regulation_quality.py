"""Control-accuracy / regulation-quality metric (EN 15500-1 CA), pure (ADR-0055).

Poise doctrine: no feature leaves shadow without a measurable acceptance
criterion. This is that measure — a continuous, bilateral control-quality metric
that turns ADR-0033's prose "flip criteria" into executable numbers and becomes
the gate for every shadow->live flip.

Three time-weighted (EWMA) figures over scored (comfort-window, unmasked) ticks:
  * ``deviation_k``     mean Kelvin the room sits OUTSIDE the comfort band (0
                        in-band; EN 15500-1 control accuracy in a dead-band
                        system — inside the band every point is "on target").
  * ``in_band``         fraction of scored time inside [heat_sp, cool_sp].
  * ``cycles_per_hour`` regime-change rate (mode/actuation transitions) — the
                        hunting detector a band-only metric would miss.

Shadow-first: the coordinator only reports these; the flip gate (meets_quality)
is defined here but wired later, per device class (ADR-0055 section 6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_HORIZON_H = 72.0  # EWMA time constant [h] ~ "recent sustained" quality
DEV_MAX_K = 0.5  # conservative default flip thresholds (per class in wiring)
CYCLE_MAX_PER_H = 3.0
BAND_MIN = 0.9
WARMUP_MIN = 3.0 * 24.0 * 60.0  # >= 3 days of scored comfort minutes before a flip


@dataclass(frozen=True, slots=True)
class RegulationQuality:
    """EWMA accumulator of control quality (persist via to_dict/from_dict)."""

    deviation_k: float = 0.0
    in_band: float = 1.0
    cycles_per_hour: float = 0.0
    minutes: float = 0.0
    last_mode: str = ""

    def observe(
        self,
        *,
        room: float,
        heat_sp: float,
        cool_sp: float,
        mode: str,
        dt_min: float,
        horizon_h: float = DEFAULT_HORIZON_H,
    ) -> RegulationQuality:
        """Fold one scored tick into the EWMA. Call only on unmasked comfort ticks."""
        dev = max(0.0, heat_sp - room, room - cool_sp)
        inb = 1.0 if heat_sp <= room <= cool_sp else 0.0
        moved = 1.0 if (self.last_mode != "" and mode != self.last_mode) else 0.0
        dt_h = max(dt_min, 1e-6) / 60.0
        alpha = 1.0 - math.exp(-dt_min / (horizon_h * 60.0))
        inst_rate = moved / dt_h
        return RegulationQuality(
            deviation_k=(1.0 - alpha) * self.deviation_k + alpha * dev,
            in_band=(1.0 - alpha) * self.in_band + alpha * inb,
            cycles_per_hour=(1.0 - alpha) * self.cycles_per_hour + alpha * inst_rate,
            minutes=self.minutes + dt_min,
            last_mode=mode,
        )

    @property
    def time_in_band_pct(self) -> float:
        return round(self.in_band * 100.0, 1)

    def to_dict(self) -> dict[str, float | str]:
        return {
            "deviation_k": round(self.deviation_k, 4),
            "in_band": round(self.in_band, 4),
            "cycles_per_hour": round(self.cycles_per_hour, 4),
            "minutes": round(self.minutes, 1),
            "last_mode": self.last_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float | str] | None) -> RegulationQuality:
        if not data:
            return cls()
        return cls(
            deviation_k=float(data.get("deviation_k", 0.0)),
            in_band=float(data.get("in_band", 1.0)),
            cycles_per_hour=float(data.get("cycles_per_hour", 0.0)),
            minutes=float(data.get("minutes", 0.0)),
            last_mode=str(data.get("last_mode", "")),
        )


def meets_quality(
    q: RegulationQuality,
    *,
    identified: bool,
    dev_max: float = DEV_MAX_K,
    cycle_max: float = CYCLE_MAX_PER_H,
    band_min: float = BAND_MIN,
    warmup_min: float = WARMUP_MIN,
) -> bool:
    """Steady-state flip gate (ADR-0055 s5). Dwell/hysteresis lives in wiring."""
    return (
        identified
        and q.minutes >= warmup_min
        and q.deviation_k <= dev_max
        and q.cycles_per_hour <= cycle_max
        and q.in_band >= band_min
    )
