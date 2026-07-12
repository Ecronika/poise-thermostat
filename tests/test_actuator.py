"""Glue test for the actuator write path (review P3).

``actuator`` is runtime-HA-free, so the real ``write`` coroutine is exercised
against a tiny fake hass that captures the service call — no Home Assistant
test rig needed.
"""

from __future__ import annotations

import asyncio

import pytest

from custom_components.poise.actuator import service_call_for, write
from custom_components.poise.contracts import ActuatorCommand, ActuatorPath


def _cmd(path=ActuatorPath.SETPOINT, value=21.5, hvac_mode="heat"):
    return ActuatorCommand("climate.trv", path, value, hvac_mode, "heat", None)


def test_service_call_for_setpoint() -> None:
    # P2-3: a conditioning mode rides along in set_temperature (atomic switch)
    domain, service, data = service_call_for(_cmd(value=21.5))
    assert (domain, service) == ("climate", "set_temperature")
    assert data == {
        "entity_id": "climate.trv",
        "temperature": 21.5,
        "hvac_mode": "heat",
    }


def test_setpoint_rides_hvac_mode_atomically() -> None:
    # P2-3: each conditioning mode is carried in the single set_temperature call
    for mode in ("heat", "cool", "dry", "heat_cool"):
        _, _, data = service_call_for(_cmd(value=24.0, hvac_mode=mode))
        assert data["hvac_mode"] == mode
        assert data["temperature"] == 24.0


def test_setpoint_omits_non_conditioning_mode() -> None:
    # P2-3: off/idle/fan_only carry no setpoint semantics -> no atomic mode ride,
    # so the guard-held switch is never bypassed by the setpoint write.
    for mode in ("off", "idle", "fan_only", "auto"):
        _, _, data = service_call_for(_cmd(value=24.0, hvac_mode=mode))
        assert "hvac_mode" not in data
        assert data == {"entity_id": "climate.trv", "temperature": 24.0}


def test_service_call_for_unsupported_path_raises() -> None:
    # CALIBRATION is not wired yet -> must raise (TPI_VALVE is now supported)
    with pytest.raises(NotImplementedError):
        service_call_for(_cmd(path=ActuatorPath.CALIBRATION))


class _FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def async_call(self, domain, service, data, blocking):  # noqa: ANN001
        self.calls.append((domain, service, data, blocking))


class _FakeHass:
    def __init__(self) -> None:
        self.services = _FakeServices()


def test_write_issues_exactly_one_nonblocking_service_call() -> None:
    hass = _FakeHass()
    asyncio.run(write(hass, _cmd(value=20.0)))
    assert hass.services.calls == [
        (
            "climate",
            "set_temperature",
            {"entity_id": "climate.trv", "temperature": 20.0, "hvac_mode": "heat"},
            False,
        )
    ]


def test_service_call_for_tpi_valve() -> None:
    # TPI valve: actuator_id is the valve-opening number, value is 0..100 %
    cmd = ActuatorCommand(
        "number.trvzb_valve_opening_degree",
        ActuatorPath.TPI_VALVE,
        65.0,
        "heat",
        "heat",
        None,
    )
    domain, service, data = service_call_for(cmd)
    assert (domain, service) == ("number", "set_value")
    assert data == {"entity_id": "number.trvzb_valve_opening_degree", "value": 65.0}
