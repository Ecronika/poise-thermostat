"""Phase 8 (S1) — pure tests for ``diagnostics/`` (shadows + collector).

Pins the composition wrappers extracted from the coordinator's finalize/
climate segments (plan 5.6 / SHADOWS-EXTRAKT) against the historical inline
semantics:

* the neutral shadow fallback vs. the healthy assembly differ by EXACTLY the
  two ``compressor_gate_*`` keys (phase-0 finding 3: the available key set
  shrinks by two on a shadow failure),
* ``evaluate_cover_shadow`` dispatches its kernels ONLY through the injected
  ``*_fn`` parameters (the coordinator resolves them from its module globals
  at call time — the fault-injection patch surface),
* the F9 dt-cap helper is bit-identical to the four historical inline
  computations,
* ``compose_climate_band``/``build_outcome_diag`` reproduce the historical
  dict assemblies (key ORDER included — the published ``coordinator.data``
  order is observable),
* ``DiagnosticsCollector.safe_collect`` swallows any failure into the
  UNTOUCHED defaults object and logs on the injected channel with the exact
  historical text/level/exc_info.

Hass-free (py310-clean); this suite is the pure-coverage obligation for the
new ``diagnostics``-package modules.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from custom_components.poise.comfort.en16798 import Category
from custom_components.poise.comfort.fan_circulation import (
    FAN_ONLY_LOW,
    fan_circulation,
)
from custom_components.poise.comfort.fan_cooling import fan_cool_setpoint, fan_velocity
from custom_components.poise.comfort.free_running import free_running_widen
from custom_components.poise.comfort.humidity import (
    HumidityDecision,
    rh_high_for_category,
)
from custom_components.poise.comfort.pmv import pmv_ppd, seasonal_clo
from custom_components.poise.comfort.thermal_shock import AdaptiveCool
from custom_components.poise.control.cover_shading import (
    predict_peak_operative,
    shading_target_position,
)
from custom_components.poise.control.hdh_savings import HdhConfig, HdhSavings
from custom_components.poise.control.mpc_shadow import MpcShadow
from custom_components.poise.control.outcome_scoring import OutcomeStats
from custom_components.poise.control.pi_shadow import PiShadow
from custom_components.poise.control.reference_offset import (
    compensated_setpoint,
    update_offset,
)
from custom_components.poise.control.regulation_quality import RegulationQuality
from custom_components.poise.control.tpi_shadow import TpiShadow
from custom_components.poise.diagnostics import async_get_config_entry_diagnostics
from custom_components.poise.diagnostics.collector import DiagnosticsCollector
from custom_components.poise.diagnostics.entry import (
    async_get_config_entry_diagnostics as entry_hook,
)
from custom_components.poise.diagnostics.shadows import (
    assemble_shadow_objs,
    build_outcome_diag,
    capped_elapsed_min,
    compose_climate_band,
    evaluate_cover_shadow,
    evaluate_multi_shadow,
    neutral_shadow_objs,
)
from custom_components.poise.estimation.tau_settle import (
    settle_confidence,
    update_settle,
)
from custom_components.poise.multi import lifecycle as _lifecycle
from custom_components.poise.multi.model import Direction
from custom_components.poise.multi.resolvers import DeviceRuntime
from custom_components.poise.multi.shadow import ThermalShadow, evaluate_thermal_shadow

# ---------------------------------------------------------------------------
# package layout
# ---------------------------------------------------------------------------


def test_package_reexports_the_diagnostics_platform_hook() -> None:
    """The package shadows the former ``diagnostics.py`` module — HA resolves
    ``custom_components.poise.diagnostics`` as the diagnostics platform, so
    the config-entry hook must be importable from the package root and be the
    IDENTICAL function object as the relocated ``entry`` module's."""
    assert async_get_config_entry_diagnostics is entry_hook


# ---------------------------------------------------------------------------
# neutral fallback vs healthy assembly (phase-0 finding 3)
# ---------------------------------------------------------------------------

