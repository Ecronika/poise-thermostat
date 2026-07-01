"""Pure capability discovery — the HA-free inventory layer (ADR-0046 §3).

Given a normalised :class:`EntitySnapshot` (the glue extracts it from HA state),
return the device's directed capabilities. Mode tokens are taken from the
device's *advertised* modes — never hardcoded (Gree/Midea numerics, Honeywell
``heat_cool``, a missing ``auto``). Unknown domains/roles degrade to *no
capability* — Poise never guesses (ADR-0046 §15).
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import (
    CMD_HVAC_MODE,
    CMD_PRESET_MODE,
    CMD_SERVICE,
    DEFAULT_STANDBY,
    Axis,
    DeviceCapability,
    Direction,
    StandbyPolicy,
    ZoneDevice,
)

# Precedence for picking the actual token to set, from the advertised modes.
_HEAT_MODES = ("heat", "heat_cool", "auto")
_COOL_MODES = ("cool", "heat_cool")

ADAPTER_FOR_DOMAIN = {
    "climate": "ClimateAdapter",
    "fan": "FanAdapter",
    "humidifier": "HumidifierAdapter",
    "switch": "SwitchAdapter",
    "number": "NumberValveAdapter",
}

# A bare switch carries no inherent climate role; the user assigns one. Without a
# role we return nothing rather than guess (ADR-0046 §15).
_SWITCH_ROLES: dict[str, tuple[Axis, Direction]] = {
    "dehumidifier": (Axis.HUMIDITY, Direction.DRY),
    "humidifier": (Axis.HUMIDITY, Direction.HUMIDIFY),
    "fan": (Axis.AIR_MOVEMENT, Direction.RECIRCULATE),
}


@dataclass(frozen=True, slots=True)
class EntitySnapshot:
    """HA-free, already-extracted view of one entity (the glue fills it in)."""

    entity_id: str
    domain: str
    hvac_modes: tuple[str, ...] = ()
    fan_modes: tuple[str, ...] = ()
    preset_modes: tuple[str, ...] = ()
    device_class: str | None = None
    available: bool = True


def _first_present(candidates: tuple[str, ...], modes: set[str]) -> str | None:
    for token in candidates:
        if token in modes:
            return token
    return None


def _match_original(
    candidates: tuple[str, ...], originals: tuple[str, ...]
) -> str | None:
    """Case-insensitive match returning the ORIGINAL casing (ADR-0050 §9).

    HVAC modes are standard lowercase, but device presets keep their own casing
    ("Dry"/"Dehumidify") and ``set_preset_mode`` needs that exact string — a
    lowercased command would be rejected by the device.
    """
    lowered = {value.lower(): value for value in originals}
    for token in candidates:
        if token in lowered:
            return lowered[token]
    return None


def discover_climate(snap: EntitySnapshot) -> list[DeviceCapability]:
    modes = {m.lower() for m in snap.hvac_modes}
    caps: list[DeviceCapability] = []

    heat_token = _first_present(_HEAT_MODES, modes)
    if heat_token is not None:
        caps.append(
            DeviceCapability(
                Axis.THERMAL,
                Direction.HEAT,
                command_kind=CMD_HVAC_MODE,
                mode_command=heat_token,
                setpoint_command="temperature",
            )
        )
    cool_token = _first_present(_COOL_MODES, modes)
    if cool_token is not None:
        caps.append(
            DeviceCapability(
                Axis.THERMAL,
                Direction.COOL,
                command_kind=CMD_HVAC_MODE,
                mode_command=cool_token,
                setpoint_command="temperature",
            )
        )
    # dry: prefer a real hvac_mode, else a preset (e.g. "Dry") — kind differs.
    if "dry" in modes:
        caps.append(
            DeviceCapability(
                Axis.HUMIDITY,
                Direction.DRY,
                command_kind=CMD_HVAC_MODE,
                mode_command="dry",
            )
        )
    else:
        dry_preset = _match_original(("dry", "dehumidify"), snap.preset_modes)
        if dry_preset is not None:
            caps.append(
                DeviceCapability(
                    Axis.HUMIDITY,
                    Direction.DRY,
                    command_kind=CMD_PRESET_MODE,
                    mode_command=dry_preset,
                )
            )
    if "fan_only" in modes:
        caps.append(
            DeviceCapability(
                Axis.AIR_MOVEMENT,
                Direction.RECIRCULATE,
                command_kind=CMD_HVAC_MODE,
                mode_command="fan_only",
            )
        )
    return caps


def discover_fan(snap: EntitySnapshot) -> list[DeviceCapability]:
    return [
        DeviceCapability(
            Axis.AIR_MOVEMENT,
            Direction.RECIRCULATE,
            command_kind=CMD_SERVICE,
            mode_command="on",
            setpoint_command="percentage",
        )
    ]


def discover_humidifier(snap: EntitySnapshot) -> list[DeviceCapability]:
    is_dehumidifier = (snap.device_class or "").lower() == "dehumidifier"
    direction = Direction.DRY if is_dehumidifier else Direction.HUMIDIFY
    return [
        DeviceCapability(
            Axis.HUMIDITY,
            direction,
            command_kind=CMD_SERVICE,
            mode_command="on",
            setpoint_command="humidity",
        )
    ]


def discover_switch(
    snap: EntitySnapshot, role: str | None = None
) -> list[DeviceCapability]:
    pair = _SWITCH_ROLES.get((role or "").lower())
    if pair is None:
        return []
    axis, direction = pair
    return [
        DeviceCapability(axis, direction, command_kind=CMD_SERVICE, mode_command="on")
    ]


def discover(
    snap: EntitySnapshot, *, role: str | None = None
) -> list[DeviceCapability]:
    if snap.domain == "climate":
        return discover_climate(snap)
    if snap.domain == "fan":
        return discover_fan(snap)
    if snap.domain == "humidifier":
        return discover_humidifier(snap)
    if snap.domain == "switch":
        return discover_switch(snap, role)
    return []  # unknown domain -> no capability (degrade safe, never guess)


def _adapter_for(domain: str, caps: list[DeviceCapability]) -> str:
    """A heat-only ``climate`` is a TRV/radiator (hold the frost floor on
    standby); anything that can cool / move air / dry is an AC (default OFF).
    """
    if domain == "climate":
        non_heat = any(
            not (c.axis is Axis.THERMAL and c.direction is Direction.HEAT) for c in caps
        )
        return "ClimateAdapter" if non_heat else "TrvAdapter"
    return ADAPTER_FOR_DOMAIN.get(domain, "ClimateAdapter")


def transient_zone_device(
    snap: EntitySnapshot, *, role: str | None = None
) -> ZoneDevice:
    """Build a transient ZoneDevice from one actuator — the CONF_ACTUATOR
    read-path used already in P0/P1 (no storage change; ADR-0046 §13).
    """
    caps = discover(snap, role=role)
    adapter = _adapter_for(snap.domain, caps)
    standby = DEFAULT_STANDBY.get(adapter, StandbyPolicy.OFF)
    return ZoneDevice(
        entity_id=snap.entity_id,
        adapter=adapter,
        capabilities=tuple(caps),
        standby_policy=standby,
    )
