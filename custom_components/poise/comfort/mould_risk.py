"""Dose-based mould risk — VTT mould index (ADR-0071).

ADR-0062 judged mould risk from a single INSTANTANEOUS number: surface RH over
80 %, inverted straight into an air-temperature floor. ADR-0071 replaces that
with the VTT mould index (Hukka & Viitanen 1999; sensitivity classes from
Ojanen et al., *Buildings XI*, 2010), the dose model ASHRAE 160 Addendum e
(2016) adopted normatively. The index integrates *how long* a surface stayed
above its critical humidity, at what temperature, on what substrate — and it
decays again while the surface is dry.

WHY a dose model at all: 80 % surface RH is the LOWER bound of possible growth,
not a growth event. Germination inside 1-2 days needs > 90 % RH at 15-25 °C;
at 81 % and 20 °C the same model puts germination at 127 days. Six 90-day
hourly scenarios (ADR-0071 §1) quantify what that buys: the instantaneous
criterion would have raised the floor for 720 h at a thermal bridge whose
surface RH merely peaks at 85 % overnight, for 360 h after bathroom showers
and for 102 h on intermittent peaks — 1182 h of heating for transients that
never approach a germination dose. The dose model raises it for none of the
three and keeps FULL protection in the one genuinely chronic case (a steady
82 %), from day one. What it does NOT do is catch cases the old criterion
missed; the gain is the absence of false alarms, plus a chronic layer that
accumulates across seasons.

Index scale (VTT): 0 = no growth, 1 = microscopic growth / germination,
2 = visible growth (first hyphae, ~10 % coverage), ... 6 = heavy coverage.
Poise engages protection at 2 because Künzel (ORNL 2016) puts the tolerable
limit for INTERIOR surfaces at MI 2 — visible growth indoors is already a
hygiene failure, whereas the ASHRAE 160 limit of 3 is written for concealed
assembly layers.

This module is PURE: no Home Assistant, no ``ha/``, ``runtime/`` or
``control/`` imports. Its only dependency is the shared psychrometry in
``comfort.mold`` / ``estimation.psychrometrics``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from ..estimation.psychrometrics import saturation_pressure, vapour_pressure
from .mold import (
    DEFAULT_F_RSI,
    surface_relative_humidity,
    surface_temperature,
)

# --- Engage / release thresholds -------------------------------------------

# Warm start for a zone with no history: "germination happened at some point,
# no visible growth" on the VTT scale — the honest prior for an existing,
# lived-in surface, which is NOT at a pristine 0 the way a lab coupon is
# (ADR-0071 §4). Deliberately NOT justified by responsiveness: for the default
# class SENSITIVE ``k1_hi`` (0.386) is SMALLER than ``k1_lo`` (0.578), so above
# index 1 the index grows more slowly, not faster. Day-one protection comes
# from the acute backstop (§5), never from the index.
WARM_START_INDEX: Final[float] = 1.0
# Künzel (ORNL 2016): MI 2 is visible growth, the interior-surface limit.
INDEX_ENGAGE: Final[float] = 2.0
# Release below engage: the index moves slowly, so without hysteresis the floor
# would chatter across the 2.0 line for days on end.
INDEX_RELEASE: Final[float] = 1.5
INDEX_MAX: Final[float] = 6.0
# Acute backstop. The index is a dose and needs weeks; a bathroom that is
# soaking wet for two straight days must be answered on day 1, independent of
# whatever index the zone has learned so far (ADR-0071 §5).
ACUTE_WET_HOURS: Final[float] = 48.0
# Carried over from ADR-0062: the floor must not chase the singularity of a
# near-saturated wall to absurd setpoints. Hitting it is reported (``capped``),
# not silently swallowed.
FLOOR_CEILING_C: Final[float] = 24.0
# Hukka & Viitanen decline rates, converted from per-day to PER HOUR
# (-0.032/d and -0.016/d). Between 6 h and 24 h of dryness the index holds
# (the plateau, see :func:`index_step`).
DECLINE_LT_6H: Final[float] = -0.00133
DECLINE_GT_24H: Final[float] = -0.000667

# --- Internal numeric guards ------------------------------------------------

# Mirrors the private ``_F_RSI_FLOOR`` in :mod:`comfort.mold`: f_Rsi is in
# (0, 1]; a 0 from a mis-typed option would divide by zero in the inversion.
_F_RSI_FLOOR: Final[float] = 0.1
# Growth-model validity window (Hukka & Viitanen): the regression is fitted for
# 0 < T < 50 °C; ln(T) is undefined at or below 0 anyway.
_T_GROWTH_MIN: Final[float] = 0.0
_T_GROWTH_MAX: Final[float] = 50.0
# The Ojanen M_max ramp is normalised over (100 - rh_crit). At 0 °C the
# critical line IS 100 %, so that span collapses; below this width we treat the
# surface as fully saturated (x = 1) instead of dividing by ~0.
_RH_SPAN_FLOOR: Final[float] = 1e-9
# The Hukka & Viitanen growth rate is expressed per DAY (its denominator is
# 7 · t_m with t_m the time-to-appearance in weeks). Poise ticks in hours, and
# the decline constants above are already per hour, so growth is converted here
# rather than silently mixing the two time bases.
_HOURS_PER_DAY: Final[float] = 24.0
# Ojanen Eq. 1 is only fitted up to 20 °C; above that the critical humidity is
# the class's flat floor.
_CRIT_RH_T_MAX: Final[float] = 20.0
# Bisection budget for :func:`required_air_temperature`. 60 halvings of a
# <= 24 K bracket land far below float resolution — the cost is 60 cheap
# exp() calls once per tick, and it removes any "did it converge?" question.
_BISECTION_STEPS: Final[int] = 60


class SubstrateClass(StrEnum):
    """Ojanen et al. (2010) material sensitivity classes."""

    VERY_SENSITIVE = "very_sensitive"  # untreated pine sapwood (the VTT origin)
    SENSITIVE = "sensitive"  # paper-faced plasterboard, wallpaper, spruce
    MEDIUM_RESISTANT = "medium_resistant"  # cement/lime render, mineral wool
    RESISTANT = "resistant"  # glass, metal, alkaline concrete surfaces


@dataclass(frozen=True, slots=True)
class SubstrateSpec:
    """Growth coefficients of one sensitivity class (Ojanen Tab. 4 / Tab. 6).

    ``k1_lo``/``k1_hi`` are the growth-intensity factors below and from index 1
    (the k1 branch switches at germination). ``a``/``b``/``c`` parameterise the
    maximum attainable index M_max. ``rh_min`` is the class's lowest critical
    humidity, ``decline`` is Ojanen's C_mat: how much of the reference decline
    rate the material actually sees when it dries out.
    """

    k1_lo: float
    k1_hi: float
    a: float
    b: float
    c: float
    rh_min: float
    decline: float


SUBSTRATES: Final[Mapping[SubstrateClass, SubstrateSpec]] = {
    SubstrateClass.VERY_SENSITIVE: SubstrateSpec(
        k1_lo=1.0, k1_hi=2.0, a=1.0, b=7.0, c=2.0, rh_min=80.0, decline=1.0
    ),
    SubstrateClass.SENSITIVE: SubstrateSpec(
        k1_lo=0.578, k1_hi=0.386, a=0.3, b=6.0, c=1.0, rh_min=80.0, decline=0.5
    ),
    SubstrateClass.MEDIUM_RESISTANT: SubstrateSpec(
        k1_lo=0.072, k1_hi=0.097, a=0.0, b=5.0, c=1.5, rh_min=85.0, decline=0.25
    ),
    SubstrateClass.RESISTANT: SubstrateSpec(
        k1_lo=0.033, k1_hi=0.014, a=0.0, b=3.0, c=1.0, rh_min=85.0, decline=0.1
    ),
}

# Paper-faced plasterboard / wallpaper is what an ordinary German interior wall
# is finished with, so "sensitive" is the honest default when nobody has told
# us otherwise (ADR-0071 §3).
DEFAULT_SUBSTRATE: Final[SubstrateClass] = SubstrateClass.SENSITIVE

# LATENT BY DESIGN — deliberately not wired to any configuration option yet and
# therefore called by NOBODY in this release. It is the prepared room-profile ->
# substrate map for the later config step (ADR-0071 §3), kept here so the
# mapping is decided once, next to the coefficients it selects, rather than
# invented ad hoc when the option lands. Do NOT delete it as dead code: the
# same "prepared, not yet routed" marking carries ``CONF_OVERRIDE_SUGGESTIONS``
# in ``const.py``.
ROOM_PROFILE_SUBSTRATE: Final[Mapping[str, SubstrateClass]] = {
    "living": SubstrateClass.SENSITIVE,  # wallpaper / plasterboard = paper-faced
    "bedroom": SubstrateClass.SENSITIVE,
    "bathroom": SubstrateClass.MEDIUM_RESISTANT,  # tile / render
    "kitchen": SubstrateClass.MEDIUM_RESISTANT,
    "office": SubstrateClass.SENSITIVE,
}


def critical_rh(t_surface: float, spec: SubstrateSpec) -> float:
    """Lowest surface RH [%] at which growth is possible, Ojanen Eq. 1.

    ``RH_crit = -0.00267·T³ + 0.160·T² - 3.13·T + 100`` for T <= 20 °C; above
    that the cubic is no longer fitted and the class floor governs. The result
    never drops below ``spec.rh_min`` — the cubic dips ~0.1 pp under 80 %
    around 17 °C, which is regression noise, not a physical effect.
    """
    if t_surface > _CRIT_RH_T_MAX:
        return spec.rh_min
    cubic = -0.00267 * t_surface**3 + 0.160 * t_surface**2 - 3.13 * t_surface + 100.0
    return max(cubic, spec.rh_min)


def max_index(t_surface: float, rh_surface: float, spec: SubstrateSpec) -> float:
    """Maximum index M_max the current conditions can ever reach (Ojanen Eq. 3).

    ``M_max = a + b·x - c·x²`` where x normalises the humidity surplus between
    the critical line (x = 0) and saturation (x = 1). This is what keeps a
    permanently damp-but-not-wet wall from creeping to 6: at 82 % surface RH a
    sensitive substrate tops out well below the engage threshold — the very
    false positive that sank the static 80 % criterion.
    """
    rh_crit = critical_rh(t_surface, spec)
    if rh_surface <= rh_crit:
        return 0.0  # below the critical line nothing can grow at all
    # Written with both signs of the SPEC form (rh_crit - rh)/(rh_crit - 100)
    # flipped — algebraically identical, but the denominator is then a positive
    # span, so the degenerate 0 °C case (rh_crit == 100) is a readable guard.
    span = 100.0 - rh_crit
    x = 1.0 if span <= _RH_SPAN_FLOOR else (rh_surface - rh_crit) / span
    x = min(max(x, 0.0), 1.0)  # surfaces above saturation are still just x = 1
    return min(max(spec.a + spec.b * x - spec.c * x**2, 0.0), INDEX_MAX)


def _growth_per_hour(
    index: float, t_surface: float, rh_surface: float, spec: SubstrateSpec
) -> float:
    """Hukka & Viitanen growth rate [index points per hour].

    ``dM/dt = k1·k2 / (7·exp(-0.68·lnT - 13.9·lnRH + 0.14·W - 0.33·SQ + 66.02))``
    with W = SQ = 0 (no wood-species / surface-quality correction: Poise does
    not know the finish, and 0 is the fastest-growing, i.e. safest, choice).
    The literature rate is per DAY, so it is divided by 24 here — the decline
    constants are already per hour and the two must share a time base.
    """
    # k1 switches at germination: before index 1 the colony is establishing,
    # afterwards it spreads at the class's own rate (Ojanen Tab. 4).
    k1 = spec.k1_lo if index < 1.0 else spec.k1_hi
    # k2 throttles growth to a halt as the index approaches what the current
    # humidity can sustain; it goes negative past M_max, hence the clamp.
    k2 = max(
        1.0 - math.exp(2.3 * (index - max_index(t_surface, rh_surface, spec))), 0.0
    )
    exponent = -0.68 * math.log(t_surface) - 13.9 * math.log(rh_surface) + 66.02
    return k1 * k2 / (7.0 * math.exp(exponent)) / _HOURS_PER_DAY


def index_step(
    index: float,
    *,
    t_surface: float,
    rh_surface: float,
    dt_h: float,
    dry_hours: float,
    spec: SubstrateSpec,
) -> float:
    """Advance the mould index by one tick of ``dt_h`` hours.

    Grows while the surface is at or above :func:`critical_rh` and the
    temperature is inside the model's validity window; otherwise it declines.
    The decline is deliberately three-staged (Hukka & Viitanen): fast for the
    first 6 dry hours, then a PLATEAU up to 24 h during which the index does
    not move at all, then slow again. The plateau is the reason a daily
    short-airing routine does not reset the dose — a colony survives a day of
    dryness essentially intact, and the model has to say so.
    """
    rh_crit = critical_rh(t_surface, spec)
    if rh_surface >= rh_crit and _T_GROWTH_MIN < t_surface < _T_GROWTH_MAX:
        delta = _growth_per_hour(index, t_surface, rh_surface, spec) * dt_h
    else:
        if dry_hours <= 6.0:
            rate = DECLINE_LT_6H
        elif dry_hours <= 24.0:
            rate = 0.0
        else:
            rate = DECLINE_GT_24H
        # C_mat: a resistant material barely loses its (small) index again —
        # the decline scales with the same class factor as the growth.
        delta = rate * spec.decline * dt_h
    return min(max(index + delta, 0.0), INDEX_MAX)


def _surface_rh_excess(
    t_air: float,
    *,
    t_out: float,
    p_v: float,
    f_rsi: float,
    spec: SubstrateSpec,
) -> float:
    """Surface RH minus its critical line [pp] at a candidate air temperature.

    Positive means the surface is still in the growth region. Monotonically
    decreasing in ``t_air`` — warming the surface raises p_sat much faster than
    it lowers the Ojanen critical line — which is what makes the plain
    bisection in :func:`required_air_temperature` valid.
    """
    t_si = surface_temperature(t_air, t_out, f_rsi)
    rh_si = 100.0 * p_v / saturation_pressure(t_si)
    return rh_si - critical_rh(t_si, spec)


def required_air_temperature(
    *,
    t_out: float,
    rh_room: float,
    t_room: float,
    f_rsi: float,
    spec: SubstrateSpec,
) -> tuple[float, bool]:
    """Air temperature [°C] that pushes the surface RH back to the critical line.

    Returns ``(floor, capped)``. ``capped`` is True when even
    ``FLOOR_CEILING_C`` fails the criterion — protection by heating alone is
    then INSUFFICIENT and the room genuinely needs dehumidification or
    ventilation; surfacing that beats silently under-protecting (ADR-0062 F15,
    carried into ADR-0071).

    Solved by bisection rather than in closed form because the target is
    implicit: warming the air warms the surface, which lowers the surface RH
    but ALSO lowers ``critical_rh`` (the Ojanen cubic falls with temperature up
    to 20 °C). Both sides of the comparison move, so the ADR-0062 one-line
    inversion no longer applies. The absolute moisture content is held constant
    (vapour pressure from the CURRENT room state): heating dries the surface by
    warming it, it does not remove water.
    """
    f = min(max(f_rsi, _F_RSI_FLOOR), 1.0)
    p_v = vapour_pressure(t_room, rh_room)
    lo = min(t_out, FLOOR_CEILING_C)  # a summer t_out above the ceiling stays sane
    hi = FLOOR_CEILING_C
    if _surface_rh_excess(hi, t_out=t_out, p_v=p_v, f_rsi=f, spec=spec) > 0.0:
        return FLOOR_CEILING_C, True
    if _surface_rh_excess(lo, t_out=t_out, p_v=p_v, f_rsi=f, spec=spec) <= 0.0:
        return lo, False  # already safe at outdoor temperature: no floor needed
    for _ in range(_BISECTION_STEPS):
        mid = 0.5 * (lo + hi)
        if _surface_rh_excess(mid, t_out=t_out, p_v=p_v, f_rsi=f, spec=spec) > 0.0:
            lo = mid
        else:
            hi = mid
    # Return the SAFE end of the bracket, so the criterion always holds at the
    # published floor rather than one float-epsilon short of it.
    return hi, False


@dataclass(frozen=True, slots=True)
class MouldRisk:
    """One tick's mould verdict — the single value the rest of Poise consumes."""

    index: float  # advanced mould index, 0..6
    wet_hours: float  # advanced hours above critical_rh (0 while dry)
    dry_hours: float  # advanced hours below critical_rh (0 while wet)
    engaged: bool  # is the protective floor active?
    floor: float | None  # required minimum air temperature, None when not engaged
    capped: bool  # floor hit FLOOR_CEILING_C -> protection insufficient
    surface_rh: float  # this tick's surface relative humidity [%]
    critical_rh: float  # this tick's critical humidity [%]
    reason: str  # "index" | "acute" | "clear" | "no_humidity"


