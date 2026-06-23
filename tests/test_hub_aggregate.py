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


def test_parse_service_action_simple_and_with_attr() -> None:
    from custom_components.poise.control.hub_aggregate import parse_service_action

    a = parse_service_action("switch.boiler/switch.turn_on")
    assert a is not None
    assert a.domain == "switch" and a.service == "turn_on"
    assert a.data == {"entity_id": "switch.boiler"}

    b = parse_service_action("climate.b/climate.set_hvac_mode/hvac_mode:heat")
    assert b is not None and b.service == "set_hvac_mode"
    assert b.data == {"entity_id": "climate.b", "hvac_mode": "heat"}


def test_parse_service_action_rejects_malformed() -> None:
    from custom_components.poise.control.hub_aggregate import parse_service_action

    assert parse_service_action(None) is None
    assert parse_service_action("") is None
    assert parse_service_action("switch.boiler") is None  # no service
    assert parse_service_action("boiler/turn_on") is None  # no dots


def test_target_boiler_state_activation_delay_then_on() -> None:
    from custom_components.poise.control.hub_aggregate import target_boiler_state

    # demand true 100s, delay 300 -> not yet on
    assert (
        target_boiler_state(
            True,
            currently_on=False,
            demand_true_since=0.0,
            now_mono=100.0,
            activation_delay_s=300.0,
            last_switch_mono=-1000.0,
            min_on_s=0.0,
            min_off_s=0.0,
        )
        is False
    )
    # demand true 400s -> on
    assert (
        target_boiler_state(
            True,
            currently_on=False,
            demand_true_since=0.0,
            now_mono=400.0,
            activation_delay_s=300.0,
            last_switch_mono=-1000.0,
            min_on_s=0.0,
            min_off_s=0.0,
        )
        is True
    )


def test_target_boiler_state_min_on_holds() -> None:
    from custom_components.poise.control.hub_aggregate import target_boiler_state

    # on, demand gone, but only 60s since switch, min_on 300 -> stay on
    assert (
        target_boiler_state(
            False,
            currently_on=True,
            demand_true_since=None,
            now_mono=60.0,
            activation_delay_s=0.0,
            last_switch_mono=0.0,
            min_on_s=300.0,
            min_off_s=0.0,
        )
        is True
    )


def _heating_zone(zid, *, gap, power, frost=False):
    return ZoneRequest(
        zone_id=zid,
        heating=True,
        hvac_action="heating",
        heat_demand=1.0,
        comfort_gap=gap,
        frost_active=frost,
        controls_boiler=False,
        mono_ts=0.0,
        declared_power=power,
    )


def test_no_shedding_when_within_budget() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_load_shedding

    r = resolve_load_shedding(
        [_heating_zone("a", gap=1.0, power=2.0)], available_power=5.0
    )
    assert r.shed == () and r.freed_power == 0.0


def test_shedding_sheds_nearest_setpoint_first() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_load_shedding

    zones = [
        _heating_zone("far", gap=3.0, power=2.0),
        _heating_zone("near", gap=0.2, power=2.0),
        _heating_zone("mid", gap=1.5, power=2.0),
    ]
    # overload of 3 kW -> shed nearest first ('near'), then next nearest ('mid')
    r = resolve_load_shedding(zones, available_power=-3.0)
    assert r.shed == ("near", "mid") and r.freed_power == 4.0


def test_frost_zone_never_shed() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_load_shedding

    zones = [
        _heating_zone("frost", gap=0.1, power=2.0, frost=True),
        _heating_zone("ok", gap=2.0, power=2.0),
    ]
    r = resolve_load_shedding(zones, available_power=-1.0)
    assert "frost" not in r.shed and r.shed == ("ok",)


def test_group_call_for_heat() -> None:
    from custom_components.poise.control.hub_aggregate import group_call_for_heat

    a = ZoneRequest(
        zone_id="a",
        heating=True,
        hvac_action="heating",
        heat_demand=1.0,
        comfort_gap=1.0,
        frost_active=False,
        controls_boiler=False,
        mono_ts=0.0,
        compressor_group="outdoor1",
    )
    b = ZoneRequest(
        zone_id="b",
        heating=False,
        hvac_action="idle",
        heat_demand=0.0,
        comfort_gap=0.0,
        frost_active=False,
        controls_boiler=False,
        mono_ts=0.0,
        compressor_group="outdoor1",
    )
    c = ZoneRequest(
        zone_id="c",
        heating=False,
        hvac_action="idle",
        heat_demand=0.0,
        comfort_gap=0.0,
        frost_active=False,
        controls_boiler=False,
        mono_ts=0.0,
        compressor_group="outdoor2",
    )
    g = group_call_for_heat([a, b, c])
    assert g == {"outdoor1": True, "outdoor2": False}


