"""Directed device / capability data model for multi-actuator zones (ADR-0046 §2).

Replaces the earlier boolean ``can_heat`` / ``can_cool`` model: a device owns a
tuple of :class:`DeviceCapability`, each a (axis, direction) pair, so a reversible
AC is one device with heat + cool + fan + dry capabilities and the pipeline picks
at most one capability per device per tick.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .reason import ReasonCode


class Axis(Enum):
    THERMAL = "thermal"
    AIR_MOVEMENT = "air_movement"
    VENTILATION = "ventilation"
    HUMIDITY = "humidity"


class Direction(Enum):
    HEAT = "heat"
    COOL = "cool"
    FAN = "fan"
    EXHAUST = "exhaust"
    SUPPLY = "supply"
    BALANCED = "balanced"
    RECIRCULATE = "recirculate"
    DRY = "dry"
    HUMIDIFY = "humidify"


class DeviceMode(Enum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    FAN_ONLY = "fan_only"
    DRY = "dry"
    AUTO = "auto"
    UNKNOWN = "unknown"


class DeviceAction(Enum):
    HEATING = "heating"
    COOLING = "cooling"
    DRYING = "drying"
    FAN = "fan"
    IDLE = "idle"
    OFF = "off"
    UNKNOWN = "unknown"


class DeviceHealth(Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    FAULT = "fault"
    STALE = "stale"
    LOCKOUT = "lockout"


class StandbyPolicy(Enum):
    OFF = "off"
    HOLD_SAFE_SETPOINT = "hold_safe_setpoint"
    FAN_ONLY_LOW = "fan_only_low"
    LEAVE_AS_IS = "leave_as_is"
    RESTORE_PREVIOUS = "restore_previous"
    ECO = "eco"


class OwnershipReturn(Enum):
    IMMEDIATE = "immediate"
    TIMER = "timer"
    COMFORT_WINDOW = "comfort_window"
    EXPLICIT_REENABLE = "explicit_reenable"


# Command kinds — how a capability is actuated. The actual token always comes
# from the device's advertised modes, never hardcoded (ADR-0046 §3).
CMD_HVAC_MODE = "hvac_mode"
CMD_PRESET_MODE = "preset_mode"
CMD_FAN_MODE = "fan_mode"
CMD_SERVICE = "service"


@dataclass(frozen=True, slots=True)
class DeviceCapability:
    axis: Axis
    direction: Direction
    command_kind: str = CMD_HVAC_MODE
    mode_command: str | None = None
    setpoint_command: str | None = None
    supports_modulation: bool = False
    priority: int = 100

    @property
    def capability_id(self) -> str:
        return f"{self.axis.value}:{self.direction.value}"


# Reasoned standby defaults per adapter family (ADR-0046 §7). The AC default is
# the conservative OFF — fan_only_low is an opt-in comfort feature, not a default.
DEFAULT_STANDBY: Mapping[str, StandbyPolicy] = {
    "ClimateAdapter": StandbyPolicy.OFF,
    "TrvAdapter": StandbyPolicy.HOLD_SAFE_SETPOINT,
    "FanAdapter": StandbyPolicy.OFF,
    "HumidifierAdapter": StandbyPolicy.LEAVE_AS_IS,
    "SwitchAdapter": StandbyPolicy.OFF,
    "NumberValveAdapter": StandbyPolicy.HOLD_SAFE_SETPOINT,
}

# Conservative compressor anti-short-cycle defaults (ADR-0046 §8).
DEFAULT_MIN_OFF_S = 600.0
DEFAULT_MIN_ON_S = 120.0
DEFAULT_MIN_MODE_HOLD_S = 300.0
DEFAULT_MODE_DEADTIME_S = 120.0


@dataclass(frozen=True, slots=True)
class OwnershipPolicy:
    return_policy: OwnershipReturn = OwnershipReturn.COMFORT_WINDOW
    echo_tolerance_s: float = 30.0


@dataclass(frozen=True, slots=True)
class ZoneDevice:
    entity_id: str
    adapter: str
    capabilities: tuple[DeviceCapability, ...]
    standby_policy: StandbyPolicy = StandbyPolicy.OFF
    ownership_policy: OwnershipPolicy = field(default_factory=OwnershipPolicy)
    min_on_s: float = DEFAULT_MIN_ON_S
    min_off_s: float = DEFAULT_MIN_OFF_S
    min_mode_hold_s: float = DEFAULT_MIN_MODE_HOLD_S
    max_starts_per_h: int | None = None
    mode_change_deadtime_s: float = DEFAULT_MODE_DEADTIME_S
    noise_class: int | None = None
    location: str | None = None
    shared_resource_id: str | None = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]

    def capability(self, axis: Axis, direction: Direction) -> DeviceCapability | None:
        for c in self.capabilities:
            if c.axis is axis and c.direction is direction:
                return c
        return None

    def has(self, axis: Axis, direction: Direction) -> bool:
        return self.capability(axis, direction) is not None

    def directions(self, axis: Axis) -> tuple[Direction, ...]:
        return tuple(c.direction for c in self.capabilities if c.axis is axis)


@dataclass(frozen=True, slots=True)
class Command:
    """A built actuator command (ADR-0046 §3). Idempotent via ``dedupe_key``;
    ``expected_echo`` is the basis for external-override detection (§9). A
    ``Command`` is pure data — building one performs no HA service call.
    """

    entity_id: str
    domain: str
    service: str
    capability_id: str
    reason: ReasonCode
    issued_at_wall: float
    dedupe_key: str
    data: Mapping[str, Any] = field(default_factory=dict)
    expected_echo: Mapping[str, Any] = field(default_factory=dict)
