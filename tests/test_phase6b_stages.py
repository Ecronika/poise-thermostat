"""Phase-6b S2 pure smoke tests for the moved stage implementations.

The S2 relocation moved the pure stage bodies out of ``coordinator.py`` into
``control/tick_pipeline.py`` with ``ZoneRuntime`` (``runtime/zone_runtime.py``)
delegating, and ``commit_execution``/``teardown_hold``/``mark_actuated``/
``restore``/``seed_ekf_cold_start`` onto the runtime itself.  Behavioural
equivalence is pinned by the (unchanged) phase-0 + integration suites; THIS
module makes the moved code exercisable by the HA-free py310 gate — every
moved stage runs at least once against minimal state groups + ``TickInputs``
and asserts its result type and core fields, which also keeps the two new
modules inside the pure-core 85 % coverage aggregate (pyproject omit list
excludes neither ``runtime/*`` nor ``control/*``).

Injection contracts exercised here on purpose:

* the patch-surface callables (``is_frozen``/``ingest_temperature``/
  ``effective_window_open``/``psychro_dewpoint``/``comfort_decide``) are
  per-call parameters — a swapped callable must take effect, mirroring the
  coordinator-module ``unittest.mock.patch`` dispatch;
* the injected logger carries the swallow-boundary records;
* ``set_mpc_params`` receives the retuned ``MpcParams`` (the one
  adapter-owned mutation of the observe stage);
* ``restore``'s F7 recompute evaluates the switchpoint callable only under
  today's exact condition.
"""

from __future__ import annotations

import logging
from typing import Any

from custom_components.poise.clock import ManualClock
from custom_components.poise.comfort.dual_setpoint import ComfortDecision
from custom_components.poise.comfort.dual_setpoint import decide as comfort_decide
from custom_components.poise.comfort.en16798 import Category
from custom_components.poise.comfort.presence import PresenceLevel
from custom_components.poise.comfort.schedule import ComfortSchedule, ComfortWindow
from custom_components.poise.const import (
    SETPOINT_ADOPT_ECHO_WINDOW_S,
)
from custom_components.poise.control.override import setpoint_adopt_reason
from custom_components.poise.control.window_auto import (
    WindowAutoConfig,
    effective_window_open,
)
from custom_components.poise.estimation.psychrometrics import (
    dewpoint as psychro_dewpoint,
)
from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.ingestion import ingest_temperature
from custom_components.poise.persistence.codec import decode as codec_decode
from custom_components.poise.runtime.tick_inputs import (
    ActuatorCapabilitySnapshot,
    BinarySensorSnapshot,
    DeviceGuardSnapshot,
    PresenceSnapshot,
    SensorValue,
    TickInputs,
)
from custom_components.poise.runtime.tick_result import (
    ActuatorPlan,
    ClimateBandResult,
    CommitResult,
    EffectExecution,
    EndHold,
    ExecutionReport,
    FinalizeContext,
    HoldRoutingResult,
    IngestResult,
    IntentsResult,
    ModeAdoptionResult,
    ModeNudgeResult,
    ModeResolutionResult,
    ObservationResult,
    OperativeResult,
    PreparedState,
    PresenceLevelResult,
    SafetyFloorsResult,
    ScheduleGateResult,
    SchedulePresenceResult,
    SetpointObservation,
    TickStageError,
    WriteTargetResult,
)
from custom_components.poise.runtime.zone_runtime import ZoneRuntime
from custom_components.poise.safety.sensor_watchdog import is_frozen

_LOG = logging.getLogger("tests.phase6b_stages")

NOW = 3600.0


def _runtime() -> ZoneRuntime:
    return ZoneRuntime(ManualClock(10_000.0))


def _inputs(**over: Any) -> TickInputs:
    base: dict[str, Any] = {
        "now_mono": NOW,
        "now_wall": 1_750_000_000.0,
        "local_minute": 600,
        "local_day_ordinal": 738_000,
        "sun_elevation": None,
        "room": SensorValue(21.0, age_s=10.0, entity_id="sensor.room"),
        "outdoor": SensorValue(5.0),
        "humidity": SensorValue(50.0),
        "trm": SensorValue(None),
        "mrt": SensorValue(None),
        "irradiance": SensorValue(None),
        "windows": (),
        "actuator": ActuatorCapabilitySnapshot(
            state="heat", hvac_modes=("heat", "off"), max_temp=30.0
        ),
        "device_guards": DeviceGuardSnapshot(
            sched_active=False,
            fault_active=False,
            battery=None,
            adaptive_mode=None,
            ext_temp_number=None,
        ),
    }
    base.update(over)
    return TickInputs(**base)


def _stage_ingest(rt: ZoneRuntime, inputs: TickInputs, **over: Any) -> IngestResult:
    kwargs: dict[str, Any] = {
        "entry_id": "e1",
        "temp_entity": "sensor.room",
        "actuator_entity": "climate.trv",
        "sched_entity": None,
        "adaptive_mode_entity": None,
        "fault_entity": None,
        "battery_entity": None,
        "is_frozen_fn": is_frozen,
        "ingest_temperature_fn": ingest_temperature,
    }
    kwargs.update(over)
    return rt.stage_ingest(inputs, inputs.room.value, **kwargs)


