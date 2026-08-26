"""Exclusive actuator-path capability matrix (ADR-0015; the
``valve_opening_degree`` exclusion in its §1 is reversed by ADR-0036).

Per device exactly one path is chosen, top-down, first match wins:
  1. direct valve  — a writable live-position number entity
  2. calibration   — a writable offset entity + reliable heat mode
  3. PI setpoint   — any climate entity (fallback)

``valve_opening_degree`` (Sonoff TRVZB, FW v1.1.4+) is a *writable* open-position
control and is used as the TPI duty target (force the TRV open via a high setpoint,
then modulate the opening). ``valve_closing_degree`` is excluded — writing it
triggers a TRVZB firmware bug that breaks ``running_state``/``hvac_action``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ActuatorPath

AUTO_VALVE_PATTERNS = (
    "valve_position",
    "pi_heating_demand",
    "heating_demand",
    "valve_opening_degree",  # Sonoff TRVZB: writable open-position (FW v1.1.4+)
)
# valve_closing_degree must never be written (TRVZB firmware bug breaks running_state)
MAX_LIMIT_PATTERNS = ("valve_closing_degree",)
CALIBRATION_PATTERNS = (
    "local_temperature_calibration",
    "temperature_offset",
    "temperature_calibration",
)


def classify_number_entity(key: str) -> str | None:
    """Classify a writable ``number`` entity key: valve / max_limit / calibration."""
    k = key.lower()
    if any(p in k for p in MAX_LIMIT_PATTERNS):  # checked first — excluded from valve
        return "max_limit"
    if any(p in k for p in AUTO_VALVE_PATTERNS):
        return "valve"
    if any(p in k for p in CALIBRATION_PATTERNS):
        return "calibration"
    return None


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    writable_valve: bool = False
    writable_calibration: bool = False
    reliable_heat_mode: bool = True


def capabilities_from_numbers(
    number_keys: list[str], *, reliable_heat_mode: bool = True
) -> DeviceCapabilities:
    kinds = {classify_number_entity(k) for k in number_keys}
    return DeviceCapabilities(
        writable_valve="valve" in kinds,
        writable_calibration="calibration" in kinds,
        reliable_heat_mode=reliable_heat_mode,
    )


def select_path(caps: DeviceCapabilities) -> ActuatorPath:
    """Choose exactly one actuation path (first match wins)."""
    if caps.writable_valve:
        return ActuatorPath.TPI_VALVE
    if caps.writable_calibration and caps.reliable_heat_mode:
        return ActuatorPath.CALIBRATION
    return ActuatorPath.PI_SETPOINT


def reliable_heat_mode_from(hvac_modes: list[str]) -> bool:
    """ADR-0015 path 2, literally: calibration requires a device that can be
    HELD in ``heat``. ``can_heat`` is not enough — ``auto`` counts as
    heat-capable there, but the mode nudge only writes literally supported
    modes (supported = desired in act_modes)."""
    return "heat" in {m.lower() for m in hvac_modes}


def select_live_path(
    caps: DeviceCapabilities,
    *,
    ext_temp_reserved: bool,
    calibration_enabled: bool,
    valve_live: bool = False,
) -> ActuatorPath:
    """The ONE live path choice (D6). ``select_path`` stays the pure
    ADR-0015 classification (diagnostics); this adds the runtime gates: a
    structurally present external-temperature input (ADR-0029) displaces any
    calibration — even while it is briefly unavailable, so the compensations
    never flip-flop; the valve path is never live until the ADR-0036 release
    (``valve_live`` is only set by P3); calibration needs the opt-in AND
    ``reliable_heat_mode``. Everything else is the plain setpoint path."""
    if ext_temp_reserved:
        return ActuatorPath.SETPOINT
    if valve_live and caps.writable_valve:
        return ActuatorPath.TPI_VALVE
    if calibration_enabled and caps.writable_calibration and caps.reliable_heat_mode:
        return ActuatorPath.CALIBRATION
    return ActuatorPath.SETPOINT


def climate_capability(hvac_modes: list[str]) -> tuple[bool, bool]:
    """(can_heat, can_cool) from a climate entity's hvac_modes (ADR-0023).

    ``cool`` capability requires an *explicit* ``cool``/``heat_cool`` mode: many
    radiator TRVs expose an ``auto`` (internal-schedule) mode but cannot cool, so
    inferring cooling from ``auto`` would falsely enable a cool setpoint on a
    heat-only valve (Sonoff TRVZB finding). ``auto`` still implies heating, which
    is safe for a heating-first integration.
    """
    modes = {m.lower() for m in hvac_modes}
    can_heat = bool(modes & {"heat", "heat_cool", "auto"})
    can_cool = bool(modes & {"cool", "heat_cool"})
    return can_heat, can_cool
