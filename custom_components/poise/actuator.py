"""Actuator choke-point — the single writer per device (ADR-0013).

Every ``ActuatorCommand`` produced by arbitration is written here and nowhere
else. Phase 0 implements only the setpoint path; the capability-matrix paths
(tpi_valve / calibration / pi_setpoint) land in Phase 3 (ADR-0015).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .contracts import ActuatorCommand, ActuatorPath

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def service_call_for(command: ActuatorCommand) -> tuple[str, str, dict[str, Any]]:
    """The (domain, service, data) for one command — pure, HA-free, testable.

    Phase 0 implements only the setpoint path; other capability-matrix paths
    (tpi_valve / calibration / pi_setpoint) are not wired yet (ADR-0015).
    """
    if command.path is ActuatorPath.SETPOINT:
        data: dict[str, Any] = {
            "entity_id": command.actuator_id,
            "temperature": command.value,
        }
        # ADR-0046 §8 / P2-3: switch mode and setpoint *atomically*. When the
        # command carries a conditioning mode, ride it along in the single
        # ``set_temperature`` call (HA core switches the mode first, then applies
        # the setpoint) so a reversible device never holds the new regime's
        # setpoint in the old mode -- the divergence window the separate
        # ``set_hvac_mode`` nudge could leave open. Non-conditioning modes
        # (off/idle/fan_only) carry no setpoint semantics and are left to the
        # dedicated mode path.
        if command.hvac_mode in ("heat", "cool", "dry", "heat_cool"):
            data["hvac_mode"] = command.hvac_mode
        return ("climate", "set_temperature", data)
    if command.path is ActuatorPath.TPI_VALVE:
        # direct valve: actuator_id is the writable valve-opening number entity,
        # value is the open percentage 0..100 (ADR-0036). Never valve_closing_*.
        return (
            "number",
            "set_value",
            {"entity_id": command.actuator_id, "value": command.value},
        )
    raise NotImplementedError(f"actuator path not wired: {command.path}")


async def write(hass: HomeAssistant, command: ActuatorCommand) -> None:
    """Translate one arbitrated command into exactly one HA service call."""
    domain, service, data = service_call_for(command)
    await hass.services.async_call(domain, service, data, blocking=False)
