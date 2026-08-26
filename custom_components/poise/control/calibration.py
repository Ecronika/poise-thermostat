"""TRV calibration (Better Thermostat method, ADR-0015).

Two paths, chosen by device capability:
  * local     — accumulating offset for TRVs with a calibration register
  * setpoint  — fake a setpoint for TRVs without one

Honesty note: the local-offset path is being wired as the calibration actuate
segment (plan tasks P1.3/P1.4, decision D6) — today the operative-mode path
feeds the true room temperature to the TRV's own external-input ``number``
entity instead (see README "External-temperature input"). ``setpoint_calibration``
stays unwired: faking the setpoint was rejected as a calibration strategy
(decision D2); a real PI-driven setpoint path is reserved to ADR-0037.
``snap_offset`` below now supplies the device-truth grid clamping this note
used to demand; the ``±5 K`` / ``5..30 °C`` defaults on the two original
helpers remain placeholders for callers that have no entity metadata — the
live segment never uses them.
"""

from __future__ import annotations

import math

from ..const import (
    CALIBRATION_DEADBAND_K,
    CALIBRATION_MIN_INTERVAL_S,
    CALIBRATION_UNCONVERGED_LIMIT,
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def local_calibration(
    external: float,
    trv_temp: float,
    current_offset: float,
    *,
    min_offset: float = -5.0,
    max_offset: float = 5.0,
) -> float:
    """Accumulating offset that makes the TRV read the external sensor."""
    new_offset = (external - trv_temp) + current_offset
    return _clamp(new_offset, min_offset, max_offset)


def setpoint_calibration(
    target: float,
    external: float,
    trv_temp: float,
    *,
    min_sp: float = 5.0,
    max_sp: float = 30.0,
) -> float:
    """Calibrated setpoint that makes an offset-less TRV honour ``target``."""
    return _clamp((target - external) + trv_temp, min_sp, max_sp)


def snap_offset(
    value: float, *, step: float, min_value: float, max_value: float
) -> float:
    """Snap onto the entity grid ``min + n*step`` (device truth).

    ``n_max`` is the highest grid rung INSIDE ``[min, max]`` — an off-grid
    ``max`` can therefore never produce an off-grid result. Candidates are
    the two neighbouring grid values; selection chain: (1) nearer to the
    value, (2) on a tie the larger magnitude (away from zero), (3) on a
    further tie the smaller value.

    Requires ``step > 0`` (guaranteed by ``CalibrationMeta`` — P1.1 maps
    step <= 0 to "unreadable")."""
    n_max = math.floor((max_value - min_value) / step + 1e-9)
    top = min_value + n_max * step
    v = _clamp(value, min_value, top)
    n = math.floor((v - min_value) / step)
    candidates = (
        min_value + n * step,
        min_value + min(n + 1, n_max) * step,
    )
    best = min(candidates, key=lambda c: (abs(c - value), -abs(c), c))
    return round(best, 6)


def calibration_write_due(
    *,
    new_offset: float,
    reported_offset: float,
    last_write_ts: float | None,
    now: float,
    deadband: float = CALIBRATION_DEADBAND_K,
    min_interval_s: float = CALIBRATION_MIN_INTERVAL_S,
) -> bool:
    """Write gate: delta at or above the deadband AND the minimum interval passed."""
    if last_write_ts is not None and (now - last_write_ts) < min_interval_s:
        return False
    return abs(new_offset - reported_offset) >= deadband - 1e-9


def calibration_converged(
    *,
    reported_offset: float,
    last_cal_value: float | None,
    step: float,
) -> bool:
    """Does the device show the last commanded offset (+- 1/2 step)?

    THE one convergence formula (P1.4c) — shared by the evidence gate below
    and the divergence input of the calibration segment, so the two can never
    drift apart.  ``last_cal_value is None`` (no command ever dispatched)
    is trivially converged: there is nothing the device could still owe."""
    if last_cal_value is None:
        return True
    return abs(reported_offset - last_cal_value) <= step / 2 + 1e-9


def calibration_accumulation_allowed(
    *,
    reported_offset: float,
    last_cal_value: float | None,
    step: float,
    actuator_updated_after_write: bool,
) -> bool:
    """Evidence gate (D4): accumulate again only once the device shows the
    last command (+- 1/2 step) AND has reported since the write.
    ``last_cal_value is None`` means no command was ever dispatched yet, so
    there is nothing to await convergence on -- always allowed."""
    if last_cal_value is None:
        return True
    return (
        calibration_converged(
            reported_offset=reported_offset,
            last_cal_value=last_cal_value,
            step=step,
        )
        and actuator_updated_after_write
    )


def calibration_diverged(
    *,
    converged: bool,
    last_write_ts: float | None,
    now: float,
    min_interval_s: float = CALIBRATION_MIN_INTERVAL_S,
    limit: int = CALIBRATION_UNCONVERGED_LIMIT,
) -> bool:
    """Divergence as a pure time predicate (no tick counter, D4): the device
    still does not show the last command ``limit`` intervals after the write."""
    if converged or last_write_ts is None:
        return False
    return (now - last_write_ts) >= limit * min_interval_s
