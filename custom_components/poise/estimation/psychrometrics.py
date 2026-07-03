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
_MW_RATIO: float = 0.621945  # molar mass ratio water / dry air (Mw / Md)
_P_ATM: float = 101325.0  # Pa, standard sea-level total pressure


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


def humidity_ratio(t_c: float, rh_percent: float, pressure_pa: float = _P_ATM) -> float:
    """Humidity ratio (mixing ratio) [g water vapour / kg dry air].

    ``w = 1000 · 0.621945 · p_v / (p_atm − p_v)`` with the vapour partial
    pressure ``p_v`` from :func:`vapour_pressure`. This is the unit in which the
    comfort layer checks the EN 16798-1 / ASHRAE-55 absolute-moisture ceiling
    (12 g/kg). ``p_v`` is capped just below total pressure so the ratio stays
    finite at pathological inputs (100 % RH at high temperature).
    """
    p_v = min(vapour_pressure(t_c, rh_percent), pressure_pa - 1.0)
    return 1000.0 * _MW_RATIO * p_v / (pressure_pa - p_v)
