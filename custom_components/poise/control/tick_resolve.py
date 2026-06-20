"""Pure per-tick resolution helpers extracted from the coordinator glue.

These hold the *decision* logic the coordinator used to inline — source
selection for the shadow estimators (T_rm, solar, MRT) and the final
write-target resolution (window / override / comfort → setpoint + mode + norm
clamp). Keeping them pure makes the trickiest tick logic unit-testable without a
Home Assistant runtime (ADR-0005/0011/0031); the coordinator only reads states
and calls these.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..comfort.norm_compliance import clamp_to_norm
from ..estimation.solar import clear_sky_normalized, normalize_irradiance


def select_t_rm(
    sensor: float | None, internal: float | None, t_out: float | None
) -> tuple[float | None, str | None]:
    """Running-mean source: external sensor → internal shadow → outdoor fallback."""
    if sensor is not None:
        return sensor, "sensor"
    if internal is not None:
        return internal, "internal"
    return t_out, ("outdoor" if t_out is not None else None)


def select_q_solar(
    elevation: float | None, ghi: float | None
) -> tuple[float, str, float]:
    """Solar input: measured irradiance overrides the always-on clear-sky shadow.

    Returns ``(q_solar_used, source, q_solar_internal)``.
    """
    internal = clear_sky_normalized(elevation) if elevation is not None else 0.0
    if ghi is not None:
        return normalize_irradiance(ghi), "sensor", internal
    if elevation is not None:
        return internal, "internal", internal
    return 0.0, "none", internal


def select_mrt(sensor: float | None, internal: float) -> tuple[float, str]:
    """MRT source: a measured globe/MRT sensor overrides the virtual estimate."""
    if sensor is not None:
        return sensor, "sensor"
    return internal, "internal"


@dataclass(frozen=True, slots=True)
class WriteTarget:
    target: float
    mode: str
    norm_binding: str | None


def resolve_write_target(
    *,
    window_open: bool,
    override: float | None,
    heat_sp: float,
    cool_sp: float,
    write_setpoint: float,
    comfort_mode: str,
    frost_floor: float,
    mold_min: float | None,
    device_max: float,
) -> WriteTarget:
    """Final write target: window/override/comfort → setpoint + mode, then the
    unconditional norm envelope (ASR cap + frost/mould floor, skipped when
    cooling) and the device max (ADR-0023/0027).
    """
    floor = max(frost_floor, mold_min if mold_min is not None else frost_floor)
    if window_open:
        target, mode = round(floor, 1), "off"
    elif override is not None:
        target, mode = round(min(max(override, heat_sp), cool_sp), 1), "manual"
    else:
        target, mode = round(write_setpoint, 1), comfort_mode

    if mode == "cool":
        norm_binding: str | None = None
    else:
        nc = clamp_to_norm(target, floor=floor)
        target, norm_binding = nc.value, nc.binding

    return WriteTarget(min(target, device_max), mode, norm_binding)