def _stage_observe(
    rt: ZoneRuntime, inputs: TickInputs, ing: IngestResult, **over: Any
) -> ObservationResult:
    kwargs: dict[str, Any] = {
        "entry_id": "e1",
        "windows": [],
        "actuator_entity": "climate.trv",
        "window_auto_cfg": WindowAutoConfig(),
        "adaptive_cool_cfg": "auto",
        "dynamics_override": None,
        "effective_window_open_fn": effective_window_open,
        "set_mpc_params": lambda params: None,
        "logger": _LOG,
    }
    kwargs.update(over)
    return rt.stage_observe(inputs, ing, **kwargs)


def _wt(**over: Any) -> WriteTargetResult:
    base: dict[str, Any] = {
        "act_state": None,
        "actuator_online": True,
        "cool_ac": None,
        "idle_park_mode": None,
        "eff_cool": 26.0,
        "target": 21.5,
        "mode": "heat",
        "norm_binding": None,
        "binding_precedence": None,
        "override_clamped": False,
    }
    base.update(over)
    return WriteTargetResult(**base)


def _routing(**over: Any) -> HoldRoutingResult:
    base: dict[str, Any] = {
        "own_change": False,
        "off_held": False,
        "hold_resumed": False,
        "mode_adopt_reason": "",
        "sp_adopt_reason": "",
    }
    base.update(over)
    return HoldRoutingResult(**base)


def _nudge(**over: Any) -> ModeNudgeResult:
    base: dict[str, Any] = {
        "mode_nudge": False,
        "guard_block": None,
        "mode_nudge_blocked": "",
    }
    base.update(over)
    return ModeNudgeResult(**base)


def _mode_res(rt: ZoneRuntime, ing: IngestResult, obs: ObservationResult, **over: Any):
    kwargs: dict[str, Any] = {
        "cool_min_outdoor": 18.0,
        "cool_lockout_enabled": True,
        "heat_max_outdoor": 18.0,
        "heat_lockout_enabled": False,
        "compressor_guard": "auto",
        "comp_min_off_opt": None,
        "comp_mode_hold_opt": None,
    }
    kwargs.update(over)
    op = OperativeResult(
        ext_num=None,
        ext_ok=False,
        operative_active=False,
        room_decide=ing.room,
        t_mrt_decide=None,
    )
    band = ClimateBandResult(climate_diag={}, hum_action="idle")
    return rt.stage_mode_resolution(ing, obs, op, _wt(), band, **kwargs)


# ---------------------------------------------------------------------------
# stage_ingest
# ---------------------------------------------------------------------------


def test_stage_ingest_happy_path_and_health_order() -> None:
    rt = _runtime()
    ing = _stage_ingest(rt, _inputs())
    assert isinstance(ing, IngestResult)
    assert ing.now == NOW
    assert ing.room == 21.0
    assert ing.frozen is False
    assert ing.t_out_eff == 5.0
    # trm observer fed (LearningRuntime mutation through the group).
    assert rt.learning.trm_tracker.current is not None
    # No guard entities discovered -> exactly the three unconditional
    # updates, in today's order.
    ids = [u.issue_id for u in ing.health_updates]
    assert ids == [
        "actuator_unavailable_e1",
        "sensor_frozen_e1",
        "sensor_at_heat_source_e1",
    ]
    assert all(u.active is False for u in ing.health_updates)


def test_stage_ingest_guard_entities_produce_conditional_updates() -> None:
    rt = _runtime()
    inputs = _inputs(
        device_guards=DeviceGuardSnapshot(
            sched_active=True,
            fault_active=False,
            battery=7.0,
            adaptive_mode="on",
            ext_temp_number=None,
        )
    )
    ing = _stage_ingest(
        rt,
        inputs,
        sched_entity="switch.sched",
        adaptive_mode_entity="select.adaptive",
        fault_entity="binary_sensor.fault",
        battery_entity="sensor.batt",
    )
    ids = [u.issue_id for u in ing.health_updates]
    assert ids == [
        "actuator_unavailable_e1",
        "sensor_frozen_e1",
        "device_schedule_e1",
        "adaptive_mode_e1",
        "device_alarm_e1",
        "low_battery_e1",
        "sensor_at_heat_source_e1",
    ]
    by_id = {u.issue_id: u for u in ing.health_updates}
    assert by_id["device_schedule_e1"].active is True
    assert by_id["adaptive_mode_e1"].active is True
    assert by_id["low_battery_e1"].active is True
    assert ing.sched_active is True
    assert ing.fault_active is False


