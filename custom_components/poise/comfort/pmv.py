"""Fanger PMV/PPD thermal-comfort index (ISO 7730) — pure, stdlib-only (ADR-0054).

Poise reasons about comfort through temperature proxies (operative temperature,
EN 16798 bands). This module adds the integrated ISO 7730 predicted-mean-vote
(PMV) and predicted-percentage-dissatisfied (PPD) so humidity and air velocity
finally enter the comfort *evaluation*. Shadow-first: the coordinator reports
pmv/ppd/category as diagnostics only; the norm temperature band stays the
control variable (ADR-0054 — PMV is never a direct setpoint).

clo/met are not measurable, so they are seasonal defaults (EN 16798-1 Annex B:
~1.0 clo winter, ~0.5 clo summer; met 1.2 sedentary office). PMV is therefore an
*estimate*, not a measurement.
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


def seasonal_clo(t_out_running_mean: float | None) -> float:
    """Seasonal default clothing insulation [clo] (EN 16798-1 Annex B)."""
    if t_out_running_mean is None:
        return CLO_SUMMER
    return CLO_WINTER if t_out_running_mean < 15.0 else CLO_SUMMER