_NEUTRAL_EXPECTED = {
    "pi_active": False,
    "pi_setpoint": None,
    "pi_offset": None,
    "multi_active_source": None,
    "multi_reason": "shadow_error",
    "multi_severity": "info",
    "multi_blocked": [],
    "multi_min_off_remaining": 0,
    "multi_device_health": "ok",
    "tpi_active": False,
    "tpi_duty": None,
    "tpi_valve_percent": None,
    "mpc_active": False,
    "mpc_power": None,
    "mpc_weight": None,
    "mpc_setpoint": None,
    "mpc_regime": "hold",
}


def test_neutral_shadow_objs_exact_payload_and_freshness() -> None:
    objs = neutral_shadow_objs("ok")
    assert objs == _NEUTRAL_EXPECTED
    # the degraded payload must NOT carry the compressor_gate_* keys
    assert "compressor_gate_would_block" not in objs
    assert "compressor_mode_hold_remaining" not in objs
    # health is the caller's (pre-fold) lifecycle health, passed through
    assert neutral_shadow_objs("unavailable")["multi_device_health"] == "unavailable"
    # fresh dict (and fresh mutable list) per call — never a shared literal
    again = neutral_shadow_objs("ok")
    assert again is not objs
    assert again["multi_blocked"] is not objs["multi_blocked"]


def _assembled(comp_block: str | None) -> dict[str, object]:
    life = _lifecycle.observe(
        _lifecycle.DeviceLifecycle(),
        conditioning=True,
        mode="heat",
        now=1_000.0,
        health="ok",
    )
    return assemble_shadow_objs(
        pi=PiShadow(active=True, setpoint=21.4, offset=0.4, next_acc=1.2),
        multi_shadow=ThermalShadow(
            active_source="climate.trv",
            reason="selected",
            severity="info",
            blocked=("cycle_lock",),
            capabilities=("thermal:heat",),
        ),
        tpi=TpiShadow(active=True, duty=0.62, valve_percent=62.0),
        shadow=MpcShadow(
            active=True, power=0.5, weight=0.7, setpoint=21.0, regime="cruise"
        ),
        lifecycle=life,
        now_wall=1_030.0,
        multi_policy=_lifecycle.LifecyclePolicy(),
        comp_pol=_lifecycle.LifecyclePolicy(min_off_s=300, min_mode_hold_s=600),
        comp_block=comp_block,
        min_off_remaining_fn=_lifecycle.min_off_remaining,
        mode_hold_remaining_fn=_lifecycle.mode_hold_remaining,
    )


def test_assemble_shadow_objs_is_neutral_plus_exactly_two_compressor_keys() -> None:
    """The healthy assembly's key set == neutral fallback + the two
    ``compressor_gate_*`` keys — the phase-0 pinned shrink-by-two."""
    objs = _assembled("min_off")
    assert set(objs) == set(_NEUTRAL_EXPECTED) | {
        "compressor_gate_would_block",
        "compressor_mode_hold_remaining",
    }


def test_assemble_shadow_objs_wires_values_and_lifecycle_fns() -> None:
    objs = _assembled("min_off")
    assert objs["pi_active"] is True
    assert objs["pi_setpoint"] == 21.4
    assert objs["multi_active_source"] == "climate.trv"
    assert objs["multi_blocked"] == ["cycle_lock"]  # tuple -> list, like inline
    assert objs["multi_device_health"] == "ok"
    assert objs["compressor_gate_would_block"] == "min_off"
    # the remaining-time kernels run against (lifecycle, now_wall, policy):
    # mode changed at 1000.0, hold 600 s, now 1030.0 -> round(570.0)
    assert objs["compressor_mode_hold_remaining"] == 570
    assert objs["tpi_duty"] == 0.62
    assert objs["mpc_regime"] == "cruise"


def test_assemble_shadow_objs_comp_block_none_becomes_empty_string() -> None:
    assert _assembled(None)["compressor_gate_would_block"] == ""


