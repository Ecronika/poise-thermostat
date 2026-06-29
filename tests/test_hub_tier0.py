"""Tier-0 safety fixes for the shared boiler (review P1/2.1 + 2.3).

Frost-override must only fire the shared boiler for a zone that controls it and
reports a *plausible* cold reading, and must surface the triggering zone. The
off-keepalive must re-assert OFF so a dropped service call cannot leave the
physical boiler stuck on.
"""

from __future__ import annotations

from custom_components.poise.contracts import ZoneRequest
from custom_components.poise.control.hub_aggregate import (
    BoilerState,
    aggregate_boiler_demand,
    step_boiler,
    zone_request_from_data,
)


def _zr(
    *,
    zone_id: str = "z",
    heating: bool = False,
    frost_active: bool = False,
    controls_boiler: bool = True,
    heat_demand: float = 0.0,
    declared_power: float | None = None,
) -> ZoneRequest:
    return ZoneRequest(
        zone_id=zone_id,
        heating=heating,
        hvac_action="heating" if heating else "idle",
        heat_demand=heat_demand,
        comfort_gap=0.0,
        frost_active=frost_active,
        controls_boiler=controls_boiler,
        mono_ts=0.0,
        declared_power=declared_power,
    )


# --- P1/2.1: frost override gating + zone surfacing ------------------------


def test_frost_fires_only_for_controls_boiler_zone() -> None:
    # a freezing zone that does NOT control the boiler must not fire it
    cold_foreign = _zr(zone_id="ac_room", frost_active=True, controls_boiler=False)
    d = aggregate_boiler_demand([cold_foreign])
    assert d.active is False and d.frost_override is False
    assert d.frost_zone_id is None

    # a freezing zone that DOES control the boiler fires it and is surfaced
    cold_own = _zr(zone_id="bath", frost_active=True, controls_boiler=True)
    d2 = aggregate_boiler_demand([cold_own])
    assert d2.active is True and d2.frost_override is True
    assert d2.frost_zone_id == "bath"


def test_cooling_only_cold_zone_does_not_pin_boiler() -> None:
    # mixed set: a cold cooling-only zone + a warm boiler zone -> no demand
    requests = [
        _zr(zone_id="server", frost_active=True, controls_boiler=False),
        _zr(zone_id="living", frost_active=False, controls_boiler=True, heating=False),
    ]
    assert aggregate_boiler_demand(requests).active is False


def test_normal_count_demand_still_works() -> None:
    calling = _zr(zone_id="living", controls_boiler=True, heating=True, heat_demand=1.0)
    d = aggregate_boiler_demand([calling], count_threshold=1)
    assert d.active is True and d.active_count == 1 and d.frost_override is False


# --- P1/2.1: implausible-reading sensor-fault floor ------------------------


def test_implausible_cold_reading_is_not_frost() -> None:
    # a broken sensor reporting -50 C is a fault, not frost
    zr = zone_request_from_data(
        "z",
        {"current_temperature": -50.0, "heating": False},
        controls_boiler=True,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert zr.frost_active is False


def test_plausible_cold_reading_is_frost() -> None:
    zr = zone_request_from_data(
        "z",
        {"current_temperature": 5.0, "heating": False},
        controls_boiler=True,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert zr.frost_active is True
    # and it propagates to a real boiler call via the aggregate
    assert aggregate_boiler_demand([zr]).frost_override is True


def test_warm_room_is_not_frost() -> None:
    zr = zone_request_from_data(
        "z",
        {"current_temperature": 21.0, "heating": False},
        controls_boiler=True,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert zr.frost_active is False


# --- 2.3: symmetric keep-alive (a dropped OFF self-heals) ------------------

_KW = dict(activation_delay_s=0.0, min_on_s=0.0, min_off_s=0.0)


def test_off_keepalive_reasserts_off() -> None:
    # boiler OFF, keepalive elapsed -> re-assert "off" so a missed call self-heals
    state = BoilerState(on=False, last_switch_mono=0.0, last_keepalive_mono=0.0)
    step = step_boiler(state, demand=False, now_mono=100.0, keepalive_s=60.0, **_KW)
    assert step.call == "off"
    assert step.state.last_keepalive_mono == 100.0


def test_on_keepalive_still_reasserts_on() -> None:
    state = BoilerState(on=True, last_switch_mono=0.0, last_keepalive_mono=0.0)
    step = step_boiler(state, demand=True, now_mono=100.0, keepalive_s=60.0, **_KW)
    assert step.call == "on"


def test_keepalive_disabled_emits_no_call() -> None:
    state = BoilerState(on=False, last_switch_mono=0.0, last_keepalive_mono=0.0)
    step = step_boiler(state, demand=False, now_mono=100.0, keepalive_s=0.0, **_KW)
    assert step.call is None


def test_keepalive_holds_within_interval() -> None:
    state = BoilerState(on=False, last_switch_mono=0.0, last_keepalive_mono=90.0)
    step = step_boiler(state, demand=False, now_mono=100.0, keepalive_s=60.0, **_KW)
    assert step.call is None  # only 10 s since last keepalive
