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
    *,
    household_offset: float = 0.0,
) -> float:
    """Graded clothing insulation [clo] — ASHRAE 55 predictive clothing model
    (Schiavon & Lee 2013) evaluated on a direction-symmetric blend of thermal
    history and today's forecast daily mean (ADR-0054 Nachtrag V1):
    ``T_eff = (1-w)*T_rm + w*T_forecast``.  The running mean stands in for the
    paper's 6:00 temperature (collinear daily statistics, chosen "arbitrarily"
    there).  No forecast -> pure running-mean input; no running mean -> the
    historical 0.5 summer default.  ``household_offset`` is the learned
    ADR-0067 bias (config, |x| <= 0.3): applied to the PRIOR before the
    bounds clamp — exactly the headroom the 0.4..1.2 bounds reserved."""
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
    return min(max(clo + household_offset, _CLO_MIN), _CLO_MAX)


@dataclass(frozen=True, slots=True)
class RoomProfile:
    """Per-room activity/clothing assumptions (ADR-0054 Nachtrag V2)."""

    met: float  # metabolic rate (ISO 8996 level-1 table values)
    clo_add: float  # additive insulation surcharge (chair/sofa, ISO 9920)


# ISO-8996-level-1 / ASHRAE-55-table values.  "office" is the backward-
# compatible default — exactly the historical fixed assumption (met 1.2, no
# surcharge).  "bedroom" is real sleeping metabolism (ASHRAE 55: 0.7 met) and
# thereby OUTSIDE the ISO 7730 domain — ``pmv_validity`` flags it and the
# shadow publishes no PMV number there (V3).  The sofa surcharge is ISO 9920
# (+0.21); max total clo stays inside the ASHRAE ceiling: 1.2 + 0.21 < 1.5.
ROOM_PROFILES: dict[str, RoomProfile] = {
    "office": RoomProfile(met=MET_OFFICE, clo_add=0.0),
    "living": RoomProfile(met=1.1, clo_add=0.21),
    "bedroom": RoomProfile(met=0.7, clo_add=0.0),
    "kitchen": RoomProfile(met=1.8, clo_add=0.0),
}


def resolve_room_profile(name: str | None) -> RoomProfile:
    """Profile for a config token — unknown/unset falls back to office."""
    return ROOM_PROFILES.get(name or "office", ROOM_PROFILES["office"])


def clo_dynamic(clo: float, met: float) -> float:
    """ASHRAE 55 dynamic insulation: movement pumps the clothing.

    ``Icl,dyn = Icl * (0.6 + 0.4 / met)`` for met > 1.2; identity at or below
    sedentary (Normative Appendix B) — which is why the correction only became
    meaningful once met stopped being fixed at 1.2 (Nachtrag V2).
    """
    if met <= 1.2:
        return clo
    return clo * (0.6 + 0.4 / met)


# ADR-0069 U8: revision tag of the PMV model configuration — part of the
# tier-2 baseline validity signature. Bump on any change to the PMV/clo/met
# computation that makes old PPD baselines incomparable.
PMV_MODEL_REV = "pmv-v1"

# PMV subtleties below +-0.3 carry no information (ADR-0054: pseudo-accuracy)
# — the offset is zero inside the deadband and continuous beyond it.
_PMV_OFFSET_DEADBAND = 0.3


def pmv_setpoint_offset(pmv: float, *, cap_k: float = 1.0) -> float:
    """ADR-0054 Stufe 2: the capped, conservative PMV inversion [K].

    A warm feeling (positive PMV) lowers the band, a cold one raises it —
    1 K per PMV unit beyond the +-0.3 deadband (deliberately far below the
    full physical inversion), hard-capped at the sanctioned +-1 K. The
    solver clamps (EN band, norm envelope) bind on top in ``decide()``.
    """
    magnitude = max(0.0, abs(pmv) - _PMV_OFFSET_DEADBAND)
    offset = min(cap_k, magnitude)
    return round(-offset if pmv > 0 else offset, 2)


def pmv_validity(*, met: float, clo: float) -> bool:
    """Inside the ISO 7730 application domain (0.8-4.0 met, 0-2.0 clo)?

    Outside it — above all sleeping at 0.7 met, where bedding systems
    (0.9-4.9 clo, coverage-dominated) defeat any ensemble estimate — the PMV
    equation is formally not validated: the shadow publishes the flag instead
    of a wrong number (ADR-0054 Nachtrag V3).
    """
    return 0.8 <= met <= 4.0 and 0.0 <= clo <= 2.0
