"""ADR-0048 non-goals guard.

``Axis.VENTILATION`` is never inventoried by discovery, and ``Direction.HUMIDIFY``
— although a real humidifier is inventoried so diagnostics can see it — is never
*actuated*: the control planner only ever commands the thermal axis (+ standby).
This locks the non-goals in place so future wiring cannot silently breach them.
"""

from __future__ import annotations

from custom_components.poise.multi.discovery import (
    EntitySnapshot,
    discover,
    discover_switch,
)
from custom_components.poise.multi.model import (
    Axis,
    DeviceCapability,
    Direction,
    ZoneDevice,
)
from custom_components.poise.multi.reason import ReasonCode
from custom_components.poise.multi.resolvers import (
    ThermalDemand,
    air_movement_resolver,
    assignment_planner,
    humidity_resolver,
    thermal_resolver,
)


def _all_discovered_caps() -> list[DeviceCapability]:
    """Capabilities from every discovery path, incl. all switch roles."""
    snaps = [
        EntitySnapshot(
            "climate.ac",
            "climate",
            hvac_modes=("heat", "cool", "dry", "fan_only", "off"),
            preset_modes=("Dry", "Boost"),
        ),
        EntitySnapshot("climate.trv", "climate", hvac_modes=("heat", "off")),
        EntitySnapshot("fan.ceiling", "fan"),
        EntitySnapshot("humidifier.h", "humidifier", device_class="humidifier"),
        EntitySnapshot("humidifier.d", "humidifier", device_class="dehumidifier"),
    ]
    caps: list[DeviceCapability] = []
    for s in snaps:
        caps += discover(s)
    for role in ("humidifier", "dehumidifier", "fan", "unknown"):
        caps += discover_switch(EntitySnapshot("switch.x", "switch"), role)
    return caps


def test_discovery_never_inventories_ventilation() -> None:
    # Axis.VENTILATION is a reserved non-goal: no discovery path maps to it.
    assert all(c.axis is not Axis.VENTILATION for c in _all_discovered_caps())


def test_humidify_is_inventoried_but_never_actuated() -> None:
    # a real humidifier IS inventoried (so diagnostics can see it)...
    assert any(c.direction is Direction.HUMIDIFY for c in _all_discovered_caps())
    # ...but the control planner only commands THERMAL (+ standby): a humidify
    # capability can never produce an actuation command (ADR-0048 control non-goal).
    heater = ZoneDevice(
        entity_id="climate.trv",
        adapter="TrvAdapter",
        capabilities=(
            DeviceCapability(
                Axis.THERMAL,
                Direction.HEAT,
                mode_command="heat",
                setpoint_command="temperature",
            ),
        ),
    )
    humidifier = ZoneDevice(
        entity_id="humidifier.h",
        adapter="HumidifierAdapter",
        capabilities=(DeviceCapability(Axis.HUMIDITY, Direction.HUMIDIFY),),
    )
    devices = [heater, humidifier]
    demand = ThermalDemand(direction=Direction.HEAT, target_c=21.0)
    reason = thermal_resolver(demand, devices, {})
    commands, _ = assignment_planner(reason, demand, devices, now_wall=0.0)
    for cmd in commands.values():
        ok = cmd.capability_id == "standby" or cmd.capability_id.startswith("thermal:")
        assert ok, cmd.capability_id
    # the humidifier specifically got a standby command, not a humidify actuation
    assert commands["humidifier.h"].capability_id == "standby"


def test_humidity_air_movement_resolvers_stay_noop() -> None:
    # both stable-interface resolvers emit a NOOP reason and no commands (ADR-0046 §4)
    assert humidity_resolver().reason is ReasonCode.HUMIDITY_NOOP
    assert air_movement_resolver().reason is ReasonCode.AIR_MOVEMENT_NOOP