def test_assemble_shadow_objs_dispatches_via_injected_fns() -> None:
    """The lifecycle remaining-time kernels must ONLY be reached through the
    injected callables (the coordinator resolves ``_lifecycle.*`` from its
    module globals at call time — the patchable dispatch)."""
    calls: list[tuple[str, object, float, object]] = []

    def fake_min_off(state: object, now: float, policy: object) -> float:
        calls.append(("min_off", state, now, policy))
        return 12.6

    def fake_mode_hold(state: object, now: float, policy: object) -> float:
        calls.append(("mode_hold", state, now, policy))
        return 33.4

    life = _lifecycle.DeviceLifecycle()
    pol_multi = _lifecycle.LifecyclePolicy()
    pol_comp = _lifecycle.LifecyclePolicy(min_off_s=1.0)
    objs = assemble_shadow_objs(
        pi=PiShadow(active=False),
        multi_shadow=ThermalShadow(
            active_source=None,
            reason="none",
            severity="info",
            blocked=(),
            capabilities=(),
        ),
        tpi=TpiShadow(active=False),
        shadow=MpcShadow(active=False),
        lifecycle=life,
        now_wall=7.0,
        multi_policy=pol_multi,
        comp_pol=pol_comp,
        comp_block=None,
        min_off_remaining_fn=fake_min_off,
        mode_hold_remaining_fn=fake_mode_hold,
    )
    assert objs["multi_min_off_remaining"] == 13  # round(12.6)
    assert objs["compressor_mode_hold_remaining"] == 33  # round(33.4)
    assert calls == [
        ("min_off", life, 7.0, pol_multi),
        ("mode_hold", life, 7.0, pol_comp),
    ]


# ---------------------------------------------------------------------------
# cover shadow (ADR-0043) + binding classification
# ---------------------------------------------------------------------------


def _cover(
    *,
    mold_min: float | None,
    predict_fn: object = None,
    shading_fn: object = None,
) -> tuple[float, int, str, str]:
    return evaluate_cover_shadow(
        operative=24.0,
        t_out_eff=30.0,
        q_solar=0.8,
        cool_sp=26.0,
        heat_sp=21.0,
        mold_min=mold_min,
        model=SimpleNamespace(alpha=0.5, beta_s=3.0),  # only .alpha/.beta_s read
        identified=True,
        temperature_std=0.1,
        predict_peak_operative_fn=predict_fn or predict_peak_operative,
        shading_target_position_fn=shading_fn or shading_target_position,
    )


def test_evaluate_cover_shadow_matches_the_historical_inline_composition() -> None:
    """Equivalence anchor: the wrapper must reproduce the exact inline result
    of the two kernels with the historical argument choreography."""
    expected_peak = predict_peak_operative(
        24.0,
        30.0,
        [0.8] * 36,
        alpha=0.5,
        beta_s=3.0,
        dt_h=5.0 / 60.0,
        confident=True,
    )
    expected_pos, expected_reason = shading_target_position(
        peak=expected_peak, t_upper=26.0, current_position=0.0, oriented_q=0.8
    )
    assert _cover(mold_min=None) == (
        expected_peak,
        expected_pos,
        expected_reason,
        "en16798",
    )


def test_evaluate_cover_shadow_kernel_choreography_via_injected_fns() -> None:
    seen: dict[str, object] = {}

    def fake_predict(
        t_now: float,
        t_out: float,
        q_series: list[float],
        *,
        alpha: float,
        beta_s: float,
        dt_h: float,
        confident: bool,
    ) -> float:
        seen["predict"] = (t_now, t_out, q_series, alpha, beta_s, dt_h, confident)
        return 27.3

    def fake_shading(
        *, peak: float, t_upper: float, current_position: float, oriented_q: float
    ) -> tuple[int, str]:
        seen["shading"] = (peak, t_upper, current_position, oriented_q)
        return 40, "deploy"

    peak, pos, reason, binding = _cover(
        mold_min=None, predict_fn=fake_predict, shading_fn=fake_shading
    )
    assert (peak, pos, reason, binding) == (27.3, 40, "deploy", "en16798")
    # historical argument choreography: 36-slot flat solar series, 5-min ZOH
    # step, confidence gate ``identified and std < 0.5``
    assert seen["predict"] == (24.0, 30.0, [0.8] * 36, 0.5, 3.0, 5.0 / 60.0, True)
    # the shading decision sees the FORECAST peak, open cover, oriented q
    assert seen["shading"] == (27.3, 26.0, 0.0, 0.8)


