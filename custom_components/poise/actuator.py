"""Actuator choke-point — the single writer per device (ADR-0013).

Every ``ActuatorCommand`` produced by arbitration is written here and nowhere
else. Phase 0 implements only the setpoint path; the capability-matrix paths
(tpi_valve / calibration / pi_setpoint) land in Phase 3 (ADR-0015).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .contracts import ActuatorCommand, ActuatorPath

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def write(hass: HomeAssistant, command: ActuatorCommand) -> None:
    """Translate one arbitrated command into exactly one HA service call."""
    if command.path is ActuatorPath.SETPOINT:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": command.actuator_id, "temperature": command.value},
            blocking=False,
        )
        return
    raise NotImplementedError(f"actuator path not in Phase 0: {command.path}")
