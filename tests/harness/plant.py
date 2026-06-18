"""Analytic 1R1C room model — the shared plant physics (ADR-0011).

This is the *same* RC formulation the production estimator/optimizer will
use, so harness tests exercise real physics, not an attrappe. The closed-form
zero-order-hold solution (not naive Euler) matches the EKF discretisation
chosen in ADR-0002.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from custom_components.poise.const import (
    DEFAULT_ALPHA_PER_S,
    DEFAULT_FULL_POWER_RISE_C,
)


@dataclass(slots=True)
class RCPlant:
    alpha: float = DEFAULT_ALPHA_PER_S  # 1/s, ~6.7 h time constant
    full_power_rise: float = DEFAULT_FULL_POWER_RISE_C  # °C at power = 1.0

    def step(self, t_air: float, power: float, t_out: float, dt: float) -> float:
        """Advance the room temperature by ``dt`` seconds under constant power."""
        t_eq = t_out + self.full_power_rise * power
        return t_eq + (t_air - t_eq) * math.exp(-self.alpha * dt)