def test_stage_ingest_injected_is_frozen_dispatch() -> None:
    """The injected callable wins — the coordinator-module patch contract."""
    rt = _runtime()
    ing = _stage_ingest(rt, _inputs(), is_frozen_fn=lambda age, thr: True)
    assert ing.frozen is True


def test_stage_ingest_transports_pending_updates_on_abort() -> None:
    rt = _runtime()
    boom = RuntimeError("ingest exploded")

    def _bad_ingest(*args: Any, **kwargs: Any) -> Any:
        raise boom

    try:
        _stage_ingest(rt, _inputs(), ingest_temperature_fn=_bad_ingest)
    except TickStageError as err:
        assert err.cause is boom
        # The health evaluation already appended its three updates.
        assert [u.issue_id for u in err.pending_health_updates] == [
            "actuator_unavailable_e1",
            "sensor_frozen_e1",
            "sensor_at_heat_source_e1",
        ]
    else:  # pragma: no cover - the abort must raise
        raise AssertionError("expected TickStageError")


# ---------------------------------------------------------------------------
# stage_observe
# ---------------------------------------------------------------------------


def test_stage_observe_learns_and_retunes() -> None:
    rt = _runtime()
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    captured: list[Any] = []
    obs = _stage_observe(
        rt, inputs, ing, set_mpc_params=lambda params: captured.append(params)
    )
    assert isinstance(obs, ObservationResult)
    assert obs.window_open is False
    assert (obs.can_heat, obs.can_cool) == (True, False)
    assert obs.device_max == 30.0
    # Learn path ran (MEASURED reading, learn gate open): anchors seeded.
    assert rt.learning.prev_room == 21.0
    assert rt.learning.prev_room_mono == NOW
    assert rt.learning.last_mono == NOW
    # ADR-0052 retune reached the injected adapter setter + the groups.
    assert len(captured) == 1
    assert rt.compressor.dynamics is not None
    # One health update: window_sensor_unavailable (no contacts -> False).
    assert [u.issue_id for u in obs.health_updates] == ["window_sensor_unavailable_e1"]
    assert obs.health_updates[0].active is False


def test_stage_observe_window_open_pauses_learning() -> None:
    rt = _runtime()
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    rt.learning.last_mono = 1.0  # pre-existing anchor must be dropped (V5)
    obs = _stage_observe(
        rt,
        inputs,
        ing,
        effective_window_open_fn=lambda **kwargs: True,
    )
    assert obs.window_open is True
    assert rt.learning.last_mono is None
    assert rt.learning.prev_room is None


def test_stage_observe_healthy_sensor_resets_slope_detector() -> None:
    rt = _runtime()
    contacts = (BinarySensorSnapshot("binary_sensor.w1", False, True),)
    inputs = _inputs(windows=contacts)
    ing = _stage_ingest(rt, inputs)
    rt.window.wa_ref_room = 20.0  # stale anchors from a prior dropout
    rt.window.wa_prev_mono = 5.0
    obs = _stage_observe(rt, inputs, ing, windows=["binary_sensor.w1"])
    # F4b: healthy configured sensor force-resets the detector anchors.
    assert rt.window.wa_ref_room is None
    assert rt.window.wa_prev_mono is None
    assert obs.window_open is False


# ---------------------------------------------------------------------------
# stage_safety_floors
# ---------------------------------------------------------------------------


def test_stage_safety_floors_computes_dewpoint_and_mold_floor() -> None:
    rt = _runtime()
    ing = _stage_ingest(rt, _inputs())
    floors = rt.stage_safety_floors(
        ing,
        entry_id="e1",
        humidity_entity="sensor.rh",
        psychro_dewpoint_fn=psychro_dewpoint,
    )
    assert isinstance(floors, SafetyFloorsResult)
    assert floors.dewpoint == psychro_dewpoint(21.0, 50.0)
    assert floors.mold_min is not None
    assert [u.issue_id for u in floors.health_updates] == [
        "mould_protection_inactive_e1"
    ]
    assert floors.health_updates[0].active is False


def test_stage_safety_floors_flags_humidity_dropout() -> None:
    rt = _runtime()
    ing = _stage_ingest(rt, _inputs(humidity=SensorValue(None)))
    calls: list[tuple[float, float]] = []

    def _spy_dewpoint(t: float, rh: float) -> float:
        calls.append((t, rh))
        return 0.0

    floors = rt.stage_safety_floors(
        ing,
        entry_id="e1",
        humidity_entity="sensor.rh",
        psychro_dewpoint_fn=_spy_dewpoint,
    )
    assert floors.dewpoint is None
    assert floors.mold_min is None
    assert calls == []  # rh is None -> the injected fn is never dispatched
    assert floors.health_updates[0].active is True


# ---------------------------------------------------------------------------
# stage_schedule_gate
# ---------------------------------------------------------------------------


def test_stage_schedule_gate_without_model_requests_no_forecast() -> None:
    rt = _runtime()
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    gate = rt.stage_schedule_gate(
        inputs,
        ing,
        obs,
        schedule=ComfortSchedule.always_comfort(),
        optimal_start=True,
        optimal_stop=False,
    )
    assert isinstance(gate, ScheduleGateResult)
    assert gate.forecast_request is None  # fresh EKF is not identified
    assert gate.sched.is_comfort is True


