"""Greedy receding-horizon MPC power optimizer (ADR-0001).

Consumes a frozen ThermalModel (from the EKF, ADR-0002) read-only and optimizes
the *first-step* heating power by forward-simulating each candidate over the
horizon under a greedy dead-band policy, then re-solving every tick. This gives
a variable trajectory across ticks without a QP. Comfort cost is dead-zone
aware with an asymmetric overshoot penalty (Better Thermostat); energy is
penalised mildly. Pure stdlib (ADR-0022).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..estimation.thermal_ekf import ThermalModel


@dataclass(frozen=True, slots=True)
class MpcParams:
    horizon_blocks: int = 12
    dt_h: float = 5.0 / 60.0  # 5-minute blocks
    w_comfort: float = 1.0
    w_energy: float = 0.02
    overshoot_penalty: float = 8.0  # asymmetric: overshoot weighs ~9x
    coarse_step: float = 0.1


def _comfort_cost(
    t: float, target: float, lower: float, upper: float, overshoot_penalty: float
) -> float:
    # Always track the neutral target; add an asymmetric extra penalty for
    # leaving the band (overshoot weighs far more than undershoot, per BT).
    cost = (t - target) ** 2
    if t > upper:
        over = t - upper
        cost += overshoot_penalty * over * over
    elif t < lower:
        under = lower - t
        cost += under * under
    return cost


def _rollout_cost(
    model: ThermalModel,
    t0: float,
    first_power: float,
    target: float,
    lower: float,
    upper: float,
    t_out: float,
    params: MpcParams,
) -> float:
    t = model.predict(t0, params.dt_h, t_out, u_h=first_power)
    cost = (
        params.w_comfort
        * _comfort_cost(t, target, lower, upper, params.overshoot_penalty)
        + params.w_energy * first_power
    )
    for _ in range(params.horizon_blocks - 1):
        power = 1.0 if t < target else 0.0  # greedy dead-band continuation
        t = model.predict(t, params.dt_h, t_out, u_h=power)
        cost += (
            params.w_comfort
            * _comfort_cost(t, target, lower, upper, params.overshoot_penalty)
            + params.w_energy * power
        )
    return cost


def optimize_power(
    model: ThermalModel,
    t0: float,
    target: float,
    lower: float,
    upper: float,
    t_out: float,
    params: MpcParams | None = None,
) -> float:
    """Return the optimal first-step heating power in [0, 1]."""
    params = params or MpcParams()
    best_power = 0.0
    best_cost = float("inf")
    steps = int(round(1.0 / params.coarse_step))
    for i in range(steps + 1):
        cand = i * params.coarse_step
        cost = _rollout_cost(model, t0, cand, target, lower, upper, t_out, params)
        if cost < best_cost - 1e-12:
            best_cost, best_power = cost, cand
    return best_power
