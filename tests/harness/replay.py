"""Forward-simulation / replay harness (ADR-0011).

Key principle: the harness drives the **production** pipeline (`run_tick`)
and the **production** controller against the shared RC plant. Test-sim and
real controller share the same code path, so a green harness test means the
real control logic is green.
"""

from __future__ import annotations

from dataclasses import dataclass

from custom_components.poise.clock import ManualClock
from custom_components.poise.controller import Controller
from custom_components.poise.ingestion import RawSample, ingest_temperature
from custom_components.poise.pipeline import ZoneInputs, run_tick

from .plant import RCPlant


@dataclass(slots=True)
class Scenario:
    t_out: float = 5.0
    target: float = 21.0
    frost_floor: float = 7.0
    device_max: float = 30.0
    start_air: float = 18.0
    dt: float = 60.0
    steps: int = 600  # 10 h at 60 s


@dataclass(frozen=True, slots=True)
class TracePoint:
    t: float
    air: float
    setpoint: float


def simulate(
    controller: Controller,
    scenario: Scenario | None = None,
    plant: RCPlant | None = None,
) -> list[TracePoint]:
    scenario = scenario or Scenario()
    plant = plant or RCPlant()
    clock = ManualClock()
    air = scenario.start_air
    trace: list[TracePoint] = []
    for _ in range(scenario.steps):
        reading = ingest_temperature(
            [RawSample(air, clock.monotonic())], now=clock.monotonic()
        )
        zone = ZoneInputs(
            actuator_id="trv",
            t_air=reading,
            target=scenario.target,
            frost_floor=scenario.frost_floor,
            device_max=scenario.device_max,
        )
        commands = run_tick({"z": zone}, clock=clock, controller=controller)
        command = commands["z"]
        # Phase-0 "device": heat at full power while commanded above air temp.
        power = 1.0 if command.value > air else 0.0
        air = plant.step(air, power, scenario.t_out, scenario.dt)
        clock.advance(scenario.dt)
        trace.append(TracePoint(clock.monotonic(), air, command.value))
    return trace
