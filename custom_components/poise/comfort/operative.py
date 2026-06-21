"""Operative temperature and the operative->air transform (EN ISO 7726, ADR-0017).

Operative temperature ``T_op = a·T_air + (1-a)·T_mrt`` where the air weight
``a`` rises with air velocity. The comfort layer reasons in operative
temperature; the control loop reasons in air temperature. The transform here
is the single place that converts between them (ADR-0017, resolves K4).
"""

from __future__ import annotations


def air_weight(velocity: float) -> float:
    """Air-temperature weight ``a`` in operative temperature (EN ISO 7726)."""
    if velocity < 0.2:
        return 0.5
    if velocity < 0.6:
        return 0.6
    return 0.7


def operative_temperature(t_air: float, t_mrt: float, velocity: float = 0.1) -> float:
    """Operative temperature from air and mean-radiant temperature [°C]."""
    a = air_weight(velocity)
    return a * t_air + (1.0 - a) * t_mrt


def operative_to_air(
    t_op_target: float, t_mrt: float | None, velocity: float = 0.1
) -> float:
    """Air setpoint that yields the operative target given the current MRT.

    With no MRT available the transform degrades to identity (operative == air,
    offset 0) — the bottom rung of the degradation ladder (ADR-0017/G14).
    """
    if t_mrt is None:
        return t_op_target
    a = air_weight(velocity)
    return (t_op_target - (1.0 - a) * t_mrt) / a
