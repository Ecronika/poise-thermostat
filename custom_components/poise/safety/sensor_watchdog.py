"""Frozen-sensor watchdog (ADR-0012).

A sensor that stays *available* but stops changing its value (dead battery,
stuck firmware, stalled integration) is a silent failure: control runs on stale
data and the EKF would mislearn from a flat signal. We detect it from the age
of the last value change and react *advisorily* — raise a repair issue and pause
learning — without altering the control output (no new control risk).
"""

from __future__ import annotations


def is_frozen(age_s: float | None, threshold_s: float) -> bool:
    """True if the last value change is at least ``threshold_s`` seconds ago.

    ``age_s`` is the seconds since the sensor value last changed (``None`` when
    unknown, e.g. just started — treated as not frozen).
    """
    if age_s is None or threshold_s <= 0.0:
        return False
    return age_s >= threshold_s


def sensor_at_heat_source(
    tau_hours: float, identified: bool, *, min_plausible_tau_h: float
) -> bool:
    """True if an *identified* model has an implausibly short time constant.

    A temperature sensor mounted on or near the radiator (e.g. a TRV's internal
    sensor) reacts almost immediately to heating, so the learned 1R1C model gets
    an implausibly small time constant ``tau = 1/alpha`` — a real room is hours,
    a heat-source sensor is minutes. Gated on ``identified`` so we only judge a
    trusted estimate (charter G17, anti-"garbage in").
    """
    return identified and tau_hours < min_plausible_tau_h


def valve_stuck(closing_steps: float | None, *, min_steps: float = 10.0) -> bool:
    """True if a motorised valve looks jammed / un-calibrated (advisory).

    A healthy calibrated TRV reports a substantial closing-step count (e.g. the
    Sonoff TRVZB ~300); a value near zero means calibration failed or the valve
    is mechanically stuck. ``None`` (no telemetry) is treated as not stuck.
    """
    if closing_steps is None:
        return False
    return closing_steps < min_steps
