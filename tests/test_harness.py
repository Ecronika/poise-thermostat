from __future__ import annotations

from custom_components.poise.controller import BangBangController
from tests.harness.replay import Scenario, simulate


def test_bangbang_reaches_target_in_plant() -> None:
    trace = simulate(BangBangController(), Scenario())
    assert abs(trace[-1].air - 21.0) < 1.0


def test_room_warms_from_cold_start() -> None:
    trace = simulate(BangBangController(), Scenario(start_air=16.0))
    assert trace[-1].air > trace[0].air


def test_simulation_is_deterministic() -> None:
    first = simulate(BangBangController(), Scenario())
    second = simulate(BangBangController(), Scenario())
    assert [p.air for p in first] == [p.air for p in second]