class _IdentifiedEkf:
    """Stub: only the ``identified`` gate is read on this path."""

    identified = True


def test_stage_schedule_gate_predictive_requests_tick_current_lead() -> None:
    rt = _runtime()
    inputs = _inputs()  # local_minute=600 (10:00)
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    rt.learning.ekf = _IdentifiedEkf()  # type: ignore[assignment]
    schedule = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])
    gate = rt.stage_schedule_gate(
        inputs, ing, obs, schedule=schedule, optimal_start=True, optimal_stop=False
    )
    assert gate.forecast_request is not None
    assert gate.forecast_request.horizon_min == 720.0  # minutes to setback
    assert gate.forecast_request.fallback == ing.t_out_eff


# ---------------------------------------------------------------------------
# stage_comfort_solve
# ---------------------------------------------------------------------------


def _solve_fixtures(rt: ZoneRuntime):
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    floors = rt.stage_safety_floors(
        ing,
        entry_id="e1",
        humidity_entity=None,
        psychro_dewpoint_fn=psychro_dewpoint,
    )
    sp = SchedulePresenceResult(
        home=None,
        presence=PresenceSnapshot(home=(), occupancy=()),
        base=21.0,
        preheating=False,
        preheat_outdoor=None,
        coasting=False,
    )
    op = OperativeResult(
        ext_num=None,
        ext_ok=False,
        operative_active=False,
        room_decide=ing.room,
        t_mrt_decide=None,
    )
    lvl = PresenceLevelResult(
        level=PresenceLevel.COMFORT,
        absent_min=0.0,
        occupied=True,
        eco_widen=0.0,
        cool_ceiling=None,
    )
    return inputs, ing, obs, floors, sp, op, lvl


def _solve(rt: ZoneRuntime, comfort_decide_fn: Any) -> ComfortDecision:
    _inputs_, ing, obs, floors, sp, op, lvl = _solve_fixtures(rt)
    return rt.stage_comfort_solve(
        ing,
        obs,
        floors,
        sp,
        op,
        lvl,
        category=Category("II"),
        cool_min_outdoor=18.0,
        cool_lockout_enabled=True,
        heat_max_outdoor=18.0,
        heat_lockout_enabled=False,
        priority=0.5,
        cool_hard_cap=26.0,
        comfort_decide_fn=comfort_decide_fn,
    )


def test_stage_comfort_solve_runs_the_real_solver() -> None:
    rt = _runtime()
    decision = _solve(rt, comfort_decide)
    assert isinstance(decision, ComfortDecision)
    assert decision.heat_sp == decision.heat_sp  # finite
    assert decision.mode in ("heat", "cool", "idle")


def test_stage_comfort_solve_dispatches_the_injected_callable() -> None:
    """The per-call injection is the coordinator-module patch surface."""
    rt = _runtime()
    sentinel = object()
    seen: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return sentinel

    assert _solve(rt, _spy) is sentinel
    # The pinned call shape: climate_mode comes from the user group.
    assert seen["climate_mode"] == "auto"
    assert seen["comfort_base"] == 21.0
    assert seen["heat_max_outdoor"] is None  # lockout disabled -> None


# ---------------------------------------------------------------------------
# stage_intents
# ---------------------------------------------------------------------------


def test_stage_intents_latches_drive_signals() -> None:
    rt = _runtime()
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    intents = rt.stage_intents(ing, obs, _wt(mode="heat", target=21.5))
    assert intents == IntentsResult(heating=True, cooling=False)
    assert rt.learning.last_u_h == 1.0  # fallback heat intent (no act_state)
    assert rt.learning.last_u_c == 0.0
    assert rt.actuator.last_target == 21.5
    assert rt.window.was_cooling is False


def test_stage_intents_cool_mode_arms_window_slope_gate() -> None:
    rt = _runtime()
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    intents = rt.stage_intents(ing, obs, _wt(mode="cool"))
    assert intents.heating is False
    assert rt.window.was_cooling is True


# ---------------------------------------------------------------------------
# stage_mode_resolution
# ---------------------------------------------------------------------------


def test_stage_mode_resolution_passthrough_and_guard_defaults() -> None:
    rt = _runtime()
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    res = _mode_res(rt, ing, obs)
    assert isinstance(res, ModeResolutionResult)
    assert res.final_mode == "heat"  # no override, no dry -> passthrough
    assert res.guard_block is None  # F1 default
    assert res.mode_nudge_blocked == ""
    assert res.g_min_off > 0.0


def test_stage_mode_resolution_resolves_while_disabled_f1() -> None:
    """F1 invariant: the resolution runs unconditionally (disabled zone)."""
    rt = _runtime()
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    rt.user.enabled = False
    rt.user.override = 23.0  # ignored while disabled (no override_mode call)
    res = _mode_res(rt, ing, obs)
    assert res.final_mode == "heat"
    assert res.guard_pol is not None or res.guard_pol is None  # resolved


