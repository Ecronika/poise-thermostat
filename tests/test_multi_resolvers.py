from __future__ import annotations

from custom_components.poise.multi.model import (
    Axis,
    DeviceCapability,
    DeviceHealth,
    Direction,
    ZoneDevice,
)
from custom_components.poise.multi.reason import (
    BlockingCause,
    FallbackCause,
    ReasonCode,
)
from custom_components.poise.multi.resolvers import (
    DeviceRuntime,
    ThermalDemand,
    air_movement_resolver,
    assignment_planner,
    humidity_resolver,
    thermal_resolver,
)


def _heat_dev(entity_id: str, priority: int = 100) -> ZoneDevice:
    cap = DeviceCapability(
        Axis.THERMAL,
        Direction.HEAT,
        mode_command="heat",
        setpoint_command="temperature",
        priority=priority,
    )
    return ZoneDevice(entity_id, "ClimateAdapter", (cap,))


def test_no_demand() -> None:
    r = thermal_resolver(ThermalDemand(None), [], {})
    assert r.reason is ReasonCode.NO_DEMAND
    assert r.selected_source is None


def test_single_source_priority() -> None:
    r = thermal_resolver(ThermalDemand(Direction.HEAT), [_heat_dev("climate.trv")], {})
    assert r.reason is ReasonCode.THERMAL_HEAT_PRIORITY
    assert r.selected_source == "climate.trv"


def test_lower_priority_value_wins() -> None:
    devs = [_heat_dev("climate.trv", 100), _heat_dev("climate.ac", 50)]
    r = thermal_resolver(ThermalDemand(Direction.HEAT), devs, {})
    assert r.selected_source == "climate.ac"  # priority 50 < 100


def test_failover_skips_unhealthy_primary() -> None:
    devs = [_heat_dev("climate.ac", 50), _heat_dev("climate.trv", 100)]
    runtimes = {"climate.ac": DeviceRuntime(health=DeviceHealth.FAULT)}
    r = thermal_resolver(ThermalDemand(Direction.HEAT), devs, runtimes)
    assert r.selected_source == "climate.trv"
    assert r.reason is ReasonCode.FAILOVER_PRIMARY_UNHEALTHY
    assert r.fallback is FallbackCause.PRIMARY_UNHEALTHY
    assert BlockingCause.DEVICE_UNHEALTHY in r.blocked


def test_min_off_blocks_only_source() -> None:
    runtimes = {"climate.ac": DeviceRuntime(min_off_active=True)}
    r = thermal_resolver(
        ThermalDemand(Direction.HEAT), [_heat_dev("climate.ac")], runtimes
    )
    assert r.reason is ReasonCode.NO_CAPABLE_SOURCE
    assert BlockingCause.COMPRESSOR_MIN_OFF_ACTIVE in r.blocked
    assert r.selected_source is None


def test_humidity_and_air_resolvers_are_noop() -> None:
    assert humidity_resolver().reason is ReasonCode.HUMIDITY_NOOP
    r = air_movement_resolver("x", 1, 2)
    assert r.reason is ReasonCode.AIR_MOVEMENT_NOOP


def test_planner_selected_command_and_standby_for_rest() -> None:
    selected = _heat_dev("climate.trv")
    other = _heat_dev("climate.ac")
    demand = ThermalDemand(Direction.HEAT, 21.0)
    reason = thermal_resolver(demand, [selected], {})
    cmds, out = assignment_planner(reason, demand, [selected, other], now_wall=1000.0)
    sel = cmds["climate.trv"]
    assert sel.capability_id == "thermal:heat"
    assert sel.expected_echo["hvac_mode"] == "heat"
    assert sel.data["temperature"] == 21.0
    assert sel.dedupe_key == "climate.trv:heat:21.0"
    # non-selected device gets a standby (OFF -> turn_off) command, no thermal write
    assert cmds["climate.ac"].service == "turn_off"
    assert cmds["climate.ac"].capability_id == "standby"
    # reason passes through unchanged (pure diagnostics, never alters control)
    assert out is reason


def test_no_demand_yields_only_standby() -> None:
    dev = _heat_dev("climate.trv")
    demand = ThermalDemand(None)
    reason = thermal_resolver(demand, [dev], {})
    cmds, _ = assignment_planner(reason, demand, [dev], now_wall=0.0)
    assert cmds["climate.trv"].capability_id == "standby"
