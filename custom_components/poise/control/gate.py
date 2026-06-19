"""Soft MPC<->bang-bang gating (ADR-0009).

Instead of a hard flip, blend the two control outputs by a confidence weight
derived from the EKF prediction std. Hysteresis at the controller prevents
regime pumping; hard data-gates remain a lower bound (handled by the caller).
"""

from __future__ import annotations

MPC_THRESHOLD_STD: float = 0.5  # above this std -> pure bang-bang
NOISE_FLOOR_STD: float = 0.2  # below this std -> full MPC


def mpc_weight(
    prediction_std: float,
    *,
    threshold: float = MPC_THRESHOLD_STD,
    noise_floor: float = NOISE_FLOOR_STD,
) -> float:
    """Weight in [0, 1] for the MPC output; 1 = confident, 0 = noisy."""
    weight = (threshold - prediction_std) / (threshold - noise_floor)
    return min(1.0, max(0.0, weight))


def blend(u_mpc: float, u_bangbang: float, weight: float) -> float:
    """Convex blend of the two control outputs."""
    return weight * u_mpc + (1.0 - weight) * u_bangbang
