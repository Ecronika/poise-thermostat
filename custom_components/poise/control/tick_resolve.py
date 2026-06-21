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

from ..comfort.norm_compliance import ASR_MAX_ROOM_C
from ..constraints import Constraint, ConstraintKind, resolve_constraints
from ..contracts import Precedence
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
    binding_precedence: str | None = None


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

    # Unified hard envelope (ADR-0035): device max + (unless cooling) the ASR
    # cap and frost/mould floor, composed with precedence. The device max is a
    # physical SAFETY cap, the norm floor HEALTH, the norm cap COMFORT.
    caps = [Constraint(device_max, "device_max", ConstraintKind.CAP, Precedence.SAFETY)]
    floors: list[Constraint] = []
    if mode != "cool":
        caps.append(
            Constraint(
                ASR_MAX_ROOM_C, "norm_cap", ConstraintKind.CAP, Precedence.COMFORT
            )
        )
        floors.append(
            Constraint(floor, "norm_floor", ConstraintKind.FLOOR, Precedence.HEALTH)
        )
    res = resolve_constraints(target, floors + caps)
    norm_binding = (
        res.binding.cause
        if (res.binding and res.binding.cause in ("norm_floor", "norm_cap"))
        else None
    )
    precedence = res.binding.precedence.name.lower() if res.binding else None
    return WriteTarget(round(res.value, 1), mode, norm_binding, precedence)


def should_write(
    actual: float | None,
    target: float,
    *,
    mode_changed: bool,
    deadband: float,
) -> bool:
    """Whether the actuator setpoint must be (re)written this tick (ADR-0012).

    ``actual`` is the actuator's *current* reported setpoint. Writes when it is
    unknown, on a mode change, or when it differs from ``target`` by at least
    ``deadband`` K. Comparing against the device's real setpoint (not our last
    command) means we re-assert after an external change while still skipping
    redundant writes — sparing battery/Zigbee TRVs from per-tick traffic.
    """
    if actual is None or mode_changed:
        return True
    # setpoints are 0.1-resolution; round the delta to avoid float artefacts
    return round(abs(target - actual), 3) >= deadband
