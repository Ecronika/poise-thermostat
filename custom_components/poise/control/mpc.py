"""Greedy receding-horizon MPC power optimizer (ADR-0001).

Consumes a frozen ThermalModel (from the EKF, ADR-0002) read-only and optimizes
the *first-step* heating power by forward-simulating each candidate over the
horizon under a coast-in-band continuation (heat only to the lower comfort
edge, then float), then re-solving every tick. This gives a variable trajectory
across ticks without a QP. Comfort cost is a true dead-zone band cost (zero
inside [lower, upper], quadratic outside, overshoot weighted more) so overshoot
is charged at every horizon step, not just the first (best-of: RoomMind/EMHASS,
review M4). Energy is penalised mildly. Pure stdlib (ADR-0022).
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
    t: float, lower: float, upper: float, overshoot_penalty: float
) -> float:
    # Dead-zone band cost (best-of: RoomMind/EMHASS, review M4): zero inside the
    # comfort band, quadratic outside, with the overshoot (upper) side weighted
    # far more heavily. No point-tracking inside the band — that is over-
    # aggressive for a band controller and suppressed horizon overshoot.
    if t > upper:
        over = t - upper
        return overshoot_penalty * over * over
    if t < lower:
        under = lower - t
        return under * under
    return 0.0


def _rollout_cost(
    model: ThermalModel,
    t0: float,
    first_power: float,
    lower: float,
    upper: float,
    t_out: float,
    params: MpcParams,
) -> float:
    t = model.predict(t0, params.dt_h, t_out, u_h=first_power)
    cost = (
        params.w_comfort * _comfort_cost(t, lower, upper, params.overshoot_penalty)
        + params.w_energy * first_power
    )
    for _ in range(params.horizon_blocks - 1):
        # Coast in band: heat only to the LOWER comfort edge, then let the room
        # float (best-of: RoomMind). A too-hot first step then actually drifts
        # above `upper` in the rollout, so its overshoot is charged every step.
        power = 1.0 if t < lower else 0.0
        t = model.predict(t, params.dt_h, t_out, u_h=power)
        cost += (
            params.w_comfort * _comfort_cost(t, lower, upper, params.overshoot_penalty)
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
    """Return the optimal first-step heating power in [0, 1].

    ``target`` is accepted for call-site compatibility but no longer shapes the
    cost: the comfort objective is the dead-zone band [lower, upper] (M4).
    """
    _ = target
    params = params or MpcParams()
    best_power = 0.0
    best_cost = float("inf")
    steps = int(round(1.0 / params.coarse_step))
    for i in range(steps + 1):
        cand = i * params.coarse_step
        cost = _rollout_cost(model, t0, cand, lower, upper, t_out, params)
        if cost < best_cost - 1e-12:
            best_cost, best_power = cost, cand
    return best_power
