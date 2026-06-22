"""Exclusive actuator-path capability matrix (ADR-0015).

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
    "level",
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