# ---------------------------------------------------------------------------
# stage_setpoint_observe + plan_setpoint_write
# ---------------------------------------------------------------------------


def _observe_setpoint(rt: ZoneRuntime, **over: Any) -> SetpointObservation:
    inputs = _inputs()
    ing = _stage_ingest(rt, inputs)
    obs = _stage_observe(rt, inputs, ing)
    res = _mode_res(rt, ing, obs)
    kwargs: dict[str, Any] = {
        "actual_sp": 21.0,
        "step": 0.5,
        "adopt_external_setpoint": False,
        # Phase 7 S2: the K3-unified observation takes the pure Layer-2
        # reason function per call (the coordinator injects its module
        # global; here the canonical function itself).
        "setpoint_adopt_reason_fn": setpoint_adopt_reason,
    }
    routing = over.pop("routing", _routing())
    kwargs.update(over)
    return rt.stage_setpoint_observe(ing, obs, _wt(), res, routing, _nudge(), **kwargs)


def test_stage_setpoint_observe_first_write_mode_change() -> None:
    rt = _runtime()
    spo = _observe_setpoint(rt)
    assert isinstance(spo, SetpointObservation)
    assert spo.actual_sp == 21.0
    assert spo.step == 0.5
    assert spo.mode_changed is True  # nothing written yet -> mode differs
    assert spo.reg_throttled is False
    assert spo.adopted_sp is None  # opt-out


def test_stage_setpoint_observe_own_echo_rebaselines() -> None:
    rt = _runtime()
    spo = _observe_setpoint(rt, routing=_routing(own_change=True), actual_sp=21.8)
    # V2: the device's settled value becomes the echo baseline ...
    assert rt.external.last_written_sp == 21.8
    # ... and is never adopted.
    assert spo.adopted_sp is None


def test_plan_setpoint_write_gates_and_snaps() -> None:
    rt = _runtime()
    spo = SetpointObservation(
        actual_sp=18.0,
        step=0.5,
        mode_changed=True,
        reg_throttled=False,
        adopted_sp=None,
    )
    plan = rt.plan_setpoint_write(
        _wt(target=21.4),
        ModeAdoptionResult(desired_hvac="heat", mode_adopt_reason=""),
        _nudge(),
        spo,
    )
    assert isinstance(plan, ActuatorPlan)
    assert plan.write_setpoint is True
    assert plan.snapped_setpoint == 21.5  # snapped to the 0.5 device step
    assert plan.raw_setpoint == 21.4  # raw value goes on the wire
    assert plan.reason == "tick"


def test_plan_setpoint_write_off_hold_writes_nothing() -> None:
    rt = _runtime()
    rt.user.mode_override = "off"  # K2: off-hold -> no setpoint write
    spo = SetpointObservation(
        actual_sp=18.0,
        step=0.5,
        mode_changed=True,
        reg_throttled=False,
        adopted_sp=None,
    )
    plan = rt.plan_setpoint_write(
        _wt(target=21.4),
        ModeAdoptionResult(desired_hvac="heat", mode_adopt_reason=""),
        _nudge(),
        spo,
    )
    assert plan.write_setpoint is False
    assert plan.snapped_setpoint is None
    assert plan.raw_setpoint is None


# ---------------------------------------------------------------------------
# build_finalize_context
# ---------------------------------------------------------------------------


def test_build_finalize_context_carries_the_stage_values() -> None:
    rt = _runtime()
    inputs, ing, obs, floors, sp, op, lvl = _solve_fixtures(rt)
    decision = rt.stage_comfort_solve(
        ing,
        obs,
        floors,
        sp,
        op,
        lvl,
        category=Category("II"),
        cool_min_outdoor=18.0,
        cool_lockout_enabled=True,
        heat_max_outdoor=18.0,
        heat_lockout_enabled=False,
        priority=0.5,
        cool_hard_cap=26.0,
        comfort_decide_fn=comfort_decide,
    )
    wt = _wt()
    band = ClimateBandResult(climate_diag={}, hum_action="idle")
    intents = rt.stage_intents(ing, obs, wt)
    res = _mode_res(rt, ing, obs)
    sched = ComfortSchedule.always_comfort().state_at(inputs.local_minute)
    state = PreparedState(
        inputs=inputs, ingest=ing, observation=obs, floors=floors, sched=sched
    )
    ctx = rt.build_finalize_context(
        state=state,
        sp=sp,
        op=op,
        decision=decision,
        wt=wt,
        band=band,
        intents=intents,
        failed=False,
        res=res,
        guard_block=res.guard_block,
        mode_nudge_blocked=res.mode_nudge_blocked,
        mode_adopt_reason="",
        sp_adopt_reason="",
    )
    assert isinstance(ctx, FinalizeContext)
    assert ctx.now == NOW
    assert ctx.room == 21.0
    assert ctx.target == wt.target
    assert ctx.final_mode == res.final_mode
    assert ctx.decision is decision
    assert ctx.act_state is wt.act_state
    assert ctx.sched is sched


