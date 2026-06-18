from __future__ import annotations

from custom_components.poise.clock import ManualClock
from custom_components.poise.contracts import Reading, Source
from custom_components.poise.controller import BangBangController
from custom_components.poise.pipeline import ZoneInputs, run_tick


def _zone(air: float, target: float = 21.0, frost: float = 7.0) -> ZoneInputs:
    reading = Reading(air, "°C", Source.MEASURED, 0.9, 0.0)
    return ZoneInputs("trv", reading, target, frost, device_max=30.0)


def test_tick_is_deterministic() -> None:
    zones = {"a": _zone(18.0), "b": _zone(22.5)}
    controller = BangBangController()
    first = run_tick(zones, clock=ManualClock(), controller=controller)
    second = run_tick(zones, clock=ManualClock(), controller=controller)
    assert first == second


def test_cold_room_commands_heat_to_target() -> None:
    command = run_tick(
        {"z": _zone(18.0)}, clock=ManualClock(), controller=BangBangController()
    )["z"]
    assert command.value == 21.0
    assert command.hvac_mode == "heat"


def test_setpoint_never_below_frost_floor() -> None:
    command = run_tick(
        {"z": _zone(25.0, target=21.0, frost=7.0)},
        clock=ManualClock(),
        controller=BangBangController(),
    )["z"]
    assert command.value >= 7.0


def test_one_command_per_zone() -> None:
    zones = {"a": _zone(18.0), "b": _zone(19.0), "c": _zone(25.0)}
    commands = run_tick(zones, clock=ManualClock(), controller=BangBangController())
    assert set(commands) == {"a", "b", "c"}
