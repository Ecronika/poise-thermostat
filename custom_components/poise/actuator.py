"""Actuator choke-point — the single writer per device (ADR-0013).

Every ``ActuatorCommand`` produced by arbitration is written here and nowhere
else. Phase 0 implements only the setpoint path; the capability-matrix paths
(tpi_valve / calibration / pi_setpoint) land in Phase 3 (ADR-0015).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .contracts import ActuatorCommand, ActuatorPath

if TYPE_CHECKING:
    from homeassistant.core import Context, HomeAssistant


def service_call_for(command: ActuatorCommand) -> tuple[str, str, dict[str, Any]]:
    """The (domain, service, data) for one command — pure, HA-free, testable.

    Phase 0 implements only the setpoint path; other capability-matrix paths
    (tpi_valve / calibration / pi_setpoint) are not wired yet (ADR-0015).
    """
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
    raise NotImplementedError(f"actuator path not wired: {command.path}")


async def write(
    hass: HomeAssistant,
    command: ActuatorCommand,
    context: Context | None = None,
) -> None:
    """Translate one arbitrated command into exactly one HA service call.

    ``context`` tags the call so the resulting state change carries a Context the
    coordinator recognises as its own (V2, analysis 2026-07-14): the next tick can
    then tell our own write's echo -- including a device re-quantise / min-max clamp
    a push integration reports under this same context -- from a genuine external
    setpoint change, without guessing from the value alone.
    """
    domain, service, data = service_call_for(command)
    await hass.services.async_call(
        domain, service, data, blocking=False, context=context
    )