# ---------------------------------------------------------------------------
# commit_execution / teardown_hold / mark_actuated
# ---------------------------------------------------------------------------


def _execution(effect_id: str, **over: Any) -> EffectExecution:
    base: dict[str, Any] = {
        "effect_id": effect_id,
        "attempted": True,
        "success": True,
        "context_id": None,
        "pre_write_value": None,
        "commanded_value": None,
        "commanded_mode": None,
        "mode_changed": False,
    }
    base.update(over)
    return EffectExecution(**base)


def test_commit_setpoint_write_success_stamps_baselines() -> None:
    rt = _runtime()
    report = ExecutionReport(
        executions=(
            _execution(
                "setpoint_write",
                context_id="ctx-1",
                pre_write_value=20.0,
                commanded_value=21.5,
                commanded_mode="heat",
            ),
        )
    )
    result = rt.commit_execution(report, now=NOW)
    assert isinstance(result, CommitResult)
    assert result.events == ()
    assert rt.external.pre_write_sp == 20.0  # attempt state
    assert list(rt.external.own_write_ctx_ids) == ["ctx-1"]
    assert rt.external.last_written_sp == 21.5  # success state (snapped)
    assert rt.external.last_sp_write_ts == NOW
    assert rt.actuator.last_written_mode == "heat"
    assert rt.actuator.has_actuated is True
    assert rt.dirty is True  # F16: the first flip persists


def test_commit_failed_dispatch_keeps_attempt_state_only() -> None:
    rt = _runtime()
    report = ExecutionReport(
        executions=(
            _execution(
                "setpoint_write",
                success=False,
                context_id="ctx-2",
                pre_write_value=19.5,
                commanded_value=22.0,
            ),
        )
    )
    rt.commit_execution(report, now=NOW)
    assert rt.external.pre_write_sp == 19.5
    assert list(rt.external.own_write_ctx_ids) == ["ctx-2"]
    assert rt.external.last_written_sp is None  # no success stamps
    assert rt.actuator.has_actuated is False
    assert rt.dirty is False


def test_commit_end_hold_post_action_tears_down_and_reports_event() -> None:
    rt = _runtime()
    rt.user.override = 22.5
    rt.user.mode_override = "off"
    rt.dirty = False
    result = rt.commit_execution(
        ExecutionReport(executions=()),
        (EndHold(reason="frost_rescue", require_success=False),),
    )
    assert [e.reason for e in result.events] == ["frost_rescue"]
    assert rt.user.override is None
    assert rt.user.mode_override is None  # K2: shared teardown
    assert rt.dirty is True


def test_commit_guards_missing_now_and_unknown_effect() -> None:
    rt = _runtime()
    try:
        rt.commit_execution(ExecutionReport(executions=(_execution("setpoint_write"),)))
    except ValueError as err:
        assert "needs now=" in str(err)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
    try:
        rt.commit_execution(ExecutionReport(executions=(_execution("bogus"),)))
    except ValueError as err:
        assert "unknown effect_id" in str(err)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_commit_rejects_require_success_end_hold() -> None:
    rt = _runtime()
    try:
        rt.commit_execution(
            ExecutionReport(executions=()),
            (EndHold(reason="x", require_success=True),),
        )
    except NotImplementedError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected NotImplementedError")


def test_mark_actuated_sets_dirty_only_on_first_flip() -> None:
    rt = _runtime()
    rt.mark_actuated()
    assert (rt.actuator.has_actuated, rt.dirty) is not None
    assert rt.actuator.has_actuated is True
    assert rt.dirty is True
    rt.dirty = False
    rt.mark_actuated()  # repeat flip: no new dirty
    assert rt.dirty is False


# ---------------------------------------------------------------------------
# restore + seed_ekf_cold_start
# ---------------------------------------------------------------------------


def test_restore_applies_user_intent_stamps_echo_and_recomputes_f7() -> None:
    rt = _runtime()  # ManualClock(10_000)
    raw = {
        "ekf": ThermalEKF().to_dict(),
        "enabled": False,
        "override": 22.0,
        "override_set_wall": 5000.0,
        "last_written_sp": 21.5,
        "dry_active": True,
    }
    decoded = codec_decode(raw, now_wall=6000.0)
    assert decoded.kind == "v1"
    switchpoint_calls: list[None] = []

    def _minutes() -> float | None:
        switchpoint_calls.append(None)
        return None

    rt.restore(
        decoded,
        override_policy="timer",
        override_timer_h=2.0,
        override_max_h=8.0,
        minutes_to_switchpoint=_minutes,
    )
    assert rt.user.enabled is False
    assert rt.user.override == 22.0
    assert rt.humidity.dry_active is True
    assert rt.external.last_written_sp == 21.5
    # Echo-window re-stamping via the runtime clock: reads as long expired.
    assert rt.external.last_sp_write_ts == 10_000.0 - SETPOINT_ADOPT_ECHO_WINDOW_S * 2.0
    # No mode baseline in the payload -> no mode echo stamp.
    assert rt.external.last_hvac_cmd_ts is None
    # F7 recompute ran (hold active, expiry lost): timer policy.
    assert switchpoint_calls == [None]
    assert rt.user.override_expires_at == 5000.0 + 2.0 * 3600.0


