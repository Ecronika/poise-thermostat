"""Operative temperature and the operative->air transform (EN ISO 7726, ADR-0017).

Operative temperature ``T_op = a·T_air + (1-a)·T_mrt`` where the air weight
``a`` rises with air velocity. The comfort layer reasons in operative
temperature; the control loop reasons in air temperature. The transform here
is the single place that converts between them (ADR-0017, resolves K4).

ADR-0017 N1 (v0.196.0): the live transform takes a :class:`RadiantModel` — the
MRT as an affine function of the air temperature — and solves the operative
target against the AIR SETPOINT, not against the current room reading. The
former ``operative_to_air(t_op, mrt(room))`` fed the room reading back into
the setpoint with gain ~0.92 (virtual MRT): after a setback the TRV target
jumped by several kelvin and sensor noise passed straight through.
"""

from __future__ import annotations

from dataclasses import dataclass

# ADR-0017 §4: plausible range of a MEASURED (MRT - air) offset [K]. A globe
# outlier beyond this is clamped, never extrapolated into the setpoint.
OFFSET_CLAMP_K: float = 3.0


def air_weight(velocity: float) -> float:
    """Air-temperature weight ``a`` in operative temperature (EN ISO 7726):
    0.5 for v < 0.2 m/s, 0.6 for 0.2 <= v < 0.6, 0.7 above."""
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


@dataclass(frozen=True, slots=True)
class RadiantModel:
    """Mean radiant temperature as an affine function of the air temperature,
    ``t_mrt = slope · t_air + intercept`` (ADR-0017 N1).

    * virtual MRT (``virtual_mrt_model``): ``slope = 1 - k``, ``intercept =
      k·t_out + solar`` — the envelope pull, independent of the room reading;
    * measured MRT (``measured_offset_model``): ``slope = 1``, ``intercept =``
      the clamped measured offset (MRT - air), i.e. ADR-0017's offset form.
    """

    slope: float
    intercept: float


def operative_to_air_model(
    t_op_target: float, model: RadiantModel, velocity: float = 0.1
) -> float:
    """Air setpoint at which the operative temperature equals the target when
    the MRT follows ``model`` — the closed-form solution of
    ``t_op = a·L + (1-a)·(slope·L + intercept)`` for ``L``. It contains no
    room reading, so the setpoint neither kicks after a setback nor carries
    sensor noise (ADR-0017 N1)."""
    a = air_weight(velocity)
    return (t_op_target - (1.0 - a) * model.intercept) / (a + (1.0 - a) * model.slope)


def measured_offset_model(
    t_mrt: float, t_air: float, clamp_k: float = OFFSET_CLAMP_K
) -> RadiantModel:
    """ADR-0017 offset form for a MEASURED MRT: ``offset = MRT - air``,
    clamped to ``±clamp_k`` (§4), carried as a constant over the setpoint."""
    offset = min(clamp_k, max(-clamp_k, t_mrt - t_air))
    return RadiantModel(slope=1.0, intercept=offset)
