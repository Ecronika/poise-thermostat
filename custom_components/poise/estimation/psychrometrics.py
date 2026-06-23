"""Psychrometric helpers (Magnus / Alduchov-Eskridge, over water).

Used by the comfort layer for dewpoint and surface-humidity (mould) checks
(ADR-0010 mould/psychrometrics). Every formula carries a reference test.
"""

from __future__ import annotations

import math

# Alduchov & Eskridge (1996) coefficients, saturation over water.
_A: float = 17.625
_B: float = 243.04  # °C
_P0: float = 610.94  # Pa, saturation vapour pressure at 0 °C
_RH_FLOOR: float = 1.0  # %, clamp before log: 0 % RH -> log(0); no sensor reads true 0
_P_SAT_FLOOR: float = 1e-6  # Pa, guard temperature_at_saturation against log(0)


def saturation_pressure(t_c: float) -> float:
    """Saturation vapour pressure over water [Pa]."""
    return _P0 * math.exp(_A * t_c / (_B + t_c))


def vapour_pressure(t_c: float, rh_percent: float) -> float:
    """Actual water-vapour partial pressure [Pa] at temperature/RH."""
    rh = min(max(rh_percent, _RH_FLOOR), 100.0)
    return (rh / 100.0) * saturation_pressure(t_c)


def temperature_at_saturation(p_sat: float) -> float:
    """Inverse of :func:`saturation_pressure` — the temperature [°C] at which
    ``p_sat`` is the saturation pressure (i.e. the dewpoint of that pressure).
    """
    gamma = math.log(max(p_sat, _P_SAT_FLOOR) / _P0)
    return _B * gamma / (_A - gamma)


def dewpoint(t_c: float, rh_percent: float) -> float:
    """Dewpoint temperature [°C] from air temperature and relative humidity."""
    rh = min(max(rh_percent, _RH_FLOOR), 100.0)
    gamma = math.log(rh / 100.0) + _A * t_c / (_B + t_c)
    return _B * gamma / (_A - gamma)
