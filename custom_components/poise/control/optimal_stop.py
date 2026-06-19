"""Advisory residual-heat estimate for Optimal Stop / coasting (ADR-0003).

Pure function: returns the fraction (0..1) of the learned heating rate still
delivered by the thermal mass after the heater stops. The MPC consumes it as a
disturbance term in its prediction (HVAC-off gated); it never commands the
actuator itself, which avoids the re-entry bug class (K5).
"""

from __future__ import annotations

import math


def residual_fraction(
    elapsed_h: float,
    heating_duration_h: float,
    *,
    tau_h: float = 1.0,
    tau_charge_h: float = 0.5,
) -> float:
    """Charge/discharge double-exponential residual heat fraction in [0, 1]."""
    if elapsed_h < 0.0 or heating_duration_h <= 0.0:
        return 0.0
    charge = 1.0 - math.exp(-heating_duration_h / tau_charge_h)
    discharge = math.exp(-elapsed_h / tau_h)
    return min(1.0, max(0.0, charge * discharge))