def test_evaluate_cover_shadow_confident_gate_needs_low_std() -> None:
    def fake_predict(*args: object, **kwargs: object) -> float:
        assert kwargs["confident"] is False  # std 0.9 >= 0.5 kills the gate
        return 24.0

    evaluate_cover_shadow(
        operative=24.0,
        t_out_eff=30.0,
        q_solar=0.0,
        cool_sp=26.0,
        heat_sp=21.0,
        mold_min=None,
        model=SimpleNamespace(alpha=0.5, beta_s=3.0),
        identified=True,
        temperature_std=0.9,
        predict_peak_operative_fn=fake_predict,
        shading_target_position_fn=shading_target_position,
    )


@pytest.mark.parametrize(
    ("mold_min", "expected"),
    [
        (None, "en16798"),
        (0.0, "en16798"),  # falsy floor: historical ``mold_min and …`` gate
        (20.9, "en16798"),  # below heat_sp
        (21.0, "mold"),  # >= heat_sp binds mould
        (23.5, "mold"),
    ],
)
def test_evaluate_cover_shadow_binding_classification(
    mold_min: float | None, expected: str
) -> None:
    assert _cover(mold_min=mold_min)[3] == expected


# ---------------------------------------------------------------------------
# F9 dt cap (four historical inline duplicates)
# ---------------------------------------------------------------------------


def test_capped_elapsed_min_first_observation_books_one_tick() -> None:
    assert capped_elapsed_min(None, 1234.5, 1.0) == 1.0


@pytest.mark.parametrize(
    ("last", "now", "tick_min"),
    [
        (100.0, 160.0, 1.0),  # exactly one tick
        (100.0, 130.0, 1.0),  # event-driven half tick
        (100.0, 1000.0, 1.0),  # masked gap -> capped at 2 ticks
        (200.0, 100.0, 1.0),  # backwards clock -> floored at 0
        (0.0, 90.0, 0.75),  # non-default tick length
    ],
)
def test_capped_elapsed_min_bit_identical_to_inline_formula(
    last: float, now: float, tick_min: float
) -> None:
    inline = min(max((now - last) / 60.0, 0.0), 2.0 * tick_min)
    assert capped_elapsed_min(last, now, tick_min) == inline


# ---------------------------------------------------------------------------
# thermal-arbitration shadow wrapper (ADR-0046)
# ---------------------------------------------------------------------------


def test_evaluate_multi_shadow_builds_snapshot_and_demand() -> None:
    seen: dict[str, object] = {}

    def fake_eval(
        snapshot: object, demand: object, *, runtime: object = None
    ) -> ThermalShadow:
        seen["snapshot"] = snapshot
        seen["demand"] = demand
        seen["runtime"] = runtime
        return ThermalShadow(
            active_source=None,
            reason="none",
            severity="info",
            blocked=(),
            capabilities=(),
        )

    rt = DeviceRuntime()
    evaluate_multi_shadow(
        entity_id="climate.trv",
        hvac_modes=["heat", 5, None],  # raw attribute list -> str-coerced tuple
        available=True,
        direction=Direction.HEAT,
        target=21.5,
        runtime=rt,
        evaluate_thermal_shadow_fn=fake_eval,
    )
    snap = seen["snapshot"]
    assert snap.entity_id == "climate.trv"  # type: ignore[attr-defined]
    assert snap.domain == "climate"  # type: ignore[attr-defined]
    assert snap.hvac_modes == ("heat", "5", "None")  # type: ignore[attr-defined]
    assert snap.available is True  # type: ignore[attr-defined]
    demand = seen["demand"]
    assert demand.direction is Direction.HEAT  # type: ignore[attr-defined]
    assert demand.target_c == 21.5  # type: ignore[attr-defined]
    assert seen["runtime"] is rt


def test_evaluate_multi_shadow_with_real_kernel_selects_the_actuator() -> None:
    shadow = evaluate_multi_shadow(
        entity_id="climate.trv",
        hvac_modes=["heat", "off"],
        available=True,
        direction=Direction.HEAT,
        target=21.5,
        runtime=DeviceRuntime(),
        evaluate_thermal_shadow_fn=evaluate_thermal_shadow,
    )
    assert shadow.active_source == "climate.trv"


# ---------------------------------------------------------------------------
# climate-band composition (legacy climate domain, finding 11b)
# ---------------------------------------------------------------------------

