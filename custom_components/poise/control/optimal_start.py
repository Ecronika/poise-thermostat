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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..estimation.thermal_ekf import ThermalModel
from .optimal_stop import advise_stop

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


@dataclass(frozen=True, slots=True)
class PreheatPlan:
    """Result of the schedule -> setback -> optimal-start orchestration."""

    base: float  # effective comfort base for this tick (setback applied / cancelled)
    preheating: bool  # optimal-start cancelled the setback to preheat now
    preheat_outdoor: float | None  # outdoor temp used for the lead estimate, if any
    coasting: bool = False  # optimal-stop dropped the base early to coast down


def plan_preheat(
    *,
    comfort_base: float,
    is_comfort: bool,
    setback_offset: float,
    minutes_to_comfort: float,
    optimal_start_enabled: bool,
    can_heat: bool,
    identified: bool,
    model: ThermalModel | None,
    room: float,
    t_out_lead: float,
    heat_lower: float,
    heat_upper: float,
    optimal_stop_enabled: bool = False,
    minutes_to_setback: float = 0.0,
    coast_lower: float | None = None,
    was_preheating: bool = False,
    was_coasting: bool = False,
) -> PreheatPlan:
    """Decide the effective comfort base, applying night setback + optimal start.

    Pure mirror of the coordinator tick: in a comfort window the full base is
    used; in setback the base is lowered by ``setback_offset``; optimal-start
    only runs when enabled AND the device can heat AND the model is identified,
    and only then may it cancel the setback (``preheating``). ``t_out_lead`` is
    the already-resolved outdoor temperature (forecast mean or constant).
    """
    if is_comfort:
        if (
            optimal_stop_enabled
            and can_heat
            and identified
            and model is not None
            and coast_lower is not None
            and minutes_to_setback > 0
        ):
            coast_advice = advise_stop(
                model,
                room=room,
                target=coast_lower,
                t_out=t_out_lead,
                minutes_to_setback=minutes_to_setback,
            )
            # Latch (anti-chatter, ADR-0034): engage on stop_now, then HOLD until
            # the room has coasted down to coast_lower. The coastdown lead shrinks
            # as the room cools, so without the latch the transient flip would put
            # the base back up and re-chatter the heater on/off every tick.
            if coast_advice.stop_now or (was_coasting and room > coast_lower):
                return PreheatPlan(coast_lower, False, round(t_out_lead, 1), True)
        return PreheatPlan(comfort_base, False, None)
    base = comfort_base + setback_offset
    if not (optimal_start_enabled and can_heat and identified and model is not None):
        return PreheatPlan(base, False, None)
    target = min(max(comfort_base, heat_lower), heat_upper)
    advice = advise(
        model,
        room=room,
        target=target,
        t_out=t_out_lead,
        minutes_to_comfort=minutes_to_comfort,
    )
    used_outdoor = round(t_out_lead, 1)
    # Latch (anti-chatter, ADR-0025): engage on start_now, then HOLD until the
    # room reaches target. Warming lowers heatup_minutes, so without the latch the
    # transient lead-drop would drop the base back to setback and re-chatter — the
    # heater flapping on/off across the preheat window.
    if advice.start_now or (was_preheating and room < target):
        return PreheatPlan(comfort_base, True, used_outdoor)
    return PreheatPlan(base, False, used_outdoor)


def _to_dt(value: Any, tz: Any) -> datetime | None:
    """Coerce a forecast 'datetime' (ISO string or datetime) to a tz-aware value.

    Naive timestamps inherit ``tz`` (the timezone of ``base_utc``), so the
    result is always comparable to the reference without a hard UTC literal.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def forecast_samples_from_response(
    resp: Mapping[str, Any] | None,
    weather_entity: str,
    base_utc: datetime,
) -> list[tuple[float, float]]:
    """Parse a weather.get_forecasts response into (minutes_from_now, temp_c).

    Tolerant of missing keys / bad timestamps (skips them) and drops past
    entries. Pure so the forecast plumbing can be unit-tested without HA.
    """
    if not resp:
        return []
    block = resp.get(weather_entity) or {}
    entries = block.get("forecast") or []
    out: list[tuple[float, float]] = []
    for e in entries:
        temp = e.get("temperature")
        when = e.get("datetime")
        if temp is None or when is None:
            continue
        ts = _to_dt(when, base_utc.tzinfo)
        if ts is None:
            continue
        offset = (ts - base_utc).total_seconds() / 60.0
        if offset >= 0.0:
            try:
                out.append((offset, float(temp)))
            except (TypeError, ValueError):
                continue
    return out