def test_frost_override_fires_for_non_optin_zone() -> None:
    # review #2: a freezing zone that is NOT opt-in must still fire the boiler
    from custom_components.poise.control.hub_aggregate import aggregate_boiler_demand

    z = _zone("cold", heating=False, frost=True, controls_boiler=False)
    d = aggregate_boiler_demand([z], count_threshold=1)
    assert d.active is True and d.frost_override is True


def test_shedding_excludes_mould_health_zone() -> None:
    # review #4: a mould/health-floored zone must never be shed
    from custom_components.poise.control.hub_aggregate import resolve_load_shedding

    health = ZoneRequest(
        zone_id="mould",
        heating=True,
        hvac_action="heating",
        heat_demand=1.0,
        comfort_gap=0.1,
        frost_active=False,
        controls_boiler=False,
        mono_ts=0.0,
        declared_power=2.0,
        health_active=True,
    )
    ok = _heating_zone("ok", gap=2.0, power=2.0)
    r = resolve_load_shedding([health, ok], available_power=-1.0)
    assert "mould" not in r.shed and r.shed == ("ok",)


def test_step_boiler_activation_latch_across_ticks() -> None:
    from custom_components.poise.control.hub_aggregate import BoilerState, step_boiler

    st = BoilerState()
    # demand appears at t=0, delay 300 -> no switch yet at t=100
    s1 = step_boiler(
        st,
        demand=True,
        now_mono=0.0,
        activation_delay_s=300.0,
        min_on_s=0.0,
        min_off_s=0.0,
        keepalive_s=0.0,
    )
    assert s1.call is None and s1.state.demand_true_since == 0.0
    s2 = step_boiler(
        s1.state,
        demand=True,
        now_mono=100.0,
        activation_delay_s=300.0,
        min_on_s=0.0,
        min_off_s=0.0,
        keepalive_s=0.0,
    )
    assert s2.call is None and s2.state.on is False
    # at t=400 the latch matured -> switch on
    s3 = step_boiler(
        s2.state,
        demand=True,
        now_mono=400.0,
        activation_delay_s=300.0,
        min_on_s=0.0,
        min_off_s=0.0,
        keepalive_s=0.0,
    )
    assert s3.call == "on" and s3.state.on is True


def test_step_boiler_min_on_holds_then_off() -> None:
    from custom_components.poise.control.hub_aggregate import BoilerState, step_boiler

    on = BoilerState(on=True, last_switch_mono=0.0, demand_true_since=None)
    # demand gone at t=60, min_on 300 -> stays on, no call
    s1 = step_boiler(
        on,
        demand=False,
        now_mono=60.0,
        activation_delay_s=0.0,
        min_on_s=300.0,
        min_off_s=0.0,
        keepalive_s=0.0,
    )
    assert s1.call is None and s1.state.on is True
    # t=400 -> min_on satisfied -> switch off
    s2 = step_boiler(
        s1.state,
        demand=False,
        now_mono=400.0,
        activation_delay_s=0.0,
        min_on_s=300.0,
        min_off_s=0.0,
        keepalive_s=0.0,
    )
    assert s2.call == "off" and s2.state.on is False


def test_step_boiler_keepalive_resends_on() -> None:
    from custom_components.poise.control.hub_aggregate import BoilerState, step_boiler

    on = BoilerState(on=True, last_switch_mono=0.0, last_keepalive_mono=0.0)
    # still on, demand true, keepalive 60 elapsed -> resend "on"
    s = step_boiler(
        on,
        demand=True,
        now_mono=60.0,
        activation_delay_s=0.0,
        min_on_s=0.0,
        min_off_s=0.0,
        keepalive_s=60.0,
    )
    assert s.call == "on" and s.state.last_keepalive_mono == 60.0


def test_step_min_cycle_advances_switch_only_on_change() -> None:
    from custom_components.poise.control.hub_aggregate import step_min_cycle

    on, switch = step_min_cycle(
        prev_on=False,
        prev_switch_mono=-1.0e9,
        demand=True,
        now_mono=500.0,
        min_on_s=300.0,
        min_off_s=300.0,
    )
    assert on is True and switch == 500.0
    # no change -> switch timestamp preserved
    on2, switch2 = step_min_cycle(
        prev_on=True,
        prev_switch_mono=500.0,
        demand=True,
        now_mono=900.0,
        min_on_s=300.0,
        min_off_s=300.0,
    )
    assert on2 is True and switch2 == 500.0


