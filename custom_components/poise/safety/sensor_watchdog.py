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
