"""Shared surface psychrometry for the mould/humidity axis (ADR-0071).

Mould risk is governed by the humidity at the *coldest surface*, not by the
room air. The surface-temperature factor ``f_Rsi = (θ_si - θ_e)/(θ_i - θ_e)``
links surface to air; this module owns that link and nothing else.

WHAT LEFT THIS MODULE: ADR-0062's judgement — surface RH over 80 % as an
INSTANTANEOUS criterion, inverted in one line into an air-temperature floor —
is gone (``mold_min_air_temperature``/``_detail``, ``SURFACE_RH_LIMIT``,
``_MOLD_MAX_C``). ADR-0071 replaced it with the VTT dose model in
:mod:`comfort.mould_risk`, which integrates how LONG a surface stayed above a
temperature- and substrate-dependent critical humidity. 80 % is the lower
bound of *possible* growth, not a growth event, so a single reading can never
carry that decision.

WHAT STAYED, and why: :func:`surface_temperature`,
:func:`surface_relative_humidity` and :func:`max_safe_rh` are plain
psychrometry, shared with the ADR-0066 ventilation/humidity axis and used BY
``comfort.mould_risk`` itself. They must not fork, so they keep living here —
one layer below the risk model, with no knowledge of it (``mould_risk``
imports this module, never the other way round).
"""

from __future__ import annotations

from ..estimation.psychrometrics import saturation_pressure, vapour_pressure

# DIN 4108-2 minimum surface-temperature factor; 0.7 is deliberately the
# conservative existing-building value (ADR-0062 — the safe assumption when
# the construction is unknown; the factor survived the ADR-0071 change of
# method, only the growth criterion on top of it did not).
DEFAULT_F_RSI: float = 0.7
_F_RSI_FLOOR: float = 0.1  # f_Rsi in (0,1]; guard div-by-zero / unphysical input
# Fallback growth limit for :func:`max_safe_rh` when the caller has no live
# critical humidity to hand. NOT the old ADR-0062 criterion re-imported: it is
# the SENSITIVE class's ``rh_min`` floor from Ojanen et al. (the lowest value
# ``mould_risk.critical_rh`` can ever return for the default substrate), so a
# defaulted call is conservative rather than arbitrary. Written as a literal
# because ``mould_risk`` imports THIS module — importing it back would close
# the cycle. Live callers pass ``MouldRisk.critical_rh / 100`` (ADR-0071 §4).
_FALLBACK_RH_LIMIT: float = 0.80


def surface_temperature(
    t_air: float, t_out: float, f_rsi: float = DEFAULT_F_RSI
) -> float:
    """Coldest interior surface temperature [°C]."""
    return t_out + f_rsi * (t_air - t_out)


def surface_relative_humidity(
    t_air: float, rh_percent: float, t_out: float, f_rsi: float = DEFAULT_F_RSI
) -> float:
    """Relative humidity at the coldest surface (0..1+)."""
    p_v = vapour_pressure(t_air, rh_percent)
    t_si = surface_temperature(t_air, t_out, f_rsi)
    return p_v / saturation_pressure(t_si)


def max_safe_rh(
    t_air: float,
    t_out: float,
    f_rsi: float = DEFAULT_F_RSI,
    limit: float = _FALLBACK_RH_LIMIT,
) -> float:
    """Mould-safe ROOM-RH ceiling [%] at the current air/outdoor temperatures.

    The surface-humidity criterion solved for relative humidity instead of
    temperature (ADR-0066 feature C):
    ``rh_max = 100 * limit * p_sat(t_si) / p_sat(t_air)``. This is the target a
    foreign humidifier (``generic_hygrostat``) lacks — published monitor-only,
    never actuated (ADR-0048 §3 / ``tests/test_non_goals.py``). Clamped to
    [0, 100]; the exact inverse of :func:`surface_relative_humidity` at
    ``limit`` (round-trip reference test).

    ``limit`` is the surface RH the ceiling is solved for, as a FRACTION. Since
    ADR-0071 the live caller (``diagnostics/shadows.py``) passes the tick's
    ``MouldRisk.critical_rh / 100`` — the substrate- and temperature-dependent
    growth line — instead of a fixed number; ``_FALLBACK_RH_LIMIT`` only covers
    calls made without one.
    """
    f = min(max(f_rsi, _F_RSI_FLOOR), 1.0)
    lim = min(max(limit, 0.01), 1.0)
    t_si = surface_temperature(t_air, t_out, f)
    rh = 100.0 * lim * saturation_pressure(t_si) / saturation_pressure(t_air)
    return min(max(rh, 0.0), 100.0)