_CLIMATE_KEY_ORDER = [
    "cool_sp_eff",
    "cool_sp_active",
    "cool_raised",
    "cool_raise_reason",
    "en_cool_upper",
    "humidity_action",
    "dry_active",
    "humidity_reason",
    "abs_humidity_gkg",
    "rh_high_used",
    "fr_active",
    "fr_heat_sp",
    "fr_cool_sp",
    "fr_adaptive_lower",
    "fr_adaptive_upper",
    "fan_circ_shadow",
    "fan_ce_k",
    "fan_cool_sp_shadow",
    "fan_velocity_ms",
    "fan_circ_reason",
    "occupied",
    "presence_level",
    "room_absent_min",
    "home_present",
    "pmv",
    "ppd",
    "pmv_category",
]


def _climate_band(
    *,
    cool_ac: AdaptiveCool | None,
    hvac_modes: list[str],
    has_fan_modes: bool = False,
    fan_mode: str | None = None,
    hvac_action: str | None = None,
    rh: float | None = 55.0,
    abs_w: float | None = 8.34,
) -> dict[str, object]:
    return compose_climate_band(
        heat_sp=21.0,
        cool_sp=26.0,
        room=22.0,
        room_decide=22.0,
        t_rm_eff=18.0,
        t_mrt=22.5,
        rh=rh,
        eff_cool=26.5,
        mode="idle",
        window_open=False,
        occupied=True,
        presence_level="present",
        absent_min=3.21,
        home_present=True,
        category=Category("II"),
        cool_hard_cap=29.0,
        cool_ac=cool_ac,
        hum=HumidityDecision(action="idle", dry_active=False, reason="rh_ok"),
        abs_humidity_gkg=abs_w,
        hvac_modes=hvac_modes,
        has_fan_modes=has_fan_modes,
        fan_mode=fan_mode,
        hvac_action=hvac_action,
    )


def test_compose_climate_band_key_order_is_the_published_contract() -> None:
    diag = _climate_band(cool_ac=None, hvac_modes=["cool", "heat", "off"])
    assert list(diag.keys()) == _CLIMATE_KEY_ORDER


def test_compose_climate_band_matches_the_inline_kernels() -> None:
    """Equivalence anchor: every published value must equal the historical
    inline composition of the comfort kernels over the same inputs."""
    diag = _climate_band(
        cool_ac=None,
        hvac_modes=["cool", "fan_only", "off"],
        fan_mode="low",
        hvac_action="fan",
    )
    fr = free_running_widen(
        heat_op=21.0, cool_op=26.0, room=22.0, t_rm=18.0, category=Category("II")
    )
    fan = fan_circulation(
        occupied=True,
        in_deadband=True,  # 21.0 <= 22.0 <= 26.5
        active_mode="idle",
        window_open=False,
        can_recirculate=True,  # "fan_only" advertised
        policy=FAN_ONLY_LOW,
        presence_optin=True,
    )
    fan_v = fan_velocity(fan_mode="low", hvac_action="fan", can_recirculate=True)
    fan_cool_sp, fan_ce = fan_cool_setpoint(
        cool_sp=26.5, air_speed=fan_v, fan_running=True, upper_cap=29.0
    )
    pmv = pmv_ppd(
        t_air=22.0, t_mrt=22.5, rh=55.0, velocity=fan_v, clo=seasonal_clo(18.0)
    )
    assert diag["cool_sp_eff"] == 26.0  # no cool_ac -> falls back to cool_sp
    assert diag["cool_sp_active"] == 26.5
    assert diag["cool_raised"] is False
    assert diag["cool_raise_reason"] == "n/a"
    assert diag["en_cool_upper"] == 0.0
    assert diag["humidity_action"] == "idle"
    assert diag["dry_active"] is False
    assert diag["humidity_reason"] == "rh_ok"
    assert diag["abs_humidity_gkg"] == 8.3  # round(8.34, 1)
    assert diag["rh_high_used"] == rh_high_for_category(Category("II"))
    assert diag["fr_active"] == fr.active
    assert diag["fr_heat_sp"] == round(fr.heat_op, 1)
    assert diag["fr_cool_sp"] == round(fr.cool_op, 1)
    assert diag["fr_adaptive_lower"] == round(fr.adaptive_lower, 1)
    assert diag["fr_adaptive_upper"] == round(fr.adaptive_upper, 1)
    assert diag["fan_circ_shadow"] == fan.action
    assert diag["fan_ce_k"] == fan_ce
    assert diag["fan_cool_sp_shadow"] == fan_cool_sp
    assert diag["fan_velocity_ms"] == round(fan_v, 2)
    assert diag["fan_circ_reason"] == fan.reason
    assert diag["occupied"] is True
    assert diag["presence_level"] == "present"
    assert diag["room_absent_min"] == 3.2  # round(3.21, 1)
    assert diag["home_present"] is True
    assert diag["pmv"] == pmv.pmv
    assert diag["ppd"] == pmv.ppd
    assert diag["pmv_category"] == pmv.category


