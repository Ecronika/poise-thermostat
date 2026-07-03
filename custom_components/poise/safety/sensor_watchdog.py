"""Frozen-sensor watchdog (ADR-0012).

A sensor that stays *available* but stops changing its value (dead battery,
stuck firmware, stalled integration) is a silent failure: control runs on stale
data and the EKF would mislearn from a flat signal. We detect it from the age
of the last value change and react *advisorily* — raise a repair issue and pause
learning — without altering the control output (no new control risk).
"""

from __future__ import annotations

from datetime import datetime


def is_frozen(age_s: float | None, threshold_s: float) -> bool:
    """True if the last value change is at least ``threshold_s`` seconds ago.

    ``age_s`` is the seconds since the sensor value last changed (``None`` when
    unknown, e.g. just started — treated as not frozen).
    """
    if age_s is None or threshold_s <= 0.0:
        return False
    return age_s >= threshold_s


def unavailable_safe_engaged(unavailable_s: float | None, threshold_s: float) -> bool:
    """True once the room sensor has been *unavailable* for at least ``threshold_s``.

    A brief drop-out is tolerated (hold the last state); a sustained loss must
    degrade to the same safe state as a frozen sensor — command the frost/mould
    floor so a heat-capable actuator protects the room with its own sensor
    (fail toward warmth). This matters most in external-feed mode, where the lost
    sensor is the room's only signal (review #7). ``None`` (not currently
    unavailable) and a non-positive threshold read as not engaged.
    """
    if unavailable_s is None or threshold_s <= 0.0:
        return False
    return unavailable_s >= threshold_s


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


def sensor_age_seconds(now: datetime, last_changed: datetime) -> float:
    """Seconds since the sensor value last changed (F1 feed for ``is_frozen``).

    Pure timestamp arithmetic extracted from the coordinator glue so the
    last-changed-based ageing is unit-testable without a HA runtime (review M13).
    """
    return (now - last_changed).total_seconds()


def frozen_safe_target(frost_floor: float, mold_min: float | None) -> float:
    """Setpoint to command when the room sensor can no longer be trusted (C3/Ü3).

    On a frozen/stale read we must not chase a comfort target computed from a
    dead value (it could overheat, or miscompute the frost floor). Instead we
    degrade to the *health floor* — the higher of frost protection and the
    mould-avoidance minimum — and let the actuator hold it with its own sensor.
    This "fails toward warmth": frost/mould protection is guaranteed without
    trusting our reading. Pure, unit-tested.
    """
    return max(frost_floor, mold_min if mold_min is not None else frost_floor)


def should_learn(*, window_open: bool, frozen: bool) -> bool:
    """Learn only when the room signal is trustworthy.

    An open window (air mixing) or a frozen sensor (stale value) must pause EKF
    learning so the model is not poisoned (F1/ADR-0012). Extracted from the
    coordinator tick so the gate itself is tested (review M13).
    """
    return not window_open and not frozen