def evaluate(
    *,
    t_room: float,
    rh_room: float | None,
    t_out: float,
    index: float,
    wet_hours: float,
    dry_hours: float,
    dt_h: float,
    was_engaged: bool,
    spec: SubstrateSpec = SUBSTRATES[DEFAULT_SUBSTRATE],
    f_rsi: float = DEFAULT_F_RSI,
) -> MouldRisk:
    """Advance the dose state by one tick and decide whether the floor engages.

    The ONE entry point for the rest of the integration (ADR-0071 §2): callers
    hand in the persisted counters and get the advanced counters plus the
    verdict back. Keeping the state outside makes the model itself pure and
    trivially replayable in the closed-loop harness.
    """
    t_si = surface_temperature(t_room, t_out, f_rsi)
    rh_crit = critical_rh(t_si, spec)

    if rh_room is None:
        # No humidity sensor (or it went unavailable): the dose state is FROZEN
        # rather than decayed. Guessing "dry" would quietly erode a real,
        # earned index while we are blind. Raising the
        # ``mould_protection_inactive`` issue stays the glue layer's job.
        return MouldRisk(
            index=index,
            wet_hours=wet_hours,
            dry_hours=dry_hours,
            engaged=False,
            floor=None,
            capped=False,
            surface_rh=0.0,
            critical_rh=rh_crit,
            reason="no_humidity",
        )

    # The psychrometry stays in comfort.mold — it is shared with the ADR-0066
    # ventilation/humidity axis and must not fork.
    surface_rh = surface_relative_humidity(t_room, rh_room, t_out, f_rsi) * 100.0

    if surface_rh >= rh_crit:
        wet_hours += dt_h
        dry_hours = 0.0
    else:
        dry_hours += dt_h
        wet_hours = 0.0

    index = index_step(
        index,
        t_surface=t_si,
        rh_surface=surface_rh,
        dt_h=dt_h,
        dry_hours=dry_hours,
        spec=spec,
    )

    if index >= INDEX_ENGAGE:
        engaged, reason = True, "index"
    elif wet_hours >= ACUTE_WET_HOURS:
        # Acute backstop: two days of continuous wetness acts on day 1, before
        # the slow dose has had any chance to climb.
        engaged, reason = True, "acute"
    elif was_engaged and index >= INDEX_RELEASE:
        # Hysteresis: once engaged we hold the floor down to INDEX_RELEASE.
        engaged, reason = True, "index"
    else:
        engaged, reason = False, "clear"

    floor: float | None = None
    capped = False
    if engaged:
        floor, capped = required_air_temperature(
            t_out=t_out, rh_room=rh_room, t_room=t_room, f_rsi=f_rsi, spec=spec
        )

    return MouldRisk(
        index=index,
        wet_hours=wet_hours,
        dry_hours=dry_hours,
        engaged=engaged,
        floor=floor,
        capped=capped,
        surface_rh=surface_rh,
        critical_rh=rh_crit,
        reason=reason,
    )
