"""TRV calibration (Better Thermostat method, ADR-0015).

Two paths, chosen by device capability:
  * local     — accumulating offset for TRVs with a calibration register
  * setpoint  — fake a setpoint for TRVs without one

Honesty note (R6): these helpers are **not yet wired into the coordinator** —
today the operative-mode path feeds the true room temperature to the TRV's own
external-input ``number`` entity instead (see README "External-temperature
input"). Without such an input Poise does **no** live TRV compensation; this
module is the generic fallback for register-only devices and stays here so the
wiring is a small, tested step rather than a rewrite. When wired, the ``±5 K`` /
``5..30 °C`` clamp defaults below must be replaced by the device's own reported
offset-register and setpoint min/max (they are conservative placeholders, not
device truth).
"""

from __future__ import annotations


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
