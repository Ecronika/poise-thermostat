"""Fanger PMV/PPD thermal-comfort index (ISO 7730) — pure, stdlib-only (ADR-0054).

Poise reasons about comfort through temperature proxies (operative temperature,
EN 16798 bands). This module adds the integrated ISO 7730 predicted-mean-vote
(PMV) and predicted-percentage-dissatisfied (PPD) so humidity and air velocity
finally enter the comfort *evaluation*. Shadow-first: the coordinator reports
pmv/ppd/category as diagnostics only; the norm temperature band stays the
control variable (ADR-0054 — PMV is never a direct setpoint).

clo/met are not measurable: clo is the graded ASHRAE 55 predictive clothing
model (Schiavon & Lee 2013) on the outdoor running mean, optionally blended
with today's forecast daily mean (ADR-0054 Nachtrag V1); met stays a fixed
1.2 sedentary-office assumption until the room profiles land (V2). PMV is
therefore an *estimate*, not a measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CLO_WINTER = 1.0
CLO_SUMMER = 0.5
MET_OFFICE = 1.2
STILL_AIR_MS = 0.1  # EN ISO 7726 baseline velocity (matches operative.py)

# EN 16798-1 comfort categories by |PMV|: I < 0.2, II < 0.5, III < 0.7.
_CATEGORY_EDGES: tuple[tuple[float, str], ...] = ((0.2, "I"), (0.5, "II"), (0.7, "III"))


@dataclass(frozen=True, slots=True)
class ComfortIndex:
    pmv: float
    ppd: float  # predicted percentage dissatisfied [%]
    category: str  # "I" | "II" | "III" | "out"


def _category(pmv: float) -> str:
    a = abs(pmv)
    for edge, name in _CATEGORY_EDGES:
        if a <= edge:
            return name
    return "out"


def pmv_ppd(
    *,
    t_air: float,
    t_mrt: float,
    rh: float,
    velocity: float = STILL_AIR_MS,
    clo: float = CLO_SUMMER,
    met: float = MET_OFFICE,
    work: float = 0.0,
) -> ComfortIndex:
    """PMV + PPD (ISO 7730, Fanger). ``rh`` in %, temps in degC, velocity m/s."""
    m = met * 58.15
    w = work * 58.15
    mw = m - w
    icl = 0.155 * clo
    var = max(velocity, STILL_AIR_MS)
    pa = rh * 10.0 * math.exp(16.6536 - 4030.183 / (t_air + 235.0))
    fcl = 1.0 + 1.29 * icl if icl <= 0.078 else 1.05 + 0.645 * icl
    hcf = 12.1 * math.sqrt(var)
    taa = t_air + 273.0
    tra = t_mrt + 273.0
    t_cla = taa + (35.5 - t_air) / (3.5 * icl + 0.1)
    p1 = icl * fcl
    p2 = p1 * 3.96
    p3 = p1 * 100.0
    p4 = p1 * taa
    p5 = 308.7 - 0.028 * mw + p2 * (tra / 100.0) ** 4
    xn = t_cla / 100.0
    xf = t_cla / 50.0
    hc = hcf
    for _ in range(150):
        if abs(xn - xf) <= 0.00015:
            break
        xf = (xf + xn) / 2.0
        hcn = 2.38 * abs(100.0 * xn - taa) ** 0.25
        hc = hcf if hcf > hcn else hcn
        xn = (p5 + p4 * hc - p2 * xf**4) / (100.0 + p3 * hc)
    tcl = 100.0 * xn - 273.0
    hl1 = 3.05 * 0.001 * (5733.0 - 6.99 * mw - pa)
    hl2 = 0.42 * (mw - 58.15) if mw > 58.15 else 0.0
    hl3 = 1.7 * 0.00001 * m * (5867.0 - pa)
    hl4 = 0.0014 * m * (34.0 - t_air)
    hl5 = 3.96 * fcl * (xn**4 - (tra / 100.0) ** 4)
    hl6 = fcl * hc * (tcl - t_air)
    ts = 0.303 * math.exp(-0.036 * m) + 0.028
    pmv = ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)
    ppd = 100.0 - 95.0 * math.exp(-0.03353 * pmv**4 - 0.2179 * pmv**2)
    return ComfortIndex(round(pmv, 2), round(ppd, 1), _category(pmv))


CLO_ANTICIPATION = 1.0 / 3.0  # forecast blend weight w (field-calibration start)
_CLO_T_MIN = -27.2  # Schiavon & Lee (2013) model validity range [degC]
_CLO_T_MAX = 26.0
_CLO_MIN = 0.4  # composition bounds — headroom for the learned offset (V4)
_CLO_MAX = 1.2


def predictive_clo(
    t_out_running_mean: float | None,
    t_forecast_day: float | None = None,
    anticipation: float = CLO_ANTICIPATION,
) -> float:
    """Graded clothing insulation [clo] — ASHRAE 55 predictive clothing model
    (Schiavon & Lee 2013) evaluated on a direction-symmetric blend of thermal
    history and today's forecast daily mean (ADR-0054 Nachtrag V1):
    ``T_eff = (1-w)*T_rm + w*T_forecast``.  The running mean stands in for the
    paper's 6:00 temperature (collinear daily statistics, chosen "arbitrarily"
    there).  No forecast -> pure running-mean input; no running mean -> the
    historical 0.5 summer default."""
    if t_out_running_mean is None:
        return CLO_SUMMER
    t_eff = t_out_running_mean
    if t_forecast_day is not None:
        t_eff = (1.0 - anticipation) * t_eff + anticipation * t_forecast_day
    t = min(max(t_eff, _CLO_T_MIN), _CLO_T_MAX)
    if t < -5.0:
        clo = CLO_WINTER
    elif t < 5.0:
        clo = 0.818 - 0.0364 * t
    elif t < 26.0:
        clo = 10.0 ** (-0.1635 - 0.0066 * t)
    else:
        clo = 0.46
    return min(max(clo, _CLO_MIN), _CLO_MAX)
