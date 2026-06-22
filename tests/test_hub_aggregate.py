"""Tests for the pure multi-zone boiler-demand aggregate (ADR-0038/0039)."""

from __future__ import annotations

from custom_components.poise.contracts import ZoneRequest
from custom_components.poise.control.hub_aggregate import (
    aggregate_boiler_demand,
    gate_min_cycle,
)


def _zone(
    zid: str,
    *,
    heating: bool = False,
    heat_demand: float = 0.0,
    frost: bool = False,
    controls_boiler: bool = True,
    declared_power: float | None = None,
) -> ZoneRequest:
    return ZoneRequest(
        zone_id=zid,
        heating=heating,
        hvac_action="heating" if heating else "idle",
        heat_demand=heat_demand,
        comfort_gap=0.0,
        frost_active=frost,
        controls_boiler=controls_boiler,
        mono_ts=0.0,
        declared_power=declared_power,
    )


def test_empty_is_inactive() -> None:
    d = aggregate_boiler_demand([])
    assert d.active is False and d.active_count == 0 and d.weighted_demand == 0.0


def test_non_participating_zones_ignored() -> None:
    # heating, but controls_boiler=False -> not counted
    d = aggregate_boiler_demand([_zone("a", heating=True, controls_boiler=False)])
    assert d.active is False and d.active_count == 0


def test_count_threshold() -> None:
    zones = [_zone("a", heating=True), _zone("b", heating=False)]
    assert aggregate_boiler_demand(zones, count_threshold=1).active is True
    assert aggregate_boiler_demand(zones, count_threshold=2).active is False


def test_power_threshold() -> None:
    zones = [
        _zone("a", heating=True, heat_demand=0.5, declared_power=2.0),
        _zone("b", heating=True, heat_demand=0.5, declared_power=2.0),
    ]  # weighted = 2.0
    # count must not trigger on its own
    assert aggregate_boiler_demand(zones, count_threshold=9, power_threshold=2.0).active
    d = aggregate_boiler_demand(zones, count_threshold=9, power_threshold=3.0)
    assert d.active is False and d.weighted_demand == 2.0


def test_frost_override_forces_on_below_threshold() -> None:
    zones = [_zone("a", heating=False, frost=True)]
    d = aggregate_boiler_demand(zones, count_threshold=5)
    assert d.active is True and d.frost_override is True and d.active_count == 0


def test_heat_demand_clamped_and_default_power() -> None:
    # declared_power None -> weight 1.0; heat_demand>1 clamped to 1.0
    d = aggregate_boiler_demand(
        [_zone("a", heating=True, heat_demand=5.0)],
        count_threshold=9,
        power_threshold=1.0,
    )
    assert d.weighted_demand == 1.0 and d.active is True


def test_min_cycle_blocks_premature_off() -> None:
    # currently on, want off, only 100s since change, min_on 300 -> stay on
    assert (
        gate_min_cycle(
            False,
            currently_on=True,
            last_change_mono=0.0,
            now_mono=100.0,
            min_on_s=300.0,
            min_off_s=300.0,
        )
        is True
    )
    # 400s elapsed -> allowed off
    assert (
        gate_min_cycle(
            False,
            currently_on=True,
            last_change_mono=0.0,
            now_mono=400.0,
            min_on_s=300.0,
            min_off_s=300.0,
        )
        is False
    )


def test_min_cycle_blocks_premature_on_and_no_change_passthrough() -> None:
    assert (
        gate_min_cycle(
            True,
            currently_on=False,
            last_change_mono=0.0,
            now_mono=100.0,
            min_on_s=300.0,
            min_off_s=300.0,
        )
        is False
    )
    # desired == current -> passthrough
    assert (
        gate_min_cycle(
            True,
            currently_on=True,
            last_change_mono=0.0,
            now_mono=1.0,
            min_on_s=300.0,
            min_off_s=300.0,
        )
        is True
    )
