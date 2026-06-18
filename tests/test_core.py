from __future__ import annotations

from custom_components.poise.clock import MonotonicClock
from custom_components.poise.contracts import (
    ComfortCorridor,
    ControlRequest,
    Reading,
    Source,
    ThermalState,
)
from custom_components.poise.pipeline import ZoneInputs, run_tick


def test_monotonic_clock_is_nondecreasing() -> None:
    clock = MonotonicClock()
    first = clock.monotonic()
    second = clock.monotonic()
    assert isinstance(first, float)
    assert second >= first


class _RaisingController:
    """Controller that always fails, to prove per-zone isolation (ADR-0012)."""

    def evaluate(
        self, state: ThermalState, corridor: ComfortCorridor, actuator_id: str
    ) -> ControlRequest:
        raise RuntimeError("boom")


def test_failing_zone_is_isolated_and_tick_survives() -> None:
    zone = ZoneInputs(
        actuator_id="trv",
        t_air=Reading(20.0, "°C", Source.MEASURED, 0.9, 0.0),
        target=21.0,
        frost_floor=7.0,
        device_max=30.0,
    )
    commands = run_tick(
        {"z": zone}, clock=MonotonicClock(), controller=_RaisingController()
    )
    assert commands == {}
