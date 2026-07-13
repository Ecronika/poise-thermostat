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
    if can_heat and can_cool:
        modes.append("auto")  # both directions -> offer auto (return-to-automatic)
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
    if climate_mode == "cool_only" and can_cool:
        return "cool"
    if climate_mode == "heat_only" and can_heat:
        return "heat"
    if can_heat and can_cool:
        return "auto"  # dual-capable device in auto mode
    # capability mismatch / single-direction: show the available direction
    if can_heat:
        return "heat"
    if can_cool:
        return "cool"
    return "off"


# The actuator's own hvac_action values we treat as ground truth (a real,
# usable "what the device is doing now" signal). "off"/"unknown"/None are NOT
# here on purpose: many ACs report no action at all, so those fall back to
# Poise's own intent. (HA HVACAction string values; PREHEATING/DEFROSTING exist
# since core 2024.2 and are only ever *passed through* from the device.)
_DEVICE_ACTIONS = frozenset(
    {"heating", "cooling", "drying", "fan", "idle", "preheating", "defrosting"}
)


def resolve_hvac_action(
    *,
    enabled: bool,
    final_mode: str,
    actuator_action: str | None,
    idle_park_mode: str | None = None,
) -> str:
    """The climate entity's ``hvac_action`` — what the zone is *doing now*.

    V2 semantics (ADR display contract): the actuator's own reported action is
    the ground truth when present, so a manual cooling override reads "cooling",
    a saturated TRV valve reads "idle", and a compressor still held by the guard
    reads "idle" until it actually runs. When the device reports no usable action
    (many ACs), fall back to Poise's arbitrated intent (``final_mode``) so the
    direction is still truthful — never the raw "manual" override tag.

    Returns a canonical HA ``HVACAction`` string value; the caller maps it to the
    enum (guarding members that may not exist on older cores).
    """
    if not enabled:
        return "off"
    act = actuator_action.lower() if isinstance(actuator_action, str) else None
    if act in _DEVICE_ACTIONS:
        return act
    # Intent fallback from the arbitrated direction (heat/cool/dry/idle/off).
    if final_mode == "heat":
        return "heating"
    if final_mode == "cool":
        return "cooling"
    if final_mode == "dry":
        return "drying"
    if final_mode == "idle" and idle_park_mode == "fan_only":
        return "fan"  # occupied-deadband recirculation is a running fan, not idle
    return "idle"


def climate_mode_for_hvac(hvac_mode: str) -> str:
    """Map a selected HVAC mode to the coordinator's climate_mode string.

    Must use ``decide_mode``'s vocabulary (auto / heat_only / cool_only); a bare
    "heat"/"cool" is *not* recognised there and would collapse to idle.
    """
    return {"heat": "heat_only", "cool": "cool_only"}.get(hvac_mode, "auto")
