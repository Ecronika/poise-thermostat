from __future__ import annotations

from custom_components.poise.multi.discovery import EntitySnapshot
from custom_components.poise.multi.model import Direction
from custom_components.poise.multi.resolvers import ThermalDemand
from custom_components.poise.multi.shadow import evaluate_thermal_shadow


def _trv_snap(available: bool = True) -> EntitySnapshot:
    return EntitySnapshot(
        "climate.trv", "climate", hvac_modes=("heat", "off"), available=available
    )


def test_heat_only_trv_picks_itself() -> None:
    s = evaluate_thermal_shadow(_trv_snap(), ThermalDemand(Direction.HEAT, 21.0))
    assert s.active_source == "climate.trv"
    assert s.reason == "thermal_heat_priority"
    assert s.severity == "info"
    assert s.blocked == ()
    assert "thermal:heat" in s.capabilities


def test_idle_is_no_demand() -> None:
    s = evaluate_thermal_shadow(_trv_snap(), ThermalDemand(None))
    assert s.active_source is None
    assert s.reason == "no_demand"


def test_unavailable_actuator_is_blocked_not_selected() -> None:
    s = evaluate_thermal_shadow(
        _trv_snap(available=False), ThermalDemand(Direction.HEAT, 21.0)
    )
    assert s.active_source is None
    assert s.reason == "no_capable_source"
    assert "device_unavailable" in s.blocked


def test_reversible_ac_cools() -> None:
    snap = EntitySnapshot("climate.ac", "climate", hvac_modes=("heat", "cool", "off"))
    s = evaluate_thermal_shadow(snap, ThermalDemand(Direction.COOL, 25.0))
    assert s.active_source == "climate.ac"
    assert s.reason == "thermal_cool_priority"
    assert "thermal:cool" in s.capabilities
