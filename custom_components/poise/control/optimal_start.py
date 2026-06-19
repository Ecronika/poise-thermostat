"""Optimal-start preheat advisory (ADR-0025).

From the learned thermal model, estimate how long full heating needs to lift
the room from its current temperature to the comfort target, then advise whether
to begin preheating *now* so comfort is reached by the scheduled deadline.

Physics: the ZOH room model converges to ``t_eq = t_out + drive/alpha`` with a
time constant ``1/alpha``. Inverting the exponential gives the heat-up time
analytically. If ``t_eq`` does not clear the target the heater cannot get there
(reachable=False) and we fall back to "start as early as the horizon allows".

Advisory only: the caller gates this on an *identified* EKF and applies the
result as a schedule shift; it never commands the actuator (avoids the re-entry
bug class K5). Pure, unit-tested.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..estimation.thermal_ekf import ThermalModel

_MIN_ALPHA = 1e-4  # guard against div-by-zero on a degenerate model
_T_EQ_MARGIN = 0.1  # equilibrium must clear the target by this margin [K]


@dataclass(frozen=True, slots=True)
class PreheatAdvice:
    """Optimal-start verdict for one tick."""

    reachable: bool  # target attainable within the planning horizon
    lead_minutes: float  # estimated heating minutes needed to reach target
    start_now: bool  # comfort deadline is within the lead time -> preheat


def heatup_minutes(
    model: ThermalModel,
    *,
    room: float,
    target: float,
    t_out: float,
    q_solar: float = 0.0,
    q_occ: float = 0.0,
    max_lead_h: float = 4.0,
) -> float | None:
    """Minutes of full heating to reach ``target``; None if unreachable in time."""
    if room >= target:
        return 0.0
    alpha = max(model.alpha, _MIN_ALPHA)
    drive = model.beta_h + model.beta_s * q_solar + model.beta_o * q_occ
    t_eq = t_out + drive / alpha
    if t_eq <= target + _T_EQ_MARGIN:
        return None  # heating power cannot lift the room to target
    ratio = (target - t_eq) / (room - t_eq)  # in (0, 1)
    t_h = -math.log(ratio) / alpha
    if t_h > max_lead_h:
        return None  # reachable in principle, but not within the horizon
    return t_h * 60.0


def advise(
    model: ThermalModel,
    *,
    room: float,
    target: float,
    t_out: float,
    minutes_to_comfort: float,
    q_solar: float = 0.0,
    q_occ: float = 0.0,
    max_lead_h: float = 4.0,
) -> PreheatAdvice:
    """Advise whether to begin preheating to hit the comfort deadline."""
    lead = heatup_minutes(
        model,
        room=room,
        target=target,
        t_out=t_out,
        q_solar=q_solar,
        q_occ=q_occ,
        max_lead_h=max_lead_h,
    )
    if lead is None:  # best effort: heat from the horizon edge so we arrive warm
        horizon_min = max_lead_h * 60.0
        return PreheatAdvice(False, horizon_min, minutes_to_comfort <= horizon_min)
    return PreheatAdvice(True, lead, minutes_to_comfort <= lead)


def mean_forecast_outdoor(
    samples: Sequence[tuple[float, float]],
    horizon_min: float,
    fallback: float,
) -> float:
    """Time-weighted mean forecast outdoor temp over [0, horizon_min] minutes.

    ``samples`` are ``(minutes_from_now, temperature_c)`` points (any order). The
    curve is piecewise-linear between samples and held flat outside their range
    (matches ha-preheat's forecast integration). Returns ``fallback`` when there
    is no usable horizon or no samples — so a missing/short forecast degrades to
    the caller's constant-outdoor estimate rather than failing.
    """
    if horizon_min <= 0.0 or not samples:
        return fallback
    pts = sorted(samples)

    def temp_at(m: float) -> float:
        if m <= pts[0][0]:
            return pts[0][1]
        if m >= pts[-1][0]:
            return pts[-1][1]
        for (a_m, a_t), (b_m, b_t) in zip(pts, pts[1:], strict=False):
            if a_m <= m <= b_m:
                if b_m == a_m:
                    return a_t
                frac = (m - a_m) / (b_m - a_m)
                return a_t + frac * (b_t - a_t)
        return pts[-1][1]

    breaks = sorted({0.0, horizon_min, *(m for m, _ in pts if 0.0 < m < horizon_min)})
    integral = 0.0
    for x0, x1 in zip(breaks, breaks[1:], strict=False):
        integral += 0.5 * (temp_at(x0) + temp_at(x1)) * (x1 - x0)
    return integral / horizon_min