def test_compose_climate_band_cool_ac_fields_pass_through() -> None:
    ac = AdaptiveCool(
        cool_sp_eff=27.5, raised=True, en_upper=28.1, upper_clamp=28.1, reason="hot_day"
    )
    diag = _climate_band(cool_ac=ac, hvac_modes=["cool", "off"])
    assert diag["cool_sp_eff"] == 27.5
    assert diag["cool_raised"] is True
    assert diag["cool_raise_reason"] == "hot_day"
    assert diag["en_cool_upper"] == 28.1


def test_compose_climate_band_recirc_via_fan_modes_attribute() -> None:
    """No fan_only hvac mode, but a fan_modes attribute -> still recirc-capable
    (the historical ``or bool(attributes.get("fan_modes"))`` arm)."""
    no_fan = _climate_band(cool_ac=None, hvac_modes=["cool", "off"])
    assert no_fan["fan_circ_reason"] == "no_fan_capability"
    with_attr = _climate_band(
        cool_ac=None, hvac_modes=["cool", "off"], has_fan_modes=True
    )
    assert with_attr["fan_circ_reason"] != "no_fan_capability"


def test_compose_climate_band_none_defaults_for_rh_and_abs_humidity() -> None:
    diag = _climate_band(cool_ac=None, hvac_modes=["cool", "off"], rh=None, abs_w=None)
    assert diag["abs_humidity_gkg"] is None
    # PMV falls back to 50 % RH — identical to computing the kernel directly
    pmv = pmv_ppd(
        t_air=22.0,
        t_mrt=22.5,
        rh=50.0,
        velocity=fan_velocity(fan_mode=None, hvac_action=None, can_recirculate=False),
        clo=seasonal_clo(18.0),
    )
    assert diag["pmv"] == pmv.pmv


# ---------------------------------------------------------------------------
# outcome_diag assembly (second boundary's healthy payload)
# ---------------------------------------------------------------------------

_OUTCOME_KEY_ORDER = [
    "outcome_last_score",
    "outcome_ts_avg",
    "outcome_obs_avg",
    "outcome_n",
    "savings_kwh_month",
    "savings_eur_month",
    "savings_pct",
    "ca_deviation_k",
    "ca_time_in_band",
    "ca_cycles_per_h",
    "ca_minutes",
    "ref_offset",
    "ref_offset_dev",
    "ref_offset_trusted",
    "ref_offset_conditioning",
    "tau_confidence",
    "tau_settled",
    "tau_settle_minutes",
    "cool_sp_compensated",
]


def test_build_outcome_diag_fresh_state_and_key_order() -> None:
    diag = build_outcome_diag(
        outcome_stats=OutcomeStats(),
        hdh=HdhSavings(),
        hdh_cfg=HdhConfig(),
        regq=RegulationQuality(),
        ref_offset=None,
        ref_conditioning=False,
        tau_settle=None,
        eff_cool=26.0,
    )
    assert list(diag.keys()) == _OUTCOME_KEY_ORDER
    # None-state degradations: every ref_*/tau_* detail key stays None
    assert diag["outcome_last_score"] is None
    assert diag["outcome_n"] == 0
    assert diag["savings_kwh_month"] == 0.0
    assert diag["ref_offset"] is None
    assert diag["ref_offset_dev"] is None
    assert diag["ref_offset_trusted"] is None
    assert diag["ref_offset_conditioning"] is False
    assert diag["tau_confidence"] == round(settle_confidence(None), 3)
    assert diag["tau_settled"] is None
    assert diag["tau_settle_minutes"] is None
    assert diag["cool_sp_compensated"] is None