def test_restore_without_hold_skips_the_f7_recompute() -> None:
    rt = _runtime()
    raw = {"ekf": ThermalEKF().to_dict(), "enabled": True}
    decoded = codec_decode(raw, now_wall=6000.0)

    def _minutes() -> float | None:  # pragma: no cover - must not be called
        raise AssertionError("switchpoint lookup must stay condition-gated")

    rt.restore(
        decoded,
        override_policy="timer",
        override_timer_h=2.0,
        override_max_h=8.0,
        minutes_to_switchpoint=_minutes,
    )
    assert rt.user.override is None
    assert rt.user.override_expires_at is None
    # No baselines -> no echo stamps (no_baseline must still win).
    assert rt.external.last_sp_write_ts is None


class _SeasonlessStub:
    def __init__(self, phase: str, prior: float | None) -> None:
        self.phase = phase
        self.mean_outdoor = 4.0
        self._prior = prior
        self.prior_calls: list[tuple[float, float, int]] = []

    def heat_rate_prior(
        self, comfort_base: float, t_out: float, day_ordinal: int
    ) -> float | None:
        self.prior_calls.append((comfort_base, t_out, day_ordinal))
        return self._prior


class _SeedEkfStub:
    n_heating = 0

    def __init__(self) -> None:
        self.seeded: list[float] = []

    def seed_beta_h(self, value: float) -> None:
        self.seeded.append(value)


def test_seed_ekf_cold_start_seeds_from_the_seasonless_prior() -> None:
    rt = _runtime()
    ekf = _SeedEkfStub()
    seasonless = _SeasonlessStub("mature", 0.42)
    rt.learning.ekf = ekf  # type: ignore[assignment]
    rt.learning.seasonless = seasonless  # type: ignore[assignment]
    days: list[None] = []

    def _day() -> int:
        days.append(None)
        return 738_000

    rt.seed_ekf_cold_start(comfort_base=21.0, day_ordinal_fn=_day)
    assert ekf.seeded == [0.42]
    assert seasonless.prior_calls == [(21.0, 4.0, 738_000)]
    assert days == [None]  # evaluated exactly once, under the condition


def test_seed_ekf_cold_start_skips_outside_the_condition() -> None:
    rt = _runtime()
    ekf = _SeedEkfStub()
    rt.learning.ekf = ekf  # type: ignore[assignment]
    rt.learning.seasonless = _SeasonlessStub("collecting", 0.42)  # type: ignore[assignment]

    def _day() -> int:  # pragma: no cover - must not be called
        raise AssertionError("day ordinal must stay condition-gated")

    rt.seed_ekf_cold_start(comfort_base=21.0, day_ordinal_fn=_day)
    assert ekf.seeded == []


def test_zone_runtime_seeds_dirty_false_and_slots_it() -> None:
    rt = _runtime()
    assert rt.dirty is False
    assert "dirty" in ZoneRuntime.__slots__


def test_commit_full_vocabulary_folds_in_call_order() -> None:
    """One report with every remaining effect id, per the 5B commit table."""
    rt = _runtime()
    report = ExecutionReport(
        executions=(
            _execution(
                "mode_nudge",
                context_id="ctx-m",
                commanded_mode="heat",
                mode_changed=True,
            ),
            _execution("ext_select"),
            _execution("ext_feed", commanded_value=21.0),
            _execution("rescue_nudge", commanded_mode="heat"),
            _execution("rescue_write", commanded_value=7.0),
            _execution("safe_mode", commanded_mode="heat"),
            _execution("safe_setpoint", commanded_value=7.0),
        )
    )
    rt.commit_execution(report, now=NOW)
    # mode_nudge: ctx registered + M2-gated ts + mode baseline.
    assert list(rt.external.own_write_ctx_ids) == ["ctx-m"]
    assert rt.external.last_hvac_cmd_ts == NOW
    # safe_mode folded LAST over the rescue_nudge baseline (call order).
    assert rt.external.last_commanded_hvac == "heat"
    assert rt.actuator.last_written_mode == "heat"
    # ext_feed anchors.
    assert rt.actuator.last_fed == 21.0
    assert rt.actuator.last_fed_ts == NOW
    # rescue/safe writes: B2 clears the echo baseline, floor -> last_target.
    assert rt.external.last_written_sp is None
    assert rt.actuator.last_target == 7.0
    assert rt.actuator.has_actuated is True


