"""Exclusive actuator-path capability matrix (ADR-0015).

Per device exactly one path is chosen, top-down, first match wins:
  1. direct valve  — a writable live-position number entity
  2. calibration   — a writable offset entity + reliable heat mode
  3. PI setpoint   — any climate entity (fallback)

``valve_opening_degree`` is deliberately *excluded* from the valve path: on the
Sonoff TRVZB it is a maximum-opening limit, not the live position — writing the
TPI duty to it caps capacity instead of modulating it (ThermoSmart finding).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ActuatorPath

AUTO_VALVE_PATTERNS = ("valve_position", "pi_heating_demand", "heating_demand", "level")
MAX_LIMIT_PATTERNS = ("valve_opening_degree",)
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
    """(can_heat, can_cool) from a climate entity's hvac_modes (ADR-0023)."""
    modes = {m.lower() for m in hvac_modes}
    can_heat = bool(modes & {"heat", "heat_cool", "auto"})
    can_cool = bool(modes & {"cool", "heat_cool", "auto"})
    return can_heat, can_cool
