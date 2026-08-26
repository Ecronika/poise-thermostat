"""Actuator choke-point — the single writer per device (ADR-0013).

Every ``ActuatorCommand`` produced by arbitration is written here and nowhere
else. The setpoint, direct-valve (tpi_valve) and calibration paths are wired;
pi_setpoint still raises (ADR-0037).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .contracts import ActuatorCommand, ActuatorPath

if TYPE_CHECKING:
    from homeassistant.core import Context, HomeAssistant


def service_call_for(command: ActuatorCommand) -> tuple[str, str, dict[str, Any]]:
    """The (domain, service, data) for one command — pure, HA-free, testable."""
    if command.path is ActuatorPath.SETPOINT:
        return (
            "climate",
            "set_temperature",
            {"entity_id": command.actuator_id, "temperature": command.value},
        )
    if command.path is ActuatorPath.TPI_VALVE:
        # direct valve: actuator_id is the writable valve-opening number entity,
        # value is the open percentage 0..100 (ADR-0036). Never valve_closing_*.
        return (
            "number",
            "set_value",
            {"entity_id": command.actuator_id, "value": command.value},
        )
    if command.path is ActuatorPath.CALIBRATION:
        # calibration (ADR-0015: offset-calibration row of the capability
        # matrix): actuator_id is the writable offset number entity, value
        # the offset snapped to the entity's own grid/limits (P1.2 snap_offset).
        return (
            "number",
            "set_value",
            {"entity_id": command.actuator_id, "value": command.value},
        )
    raise NotImplementedError(f"actuator path not wired: {command.path}")


async def write(
    hass: HomeAssistant,
    command: ActuatorCommand,
    context: Context | None = None,
) -> None:
    """Translate one arbitrated command into exactly one HA service call.

    ``context`` tags the call so the resulting state change carries a Context the
    coordinator recognises as its own: the next tick can
    then tell our own write's echo -- including a device re-quantise / min-max clamp
    a push integration reports under this same context -- from a genuine external
    setpoint change, without guessing from the value alone.
    """
    domain, service, data = service_call_for(command)
    await hass.services.async_call(
        domain, service, data, blocking=False, context=context
    )
