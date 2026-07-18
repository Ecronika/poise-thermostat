"""R13 (P3): pure per-zone heat-demand helper.

The value the hub aggregates for the shared boiler is now derived by one shared
helper (``zone_heat_demand``) and also published per-zone, so the aggregated and
the surfaced value can never drift.
"""

from __future__ import annotations

from custom_components.poise.control.hub_aggregate import (
    zone_heat_demand,
    zone_request_from_data,
)


def test_zone_heat_demand_prefers_duty_else_binary() -> None:
    # the live TPI duty shadow wins when present
    assert zone_heat_demand(heating=True, tpi_duty=0.42, frozen=False) == 0.42
    assert zone_heat_demand(heating=False, tpi_duty=0.3, frozen=False) == 0.3
    # no duty -> binary fall-back from ``heating``
    assert zone_heat_demand(heating=True, tpi_duty=None, frozen=False) == 1.0
    assert zone_heat_demand(heating=False, tpi_duty=None, frozen=False) == 0.0


def test_zone_heat_demand_frozen_forces_zero() -> None:
    # V9: a dead room sensor never pins the shared boiler, even mid-heat / w/ duty
    assert zone_heat_demand(heating=True, tpi_duty=0.9, frozen=True) == 0.0
    assert zone_heat_demand(heating=True, tpi_duty=None, frozen=True) == 0.0


def test_zone_request_uses_the_same_helper() -> None:
    # the hub's ZoneRequest.heat_demand IS zone_heat_demand(...) -- no drift
    data = {
        "heating": True,
        "tpi_duty": 0.55,
        "current_temperature": 20.0,
        "heat_sp": 21.0,
    }
    req = zone_request_from_data(
        "z",
        data,
        controls_boiler=True,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert req.heat_demand == zone_heat_demand(
        heating=True, tpi_duty=0.55, frozen=False
    )
    assert req.heat_demand == 0.55
