"""Advisory residual-heat estimate for Optimal Stop / coasting (ADR-0003).

Pure function: returns the fraction (0..1) of the learned heating rate still
delivered by the thermal mass after the heater stops. The MPC consumes it as a
disturbance term in its prediction (HVAC-off gated); it never commands the
actuator itself, which avoids the re-entry bug class (K5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..estimation.thermal_ekf import ThermalModel

_MIN_ALPHA = 1e-4  # guard against div-by-zero on a degenerate model
_T_EQ_MARGIN = 0.1  # equilibrium must clear the target by this margin [K]


def residual_fraction(
    elapsed_h: float,
    heating_duration_h: float,
    *,
    tau_h: float = 1.0,
    tau_charge_h: float = 0.5,
) -> float:
    """Charge/discharge double-exponential residual heat fraction in [0, 1]."""
    if elapsed_h < 0.0 or heating_duration_h <= 0.0:
        return 0.0
    charge = 1.0 - math.exp(-heating_duration_h / tau_charge_h)
    discharge = math.exp(-elapsed_h / tau_h)
    return min(1.0, max(0.0, charge * discharge))


@dataclass(frozen=True, slots=True)
class CoastAdvice:
    """Optimal-stop verdict for one tick."""

    reachable: bool  # the room can drift down to ``target`` by passive cooling
    lead_minutes: float  # minutes of no-heating to reach ``target``
    stop_now: bool  # the window-end deadline is within the lead -> coast now


def coastdown_minutes(
    model: ThermalModel,
    *,
    room: float,
    target: float,
    t_out: float,
    q_solar: float = 0.0,
    max_lead_h: float = 4.0,
) -> float | None:
    """Minutes of *no heating* for the room to drift down to ``target``.

    Closed-form mirror of :func:`optimal_start.heatup_minutes`: with the heater
    off the room decays toward ``t_eq = t_out + beta_s*q_solar/alpha`` with time
    constant ``1/alpha``. Returns ``None`` when passive cooling cannot reach the
    target (equilibrium too warm) or the coast exceeds the horizon.
    """
    if room <= target:
        return 0.0
    alpha = max(model.alpha, _MIN_ALPHA)
    t_eq = t_out + (model.beta_s * q_solar) / alpha
    if t_eq >= target - _T_EQ_MARGIN:
        return None  # the room never cools to the target without heating off-help
    ratio = (target - t_eq) / (room - t_eq)  # in (0, 1) since t_eq < target < room
    t_h = -math.log(ratio) / alpha
    if t_h > max_lead_h:
        return None
    return t_h * 60.0


def advise_stop(
    model: ThermalModel,
    *,
    room: float,
    target: float,
    t_out: float,
    minutes_to_setback: float,
    q_solar: float = 0.0,
    max_lead_h: float = 4.0,
) -> CoastAdvice:
    """Advise whether to stop heating now so the room coasts to ``target``
    by the comfort window's end. Conservative: if the room cannot coast to the
    target (``None``), keep heating (``stop_now=False``)."""
    lead = coastdown_minutes(
        model,
        room=room,
        target=target,
        t_out=t_out,
        q_solar=q_solar,
        max_lead_h=max_lead_h,
    )
    if lead is None:
        return CoastAdvice(False, 0.0, False)
    return CoastAdvice(True, lead, minutes_to_setback <= lead)