def test_zone_request_frost_derived_from_cold_room() -> None:
    # review #2: frost MUST come from the physical temperature, not the cause
    from custom_components.poise.control.hub_aggregate import zone_request_from_data

    cold = zone_request_from_data(
        "z",
        {"current_temperature": 6.0, "heat_sp": 7.0, "binding_lower_cause": "en16798"},
        controls_boiler=False,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert cold.frost_active is True
    warm = zone_request_from_data(
        "z",
        {
            "current_temperature": 21.0,
            "heat_sp": 21.5,
            "binding_lower_cause": "en16798",
        },
        controls_boiler=False,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert warm.frost_active is False


def test_zone_request_frost_fires_boiler_end_to_end() -> None:
    # the exact scenario review #2 said was broken: cold non-opt-in zone -> demand
    from custom_components.poise.control.hub_aggregate import (
        aggregate_boiler_demand,
        zone_request_from_data,
    )

    z = zone_request_from_data(
        "cold",
        {"current_temperature": 5.0, "heat_sp": 7.0},
        controls_boiler=False,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert aggregate_boiler_demand([z]).active is True


def test_zone_request_health_from_mould_cause() -> None:
    from custom_components.poise.control.hub_aggregate import zone_request_from_data

    z = zone_request_from_data(
        "z",
        {"current_temperature": 19.0, "heat_sp": 20.0, "binding_lower_cause": "mold"},
        controls_boiler=True,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert z.health_active is True and z.frost_active is False


def test_zone_request_demand_gap_and_passthrough() -> None:
    from custom_components.poise.control.hub_aggregate import zone_request_from_data

    z = zone_request_from_data(
        "z",
        {
            "current_temperature": 18.0,
            "heat_sp": 21.0,
            "heating": True,
            "tpi_duty": 0.4,
        },
        controls_boiler=True,
        declared_power=1.5,
        compressor_group="g1",
        flow_temp_request=None,
        source_pref=None,
        mono_ts=7.0,
    )
    assert z.heat_demand == 0.4 and z.comfort_gap == 3.0
    assert z.declared_power == 1.5 and z.compressor_group == "g1" and z.mono_ts == 7.0
    # fall-backs: no duty, not heating
    z2 = zone_request_from_data(
        "z",
        {},
        controls_boiler=False,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )
    assert z2.heat_demand == 0.0 and z2.comfort_gap == 0.0 and z2.frost_active is False


def _flow_zone(zid, *, flow, heating=True):
    return ZoneRequest(
        zone_id=zid,
        heating=heating,
        hvac_action="heating" if heating else "idle",
        heat_demand=1.0 if heating else 0.0,
        comfort_gap=1.0,
        frost_active=False,
        controls_boiler=False,
        mono_ts=0.0,
        flow_temp_request=flow,
    )


def test_flow_highest_request_wins_and_caps() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_flow_temperature

    zones = [_flow_zone("ufh", flow=35.0), _flow_zone("rad", flow=55.0)]
    d = resolve_flow_temperature(zones, current=None, max_flow=60.0, hysteresis=2.0)
    assert d.target == 55.0 and d.requested_max == 55.0 and d.changed is True
    # cap applies
    hot = resolve_flow_temperature(
        [_flow_zone("rad", flow=80.0)], current=None, max_flow=60.0, hysteresis=2.0
    )
    assert hot.target == 60.0


def test_flow_hysteresis_holds_small_changes() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_flow_temperature

    # request 46 while commanding 45, hysteresis 2 -> hold 45 (no hunt)
    hold = resolve_flow_temperature(
        [_flow_zone("a", flow=46.0)], current=45.0, max_flow=60.0, hysteresis=2.0
    )
    assert hold.target == 45.0 and hold.changed is False
    # request 48 -> exceeds band -> move
    move = resolve_flow_temperature(
        [_flow_zone("a", flow=48.0)], current=45.0, max_flow=60.0, hysteresis=2.0
    )
    assert move.target == 48.0 and move.changed is True


def test_flow_demand_gone_releases() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_flow_temperature

    none_heating = [_flow_zone("a", flow=45.0, heating=False)]
    d = resolve_flow_temperature(
        none_heating, current=45.0, max_flow=60.0, hysteresis=2.0
    )
    assert d.target is None and d.changed is True


def _src_zone(zid, *, pref, heating=True):
    return ZoneRequest(
        zone_id=zid,
        heating=heating,
        hvac_action="heating" if heating else "idle",
        heat_demand=1.0 if heating else 0.0,
        comfort_gap=1.0,
        frost_active=False,
        controls_boiler=False,
        mono_ts=0.0,
        source_pref=pref,
    )


def test_source_policy_honours_explicit_and_defaults_auto() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_source_policy

    zones = [
        _src_zone("a", pref="heat_pump"),
        _src_zone("b", pref="radiator"),
        _src_zone("c", pref="auto"),
        _src_zone("d", pref=None),
    ]
    g = resolve_source_policy(zones, default_source="radiator")
    assert g == {"a": "heat_pump", "b": "radiator", "c": "radiator", "d": "radiator"}


def test_source_policy_default_and_skips_idle() -> None:
    from custom_components.poise.control.hub_aggregate import resolve_source_policy

    zones = [
        _src_zone("a", pref="auto"),
        _src_zone("idle", pref="radiator", heating=False),
    ]
    g = resolve_source_policy(zones, default_source="heat_pump")
    assert g == {"a": "heat_pump"}  # idle zone excluded, auto -> default