def test_build_outcome_diag_matches_the_inline_assembly_on_live_state() -> None:
    stats = OutcomeStats().observe(0.8, "ts").observe(0.6, "obs")
    regq = RegulationQuality().observe(
        room=21.4, heat_sp=21.0, cool_sp=26.0, mode="heat", dt_min=1.0
    )
    ref = update_offset(
        None, actuator_temp=23.0, room_temp=21.0, dt_min=1.0, conditioning=True
    )
    tau = update_settle(None, alpha=0.2, dt_min=1.0, learn_active=True)
    hdh = HdhSavings()
    cfg = HdhConfig(annual_kwh=10_000.0, price_eur_kwh=0.25)
    diag = build_outcome_diag(
        outcome_stats=stats,
        hdh=hdh,
        hdh_cfg=cfg,
        regq=regq,
        ref_offset=ref,
        ref_conditioning=True,
        tau_settle=tau,
        eff_cool=26.0,
    )
    rep = hdh.report(cfg)
    assert diag["outcome_last_score"] == stats.last_score
    assert diag["outcome_ts_avg"] == stats.ts_avg
    assert diag["outcome_obs_avg"] == stats.obs_avg
    assert diag["outcome_n"] == stats.ts_n + stats.obs_n
    assert diag["savings_kwh_month"] == rep["kwh"]
    assert diag["savings_eur_month"] == rep["eur"]
    assert diag["savings_pct"] == rep["pct"]
    assert diag["ca_deviation_k"] == round(regq.deviation_k, 3)
    assert diag["ca_time_in_band"] == regq.time_in_band_pct
    assert diag["ca_cycles_per_h"] == round(regq.cycles_per_hour, 2)
    assert diag["ca_minutes"] == round(regq.minutes, 0)
    assert ref is not None
    assert diag["ref_offset"] == round(ref.offset, 2)
    assert diag["ref_offset_dev"] == round(ref.deviation, 2)
    assert diag["ref_offset_trusted"] == ref.trusted
    assert diag["ref_offset_conditioning"] is True
    assert diag["tau_confidence"] == round(settle_confidence(tau), 3)
    assert diag["tau_settled"] == tau.settled
    assert diag["tau_settle_minutes"] == round(tau.minutes, 0)
    assert diag["cool_sp_compensated"] == compensated_setpoint(26.0, ref, enabled=True)


# ---------------------------------------------------------------------------
# DiagnosticsCollector — the ONE broad boundary (plan 5.6)
# ---------------------------------------------------------------------------


def test_safe_collect_success_returns_collect_result_untouched() -> None:
    collector = DiagnosticsCollector(logging.getLogger("poise.test.collector"))
    payload = {"outcome_n": 3}
    defaults = {"outcome_n": 0}
    result = collector.safe_collect(lambda: payload, defaults)
    assert result is payload  # replace-on-success, never merged
    assert defaults == {"outcome_n": 0}  # defaults never mutated


def test_safe_collect_failure_returns_the_same_defaults_object_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Degradation semantics: any exception inside the boundary swallows into
    the UNTOUCHED defaults object; one DEBUG record with the exact historical
    text + traceback on the INJECTED channel (5A lesson: the channel is
    behaviour — the coordinator passes its own logger)."""
    channel = "custom_components.poise.coordinator"
    collector = DiagnosticsCollector(logging.getLogger(channel))
    defaults = {"outcome_n": 0}
    partial: list[str] = []

    def failing_collect() -> dict[str, object]:
        partial.append("fold-1 ran")  # folds BEFORE the raise stay applied
        raise RuntimeError("injected fold failure")

    with caplog.at_level(logging.DEBUG, logger=channel):
        result = collector.safe_collect(failing_collect, defaults)
    assert result is defaults
    assert partial == ["fold-1 ran"]
    records = [
        r
        for r in caplog.records
        if r.getMessage() == "Poise outcome/savings diagnostics failed"
    ]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].name == channel
    assert records[0].exc_info is not None  # exc_info=True: traceback attached


def test_safe_collect_swallows_non_runtime_errors_too() -> None:
    collector = DiagnosticsCollector(logging.getLogger("poise.test.collector"))
    defaults: dict[str, object] = {}

    def raising() -> dict[str, object]:
        raise KeyError("kwh")  # e.g. a malformed report dict

    assert collector.safe_collect(raising, defaults) is defaults
