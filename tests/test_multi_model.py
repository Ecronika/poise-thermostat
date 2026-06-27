from __future__ import annotations

from custom_components.poise.multi.model import (
    DEFAULT_STANDBY,
    Axis,
    Command,
    DeviceCapability,
    Direction,
    StandbyPolicy,
    ZoneDevice,
)
from custom_components.poise.multi.reason import ReasonCode


def test_capability_id() -> None:
    cap = DeviceCapability(Axis.THERMAL, Direction.HEAT)
    assert cap.capability_id == "thermal:heat"


def test_zone_device_lookup_and_domain() -> None:
    dev = ZoneDevice(
        "climate.ac",
        "ClimateAdapter",
        (
            DeviceCapability(Axis.THERMAL, Direction.HEAT),
            DeviceCapability(Axis.THERMAL, Direction.COOL),
            DeviceCapability(Axis.HUMIDITY, Direction.DRY),
            DeviceCapability(Axis.AIR_MOVEMENT, Direction.RECIRCULATE),
        ),
    )
    assert dev.domain == "climate"
    assert dev.has(Axis.THERMAL, Direction.HEAT)
    assert dev.has(Axis.THERMAL, Direction.COOL)
    assert dev.capability(Axis.HUMIDITY, Direction.DRY) is not None
    assert dev.capability(Axis.VENTILATION, Direction.SUPPLY) is None
    assert set(dev.directions(Axis.THERMAL)) == {Direction.HEAT, Direction.COOL}


def test_standby_defaults_ac_off_trv_hold() -> None:
    assert DEFAULT_STANDBY["ClimateAdapter"] is StandbyPolicy.OFF
    assert DEFAULT_STANDBY["TrvAdapter"] is StandbyPolicy.HOLD_SAFE_SETPOINT


def test_command_is_pure_data() -> None:
    cmd = Command(
        entity_id="climate.ac",
        domain="climate",
        service="set_hvac_mode",
        capability_id="thermal:heat",
        reason=ReasonCode.THERMAL_HEAT_PRIORITY,
        issued_at_wall=1000.0,
        dedupe_key="climate.ac:heat:21.0",
    )
    assert cmd.domain == "climate"
    assert dict(cmd.data) == {}
    assert dict(cmd.expected_echo) == {}
