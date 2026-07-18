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
    # R5: optional valve non-idealities for validating direct-valve (TPI) control
    # against a realistic actuator. Defaults are a perfectly linear valve, so the
    # existing setpoint/EKF harness is byte-for-byte unchanged.
    valve_deadband: float = 0.0  # commanded fraction below which no flow passes
    valve_curve: float = 1.0  # authority exponent (1 = linear, >1 = equal-%-ish)

    def flow(self, duty: float) -> float:
        """Effective heat fraction from a commanded valve duty (R5).

        At/below ``valve_deadband`` the seat is effectively shut (stiction / low
        authority); above it the remaining travel is remapped through
        ``valve_curve``. Perfectly linear by default (``flow(d) == d``).
        """
        d = max(0.0, min(1.0, duty))
        if d <= self.valve_deadband:
            return 0.0
        span = 1.0 - self.valve_deadband
        x = (d - self.valve_deadband) / span if span > 0.0 else 1.0
        return float(x**self.valve_curve)

    def step(self, t_air: float, power: float, t_out: float, dt: float) -> float:
        """Advance the room temperature by ``dt`` seconds under constant power."""
        t_eq = t_out + self.full_power_rise * self.flow(power)
        return t_eq + (t_air - t_eq) * math.exp(-self.alpha * dt)
