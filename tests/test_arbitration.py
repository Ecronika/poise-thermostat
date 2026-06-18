from __future__ import annotations

from custom_components.poise.arbitration import resolve
from custom_components.poise.contracts import (
    ActuatorPath,
    Bound,
    ComfortCorridor,
    ControlRequest,
)


def _corridor(upper: float = 35.0) -> ComfortCorridor:
    return ComfortCorridor((Bound(7.0, "frost"),), (Bound(upper, "band"),), 21.0)


def test_clamps_to_device_max_below_corridor_upper() -> None:
    # corridor would allow up to 35 °C, but the device maxes out at 30 °C
    request = ControlRequest("trv", ActuatorPath.SETPOINT, target_setpoint=34.0)
    command = resolve(_corridor(upper=35.0), request, device_max=30.0)
    assert command.value == 30.0
    assert command.clamped_by == "device_max"


def test_uses_corridor_target_when_request_has_no_setpoint() -> None:
    request = ControlRequest("trv", ActuatorPath.SETPOINT)
    command = resolve(_corridor(), request, device_max=30.0)
    assert command.value == 21.0
    assert command.clamped_by is None