def test_commit_mode_nudge_without_change_skips_the_ts_stamp() -> None:
    """M2: an unchanged mode dispatch re-arms no echo window."""
    rt = _runtime()
    report = ExecutionReport(
        executions=(
            _execution("mode_nudge", commanded_mode="heat", mode_changed=False),
        )
    )
    rt.commit_execution(report)  # no ts stamp -> now= may be omitted
    assert rt.external.last_commanded_hvac == "heat"
    assert rt.external.last_hvac_cmd_ts is None


def test_restore_full_model_payload_roundtrip() -> None:
    """encode -> decode -> restore applies every persisted model section."""
    from custom_components.poise.control.hdh_savings import HdhSavings
    from custom_components.poise.control.outcome_scoring import OutcomeStats
    from custom_components.poise.control.override import OverrideMode
    from custom_components.poise.control.regulation_quality import (
        RegulationQuality,
    )
    from custom_components.poise.control.window_auto import WindowAutoState
    from custom_components.poise.estimation.running_mean import (
        RunningMeanTracker,
    )
    from custom_components.poise.estimation.seasonless_rate import (
        SeasonlessRate,
    )
    from custom_components.poise.multi.lifecycle import DeviceLifecycle
    from custom_components.poise.persistence.codec import (
        PersistedZoneState,
        encode,
    )

    state = PersistedZoneState(
        ekf=ThermalEKF(),
        trm_tracker=RunningMeanTracker(),
        seasonless=SeasonlessRate(),
        window_auto=WindowAutoState(),
        multi_lifecycle=DeviceLifecycle(),
        ref_offset=None,
        tau_settle=None,
        outcome_stats=OutcomeStats(),
        regq=RegulationQuality(),
        hdh=HdhSavings(),
        dry_active=False,
        enabled=True,
        preset=OverrideMode.NONE,
        climate_mode="heat",
        window_bypass=True,
        has_actuated=True,
        override=None,
        mode_override="off",
        override_set_wall=None,
        override_requested=None,
        override_policy="timer",
        override_expires_at=8000.0,
        override_expiry_is_switchpoint=True,
        boost_expires_at=None,
        boost_prev_preset=None,
        override_stats=[{"delta": 0.5}],
        override_reason="device_adopt_mode",
        last_written_sp=None,
        prev_device_sp=20.5,
        last_commanded_hvac="heat",
        prev_device_mode="heat",
    )
    decoded = codec_decode(encode(state), now_wall=6000.0)
    assert decoded.kind == "v1"
    rt = _runtime()
    rt.restore(
        decoded,
        override_policy="timer",
        override_timer_h=2.0,
        override_max_h=8.0,
        minutes_to_switchpoint=lambda: None,
    )
    # Model sections landed on their groups.
    assert isinstance(rt.learning.ekf, ThermalEKF)
    assert isinstance(rt.learning.trm_tracker, RunningMeanTracker)
    assert isinstance(rt.learning.seasonless, SeasonlessRate)
    assert isinstance(rt.window.window_auto, WindowAutoState)
    assert isinstance(rt.compressor.multi_lifecycle, DeviceLifecycle)
    assert isinstance(rt.diagnostics.outcome_stats, OutcomeStats)
    assert isinstance(rt.diagnostics.regq, RegulationQuality)
    assert isinstance(rt.diagnostics.hdh, HdhSavings)
    # User intent + K2 mode-hold lifecycle.
    assert rt.user.climate_mode == "heat"
    assert rt.user.window_bypass is True
    assert rt.actuator.has_actuated is True
    assert rt.user.mode_override == "off"
    assert rt.user.override_expires_at == 8000.0  # persisted -> no F7 rerun
    assert rt.user.override_expiry_is_switchpoint is True
    assert rt.user.override_reason == "device_adopt_mode"
    assert rt.user.override_stats == [{"delta": 0.5}]
    # B5 baselines + mode echo stamp (baseline exists -> stamped stale).
    assert rt.external.prev_device_sp == 20.5
    assert rt.external.last_commanded_hvac == "heat"
    assert rt.external.last_hvac_cmd_ts is not None
    # No setpoint baseline -> no setpoint echo stamp.
    assert rt.external.last_sp_write_ts is None


def test_stage_observe_second_tick_steps_ekf_and_slope() -> None:
    """A second tick with a real dt drives the EKF observer + slope step."""
    rt = _runtime()
    first = _inputs()
    ing1 = _stage_ingest(rt, first)
    _stage_observe(rt, first, ing1)
    second = _inputs(now_mono=NOW + 60.0, room=SensorValue(20.8, age_s=10.0))
    ing2 = _stage_ingest(rt, second)
    obs2 = _stage_observe(rt, second, ing2)
    assert obs2.window_open is False
    # learn_step ran its predict/update branch and re-anchored.
    assert rt.learning.last_mono == NOW + 60.0
    assert rt.learning.prev_room == 20.8
    # observe_window_auto stepped over the real dt (anchor advanced).
    assert rt.window.wa_prev_mono == NOW + 60.0
