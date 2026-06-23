"""Mould-protection minimum temperature (DIN 4108-2, EN ISO 13788).

Mould risk is governed by the relative humidity at the *coldest surface*, not
the room air. The surface temperature factor ``f_Rsi = (θ_si - θ_e)/(θ_i - θ_e)``
links surface to air; the growth criterion is surface RH <= 80 %. We invert it
to the minimum air temperature that keeps the surface below the limit
(charter G4, ADR-0010).
"""

from __future__ import annotations

from ..estimation.psychrometrics import (
    saturation_pressure,
    temperature_at_saturation,
    vapour_pressure,
)

DEFAULT_F_RSI: float = 0.7  # DIN 4108-2 minimum for existing construction
SURFACE_RH_LIMIT: float = 0.80  # mould growth criterion (EN ISO 13788)
_F_RSI_FLOOR: float = 0.1  # f_Rsi in (0,1]; guard div-by-zero / unphysical input
_MOLD_MAX_C: float = 24.0  # sane ceiling: caps the singularity blow-up (review F4)


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


def mold_min_air_temperature(
    t_out: float,
    rh_percent: float,
    t_air_ref: float,
    f_rsi: float = DEFAULT_F_RSI,
    limit: float = SURFACE_RH_LIMIT,
) -> float:
    """Minimum room air temperature keeping the coldest surface <= ``limit`` RH.

    ``t_air_ref`` (current room air temperature) is used to estimate the room's
    absolute humidity from ``rh_percent``.
    """
    f = min(max(f_rsi, _F_RSI_FLOOR), 1.0)
    lim = min(max(limit, 0.01), 1.0)
    p_v = vapour_pressure(t_air_ref, rh_percent)
    t_si_min = temperature_at_saturation(p_v / lim)
    return min(t_out + (t_si_min - t_out) / f, _MOLD_MAX_C)
