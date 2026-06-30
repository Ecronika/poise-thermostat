"""Model-based expected heating minutes for outcome scoring (ADR-0044 §2).

The speed component of the outcome score (35 % weight) compares the actual
heat-up time against an *expected* duration. ADR-0044 §2 requires that
expectation to be model-based — the physics ``heatup_minutes`` from the learned
EKF — not a schedule clock (which is 0 inside the comfort window and would pin
the speed score to its neutral floor). This thin helper returns the physics
estimate when the model is identified and a caller-supplied fallback otherwise,
so the score degrades safely instead of silently using a non-physical value.
Pure; unit-tested.
"""

from __future__ import annotations

from ..estimation.thermal_ekf import ThermalModel
from .optimal_start import heatup_minutes


def model_expected_minutes(
    model: ThermalModel | None,
    *,
    room: float,
    target: float,
    t_out: float,
    q_solar: float = 0.0,
    fallback: float = 0.0,
) -> float:
    """Physics heat-up minutes from an identified model, else ``fallback``.

    Pass ``None`` for an unidentified EKF. Falls back when the model is absent,
    the target is unreachable in the horizon, or the room is already at/above
    target — so the speed score is never driven by a zero or by a schedule
    countdown instead of a real, difficulty-adjustable expectation.
    """
    if model is not None:
        minutes: float | None = heatup_minutes(
            model, room=room, target=target, t_out=t_out, q_solar=q_solar
        )
        if minutes is not None and minutes > 0.0:
            return minutes
    return fallback
