"""Capability-driven config-flow field selection (ADR-0046 §12).

Pure: given the device menu and which sensors exist, decide *which* fields to
show — so a single-TRV user sees exactly three setup fields and never the
arbitration / humidity / air-movement knobs. The glue maps these specs to a
voluptuous schema; the decision itself is table-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_NAME,
    CONF_TEMP_SENSOR,
)
from .model import Axis, Direction, ZoneDevice

# Option keys introduced by ADR-0046; promoted to const.py when the glue/storage
# lands in P3. Kept local to the pure layer for P0.
FIELD_ARBITRATION = "arbitration"
FIELD_STANDBY = "standby_policy"
FIELD_BOOST = "boost"
FIELD_AIR_MOVEMENT_CREDIT = "air_movement_credit"
FIELD_HUMIDITY_CONTROL = "humidity_control"
FIELD_COP_BALANCE = "cop_balance_c"  # advanced
FIELD_MARGINAL_COST = "marginal_cost_sensor"  # advanced
FIELD_MODE_DEADTIME = "mode_change_deadtime_s"  # advanced


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    required: bool = False
    advanced: bool = False


def build_setup_fields() -> tuple[FieldSpec, ...]:
    """First-zone setup = exactly three fields (ADR-0046 §12): room sensor and
    actuator required, display name optional/auto. Comfort base + category have
    defaults and move to the options flow.
    """
    return (
        FieldSpec(CONF_NAME),
        FieldSpec(CONF_TEMP_SENSOR, required=True),
        FieldSpec(CONF_ACTUATOR, required=True),
    )


def _thermal_source_count(devices: tuple[ZoneDevice, ...]) -> int:
    return sum(
        1
        for d in devices
        if d.has(Axis.THERMAL, Direction.HEAT) or d.has(Axis.THERMAL, Direction.COOL)
    )


def _any_cap(devices: tuple[ZoneDevice, ...], axis: Axis, direction: Direction) -> bool:
    return any(d.has(axis, direction) for d in devices)


def build_options_fields(
    devices: tuple[ZoneDevice, ...],
    *,
    has_humidity_sensor: bool = False,
    has_humidity_actuator: bool = False,
    has_presence: bool = False,
    advanced: bool = False,
) -> tuple[FieldSpec, ...]:
    """Capability-driven options. Only what the real devices/sensors support is
    shown; the deepest knobs are gated behind ``advanced`` (ADR-0046 §12).
    """
    fields: list[FieldSpec] = [
        FieldSpec(CONF_COMFORT_BASE),
        FieldSpec(CONF_CATEGORY),
    ]
    if _any_cap(devices, Axis.THERMAL, Direction.COOL):
        fields.append(FieldSpec(CONF_CLIMATE_MODE))
    # Arbitration appears only with >= 2 thermal sources.
    if _thermal_source_count(devices) >= 2:
        fields.append(FieldSpec(FIELD_ARBITRATION))
        fields.append(FieldSpec(FIELD_STANDBY))
        fields.append(FieldSpec(FIELD_BOOST))
        if advanced:
            fields.append(FieldSpec(FIELD_COP_BALANCE, advanced=True))
            fields.append(FieldSpec(FIELD_MARGINAL_COST, advanced=True))
    # Air-movement comfort credit needs a fan_only-capable device AND presence.
    if _any_cap(devices, Axis.AIR_MOVEMENT, Direction.RECIRCULATE) and has_presence:
        fields.append(FieldSpec(FIELD_AIR_MOVEMENT_CREDIT))
    # Humidity axis only when both a sensor and an actuator exist.
    if has_humidity_sensor and has_humidity_actuator:
        fields.append(FieldSpec(FIELD_HUMIDITY_CONTROL))
    if advanced:
        fields.append(FieldSpec(FIELD_MODE_DEADTIME, advanced=True))
    return tuple(fields)


def field_keys(fields: tuple[FieldSpec, ...]) -> frozenset[str]:
    return frozenset(f.key for f in fields)
