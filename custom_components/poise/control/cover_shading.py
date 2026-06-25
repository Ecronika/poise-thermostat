"""Predictive solar shading for covers (ADR-0043, shadow stage).

The only predictive-thermal cover shading in the HA field is RoomMind; this is a
clean re-implementation of its *method* (not its code): forecast the room's peak
operative temperature over the rest of the day and lower a cover before the room
overheats, instead of reacting after the fact. Two-tier forecast — forward-
simulate the learned EKF model when it is confident, else a linear solar
estimate — then a hysteresis decision on a graded 0–100 shade position, gated by
the sun's actual orientation to the surface, and never fighting a manual move.
Pure and unit-tested; the coordinator owns sun/cover I/O and (later) actuation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoverShadeConfig:
    deploy_threshold: float = (
        1.5  # shade when predicted peak exceeds T_upper by this [K]
    )
    hysteresis: float = 0.5  # retract below (deploy_threshold - hysteresis)
    pos_scale: float = 40.0  # shade % per K of excess above the deploy threshold
    pos_deadband: float = 20.0  # ignore position changes smaller than this [%]
    solar_min: float = 0.05  # oriented q_solar below this -> never shade
    linear_beta_s: float = 3.0  # K/h per normalised q in the linear fallback
    linear_lookahead_h: float = 1.0  # fallback horizon
    override_settle_s: float = (
        90.0  # wait this long after a command before trusting drift
    )
    override_drift: float = (
        15.0  # actual-vs-commanded drift [%] that means "user moved it"
    )


_DEFAULT_CFG = CoverShadeConfig()


def orientation_factor(
    elevation_deg: float, azimuth_deg: float, surface_azimuth_deg: float
) -> float:
    """Fraction of sun hitting a vertical surface (RoomMind: cos(el)·cos(Δaz)).

    Zero when the sun is below the horizon or behind the surface, so a cover is
    only shaded when the sun is actually on its side.
    """
    if elevation_deg <= 0.0:
        return 0.0
    f = math.cos(math.radians(elevation_deg)) * math.cos(
        math.radians(azimuth_deg - surface_azimuth_deg)
    )
    return max(0.0, f)


def predict_peak_operative(
    t_now: float,
    t_out: float,
    q_series: list[float],
    *,
    alpha: float,
    beta_s: float,
    dt_h: float,
    confident: bool,
    cfg: CoverShadeConfig = _DEFAULT_CFG,
) -> float:
    """Forecast the peak operative temperature over the solar series.

    Tier 1 (``confident`` and ``alpha > 0``): forward-simulate the RC model with
    the (oriented) solar series via the analytic ZOH step and take the max. Tier
    2: a linear ``t_now + beta_s·max(q)·lookahead`` fallback.
    """
    if confident and q_series and alpha > 0.0:
        decay = math.exp(-alpha * dt_h)
        t = t_now
        peak = t_now
        for q in q_series:
            t_eq = t_out + (beta_s * q) / alpha
            t = t_eq + (t - t_eq) * decay
            peak = max(peak, t)
        return peak
    q_peak = max(q_series) if q_series else 0.0
    return t_now + cfg.linear_beta_s * q_peak * cfg.linear_lookahead_h


def shading_target_position(
    *,
    peak: float,
    t_upper: float,
    current_position: float,
    oriented_q: float,
    cfg: CoverShadeConfig = _DEFAULT_CFG,
) -> tuple[int, str]:
    """Decide the shade position (0=open … 100=fully shaded) + a reason.

    Hysteresis: deploy when the predicted peak exceeds ``t_upper`` by more than
    ``deploy_threshold``, retract below ``deploy_threshold - hysteresis``, hold
    between. A position deadband stops motor flapping. No shade when the sun is
    not on the surface (``oriented_q`` below the floor).
    """
    if oriented_q < cfg.solar_min:
        return (0, "no_sun") if current_position == 0 else (0, "retract")
    excess = peak - t_upper
    if excess > cfg.deploy_threshold:
        target = min(100, int((excess - cfg.deploy_threshold) * cfg.pos_scale))
        if abs(target - current_position) < cfg.pos_deadband:
            return int(current_position), "deadband"
        return target, "deploy"
    if excess < cfg.deploy_threshold - cfg.hysteresis:
        return 0, "retract"
    return int(current_position), "hold"


def cover_user_override(
    actual_position: float,
    last_commanded_position: float,
    seconds_since_command: float,
    cfg: CoverShadeConfig = _DEFAULT_CFG,
) -> bool:
    """True if the user moved the cover manually (drift after the settle delay)."""
    return (
        abs(actual_position - last_commanded_position) > cfg.override_drift
        and seconds_since_command >= cfg.override_settle_s
    )
