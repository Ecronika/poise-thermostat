from __future__ import annotations

from custom_components.poise.multi.discovery import (
    EntitySnapshot,
    discover,
    transient_zone_device,
)
from custom_components.poise.multi.model import Axis, Direction, StandbyPolicy


def test_heat_only_trv_has_only_thermal_heat() -> None:
    snap = EntitySnapshot("climate.trv", "climate", hvac_modes=("heat", "off"))
    caps = discover(snap)
    assert [(c.axis, c.direction) for c in caps] == [(Axis.THERMAL, Direction.HEAT)]
    assert caps[0].mode_command == "heat"


def test_auto_only_implies_heat_not_cool() -> None:
    snap = EntitySnapshot("climate.trv", "climate", hvac_modes=("auto", "off"))
    caps = discover(snap)
    dirs = {c.direction for c in caps if c.axis is Axis.THERMAL}
    assert dirs == {Direction.HEAT}
    # advertised token, not a hardcoded "heat"
    assert caps[0].mode_command == "auto"


def test_heat_cool_token_is_not_hardcoded() -> None:
    snap = EntitySnapshot("climate.ac", "climate", hvac_modes=("heat_cool", "off"))
    caps = discover(snap)
    by_dir = {c.direction: c for c in caps if c.axis is Axis.THERMAL}
    assert by_dir[Direction.HEAT].mode_command == "heat_cool"
    assert by_dir[Direction.COOL].mode_command == "heat_cool"


def test_reversible_ac_has_four_capabilities() -> None:
    snap = EntitySnapshot(
        "climate.ac",
        "climate",
        hvac_modes=("heat", "cool", "dry", "fan_only", "off"),
    )
    pairs = {(c.axis, c.direction) for c in discover(snap)}
    assert pairs == {
        (Axis.THERMAL, Direction.HEAT),
        (Axis.THERMAL, Direction.COOL),
        (Axis.HUMIDITY, Direction.DRY),
        (Axis.AIR_MOVEMENT, Direction.RECIRCULATE),
    }


def test_dry_as_preset_uses_preset_kind() -> None:
    snap = EntitySnapshot(
        "climate.ac",
        "climate",
        hvac_modes=("cool", "off"),
        preset_modes=("Dry", "boost"),
    )
    dry = next(c for c in discover(snap) if c.axis is Axis.HUMIDITY)
    assert dry.command_kind == "preset_mode"
    assert dry.mode_command == "Dry"  # ADR-0050 §9: original device casing kept


def test_fan_domain_is_air_movement() -> None:
    caps = discover(EntitySnapshot("fan.box", "fan"))
    assert [(c.axis, c.direction) for c in caps] == [
        (Axis.AIR_MOVEMENT, Direction.RECIRCULATE)
    ]


def test_dehumidifier_device_class() -> None:
    snap = EntitySnapshot("humidifier.dh", "humidifier", device_class="dehumidifier")
    cap = discover(snap)[0]
    assert cap.axis is Axis.HUMIDITY
    assert cap.direction is Direction.DRY


def test_bare_switch_without_role_yields_nothing() -> None:
    # degrade safe — never guess a switch's climate role (ADR-0046 §15)
    assert discover(EntitySnapshot("switch.x", "switch")) == []


def test_switch_with_role() -> None:
    caps = discover(EntitySnapshot("switch.dh", "switch"), role="dehumidifier")
    assert caps[0].direction is Direction.DRY


def test_unknown_domain_yields_nothing() -> None:
    assert discover(EntitySnapshot("light.x", "light")) == []


def test_transient_trv_holds_frost_floor_on_standby() -> None:
    snap = EntitySnapshot("climate.trv", "climate", hvac_modes=("heat", "off"))
    dev = transient_zone_device(snap)
    assert dev.adapter == "TrvAdapter"
    assert dev.standby_policy is StandbyPolicy.HOLD_SAFE_SETPOINT


def test_transient_reversible_ac_standby_off() -> None:
    snap = EntitySnapshot("climate.ac", "climate", hvac_modes=("heat", "cool", "off"))
    dev = transient_zone_device(snap)
    assert dev.adapter == "ClimateAdapter"
    assert dev.standby_policy is StandbyPolicy.OFF
