"""Capability-aware HVAC-mode mapping for the climate entity (ADR-0023, review P2).

Pure, HA-free string mapping so the entity surfaces exactly the modes the device
supports. We deliberately expose only HEAT/COOL/OFF (no HEAT_COOL) to avoid the
dual-range-setpoint UI — internal "auto" dual-setpoint still works via config.
A heat-only TRV keeps exactly ("heat", "off"), so its behaviour is unchanged.
"""

from __future__ import annotations


def available_hvac_modes(can_heat: bool, can_cool: bool) -> tuple[str, ...]:
    """The HVAC modes to advertise for a device with these capabilities."""
    modes: list[str] = []
    if can_heat:
        modes.append("heat")
    if can_cool:
        modes.append("cool")
    modes.append("off")
    return tuple(modes)


def current_hvac_mode(
    enabled: bool, climate_mode: str, can_heat: bool, can_cool: bool
) -> str:
    """The mode to report now — always a member of ``available_hvac_modes``."""
    if not enabled:
        return "off"
    if climate_mode == "cool" and can_cool:
        return "cool"
    if can_heat:
        return "heat"
    if can_cool:
        return "cool"
    return "off"


def climate_mode_for_hvac(hvac_mode: str) -> str:
    """Map a selected HVAC mode to the coordinator's climate_mode string."""
    return {"heat": "heat", "cool": "cool"}.get(hvac_mode, "auto")
