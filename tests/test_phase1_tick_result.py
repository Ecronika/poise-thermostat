"""Phase-1 contract tests for ``runtime/tick_result.py`` (pure, no HA).

The types are behaviour-free shells; these tests pin the contract itself:
construction of every type, enum values, frozen-ness, the ``EndHold`` default
(``require_success=False`` — phase-0 frost-rescue matrix), report ordering,
``TickStageError`` transport and the two ``Literal`` data forms.
"""

from __future__ import annotations

import dataclasses

import pytest

from custom_components.poise.comfort.dual_setpoint import ComfortDecision
from custom_components.poise.comfort.presence import PresenceLevel
from custom_components.poise.comfort.schedule import ScheduleState
from custom_components.poise.contracts import Reading, Source
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
    AvailableTickData,
    ClimateBandResult,
    CommandResult,
    CommitResult,
    EffectExecution,
    EndHold,
    ExecutionReport,
    ExternalTemperaturePlan,
    FinalizeContext,
    ForecastRequest,
    HealthUpdate,
    HoldRoutingResult,
    IngestResult,
    IntentsResult,
    ModeAdoptionResult,
    ModeNudgeResult,
    ModeResolutionResult,
    ObservationResult,
    OperativeResult,
    OverrideEnded,
    PersistencePhase,
    PostExecutionAction,
    PrepareContinuation,
    PreparedState,
    PresenceLevelResult,
    SafetyFloorsResult,
    ScheduleGateResult,
    SchedulePresenceResult,
    SetpointObservation,
    ShadowStageResult,
    TickOutcome,
    TickPlan,
    TickStageError,
    UnavailableTickData,
    ValveHealthResult,
    WriteTargetResult,
)


def _actuator_plan() -> ActuatorPlan:
    return ActuatorPlan(
        write_mode=True,
        hvac_mode="heat",
        write_setpoint=True,
        snapped_setpoint=21.5,
        reason="tick",
        # Phase 6a (S3): the wire value is RAW (today's ActuatorCommand.value
        # is the un-snapped target); the snapped value is the echo baseline.
        raw_setpoint=21.43,
    )


def _tick_inputs() -> TickInputs:
    """A representative pre-await snapshot (value-equal on every call)."""
    return TickInputs(
        now_mono=1000.0,
        now_wall=1_753_000_000.0,
        local_minute=8 * 60 + 30,
        local_day_ordinal=739_450,
        sun_elevation=12.5,
        room=SensorValue(21.2, age_s=30.0, entity_id="sensor.room"),
        outdoor=SensorValue(4.0, entity_id="sensor.outdoor"),
        humidity=SensorValue(55.0, entity_id="sensor.humidity"),
        trm=SensorValue(None),
        mrt=SensorValue(None),
        irradiance=SensorValue(None),
        windows=(
            BinarySensorSnapshot("binary_sensor.window", is_on=False, available=True),
        ),
        actuator=ActuatorCapabilitySnapshot(
            state="heat", hvac_modes=("heat", "off"), max_temp=30.0
        ),
        device_guards=DeviceGuardSnapshot(
            sched_active=False,
            fault_active=False,
            battery=87.0,
            adaptive_mode="off",
            ext_temp_number="number.trv_ext",
        ),
    )


def _ingest_result() -> IngestResult:
    return IngestResult(
        now=1000.0,
        frozen=False,
        sched_active=False,
        fault_active=False,
        heat_source_suspect=False,
        reading=Reading(21.2, "°C", Source.MEASURED, 1.0, 1000.0),
        room=21.2,
        rh=55.0,
        t_out_eff=4.0,
        t_rm_eff=5.1,
        t_rm_source="internal",
        q_solar=0.1,
        q_solar_source="internal",
        q_solar_internal=0.1,
        t_mrt=20.9,
        mrt_source="internal",
        mrt_internal=20.9,
    )


def _observation_result() -> ObservationResult:
    return ObservationResult(
        window_open=False,
        can_heat=True,
        can_cool=False,
        adaptive_cool=False,
        device_max=30.0,
    )


def _floors() -> SafetyFloorsResult:
    return SafetyFloorsResult(mold_min=None, mold_capped=False, dewpoint=8.6)


def _prepared_state() -> PreparedState:
    return PreparedState(
        inputs=_tick_inputs(),
        ingest=_ingest_result(),
        observation=_observation_result(),
        floors=_floors(),
        sched=ScheduleState(True, 0, 0.0, 120),
    )


def _finalize_context() -> FinalizeContext:
    """A representative phase-6a context (value-equal on every call)."""
    return FinalizeContext(
        now=1234.5,
        room=20.8,
        room_decide=20.8,
        reading_source=Source.MEASURED,
        rh=45.0,
        dewpoint=8.6,
        mold_min=None,
        mold_capped=False,
        t_out_eff=5.0,
        t_rm_eff=6.2,
        t_rm_source="internal",
        q_solar=0.1,
        q_solar_source="internal",
        q_solar_internal=0.1,
        t_mrt=20.5,
        mrt_source="internal",
        mrt_internal=20.5,
        sched=ScheduleState(True, 0, 0.0, 120),
        frozen=False,
        window_open=False,
        decision=ComfortDecision(
            heat_sp=21.0,
            cool_sp=25.0,
            mode="heat",
            write_setpoint=21.0,
            target=21.0,
        ),
        eff_cool=25.0,
        mode="heat",
        target=21.0,
        final_mode="heat",
        norm_binding="en16798",
        binding_precedence="comfort",
        override_clamped=False,
        heating=True,
        cooling=False,
        failed=False,
        adaptive_cool=False,
        preheating=False,
        preheat_outdoor=None,
        coasting=False,
        act_state=None,
        guard_pol=None,
        g_min_off=0.0,
        g_mode_hold=0.0,
        guard_block=None,
        mode_nudge_blocked="",
        idle_park_mode=None,
        mode_adopt_reason="",
        sp_adopt_reason="",
        climate_diag={"dry_active": False},
        sched_active=False,
        fault_active=False,
        heat_source_suspect=False,
        ext_num=None,
        operative_active=False,
    )


def _tick_plan() -> TickPlan:
    return TickPlan(
        actuator_plan=_actuator_plan(),
        external_temperature_plan=ExternalTemperaturePlan(
            select_external=False, feed_value=21.3
        ),
        pre_events=(OverrideEnded("hold_expired"),),
        post_actions=(EndHold("frost_rescue"),),
        persistence=PersistencePhase.AFTER_EXECUTION,
        control_data={"final_mode": "heat"},
        finalize_context=_finalize_context(),
    )


# ---------------------------------------------------------------------------
# PersistencePhase
# ---------------------------------------------------------------------------


def test_persistence_phase_members_and_values() -> None:
    assert [p.value for p in PersistencePhase] == [
        "none",
        "before_execution",
        "after_execution",
    ]
    assert PersistencePhase("after_execution") is PersistencePhase.AFTER_EXECUTION


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------


def test_actuator_plan_carries_the_decision() -> None:
    plan = _actuator_plan()
    assert plan.write_mode is True
    assert plan.hvac_mode == "heat"
    assert plan.write_setpoint is True
    assert plan.snapped_setpoint == 21.5
    assert plan.reason == "tick"
    # Phase 6a (S3): raw wire value vs. snapped echo baseline are distinct
    # fields; a no-write plan defaults the raw value to None.
    assert plan.raw_setpoint == 21.43
    no_write = ActuatorPlan(
        write_mode=False,
        hvac_mode=None,
        write_setpoint=False,
        snapped_setpoint=None,
        reason="tick",
    )
    assert no_write.raw_setpoint is None


def test_actuator_plan_is_frozen() -> None:
    plan = _actuator_plan()
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.write_setpoint = False  # type: ignore[misc]


def test_external_temperature_plan_skip_feed_defaults_true() -> None:
    # Finding 11 (Z. 3191-3240): select success skips the feed by default.
    plan = ExternalTemperaturePlan(select_external=True, feed_value=20.9)
    assert plan.skip_feed_on_select_success is True
    explicit = ExternalTemperaturePlan(
        select_external=False, feed_value=None, skip_feed_on_select_success=False
    )
    assert explicit.skip_feed_on_select_success is False


# ---------------------------------------------------------------------------
# Domain events, command result, post-execution actions
# ---------------------------------------------------------------------------


def test_command_result_defaults_and_events() -> None:
    assert CommandResult() == CommandResult(events=(), dirty=False)
    result = CommandResult(events=(OverrideEnded("user_resume"),), dirty=True)
    assert result.events[0].reason == "user_resume"
    assert result.dirty is True


def test_end_hold_default_require_success_false() -> None:
    # Findings 6+9: the frost-rescue hold end (Z. 3324-3325) is deliberately
    # NOT coupled to write success — the default must encode that.
    action = EndHold("frost_rescue")
    assert action.require_success is False
    assert action.reason == "frost_rescue"
    assert isinstance(action, PostExecutionAction)


def test_end_hold_is_frozen() -> None:
    action = EndHold("frost_rescue", require_success=True)
    assert action.require_success is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.reason = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Health updates and TickStageError
# ---------------------------------------------------------------------------


def test_tick_stage_error_carries_pending_health_updates() -> None:
    # Placeholders mirror _issue()'s keyword (coordinator.py L1274-1281);
    # real sites pass entity/zone names (e.g. heating_failure {zone}) that
    # must survive the TickStageError transport (finding 13).
    update = HealthUpdate(
        issue_id="heating_failure_x",
        active=True,
        translation_key="heating_failure",
        placeholders={"zone": "Living"},
    )
    cause = ValueError("boom")
    err = TickStageError(cause, pending_health_updates=(update,))
    assert isinstance(err, Exception)
    assert err.cause is cause
    assert err.pending_health_updates == (update,)
    assert err.pending_health_updates[0].translation_key == "heating_failure"
    assert err.pending_health_updates[0].placeholders == {"zone": "Living"}
    assert "boom" in str(err)


def test_health_update_placeholders_default_to_none() -> None:
    # Most sites emit without placeholders — the field must be optional.
    update = HealthUpdate(
        issue_id="sensor_unavailable_x", active=True, translation_key="sensor_gone"
    )
    assert update.placeholders is None


def test_tick_stage_error_defaults_to_no_pending_updates() -> None:
    err = TickStageError(RuntimeError("stage failed"))
    assert err.pending_health_updates == ()
    with pytest.raises(TickStageError):
        raise err


# ---------------------------------------------------------------------------
# Forecast handshake and prepare/finalize contexts
# ---------------------------------------------------------------------------


def test_prepare_continuation_with_forecast_request() -> None:
    request = ForecastRequest(horizon_min=45.0, fallback=5.0)
    prep = PrepareContinuation(
        forecast_request=request, prepared_state=_prepared_state()
    )
    assert prep.forecast_request is not None
    assert prep.forecast_request is request
    assert prep.forecast_request.horizon_min == 45.0
    assert prep.forecast_request.fallback == 5.0


def test_prepare_continuation_without_forecast_request() -> None:
    # Non-predictive ticks request no forecast at all (finding 5).
    prep = PrepareContinuation(forecast_request=None, prepared_state=_prepared_state())
    assert prep.forecast_request is None
    assert isinstance(prep.prepared_state, PreparedState)


def test_prepared_state_value_semantics_and_frozen() -> None:
    # Phase 6a (S2): the cross-seam carrier is an honest value object.
    state = _prepared_state()
    assert state == _prepared_state()
    assert state.ingest.room == 21.2
    assert state.sched.is_comfort is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.sched = ScheduleState(False, 3.0, 60.0, 0)  # type: ignore[misc]


def test_prepared_state_field_set_is_pinned() -> None:
    # Phase 6a (S2): the field set IS the cross-forecast-seam contract
    # (prepare_until_forecast -> resume_prepare); 6b moves it onto
    # ZoneRuntime unchanged. Adding or removing a field is a contract
    # change and must update this pin.
    assert [f.name for f in dataclasses.fields(PreparedState)] == [
        "inputs",
        "ingest",
        "observation",
        "floors",
        "sched",
    ]


def test_stage_result_field_sets_are_pinned() -> None:
    # Phase 6a (S2): every prepare/resume stage returns one of these typed
    # results (plan section 5 cuts; DoD "no stage with 50 loose locals").
    # The field names ARE the inter-stage dataflow — pinned so a silent
    # contract drift fails loudly.
    expected: dict[type, list[str]] = {
        IngestResult: [
            "now",
            "frozen",
            "sched_active",
            "fault_active",
            "heat_source_suspect",
            "reading",
            "room",
            "rh",
            "t_out_eff",
            "t_rm_eff",
            "t_rm_source",
            "q_solar",
            "q_solar_source",
            "q_solar_internal",
            "t_mrt",
            "mrt_source",
            "mrt_internal",
            # Phase 6a (S4, finding 13): the collecting stages return their
            # HealthUpdates for the coordinator's stage-end checkpoints.
            "health_updates",
        ],
        ObservationResult: [
            "window_open",
            "can_heat",
            "can_cool",
            "adaptive_cool",
            "device_max",
            "health_updates",
        ],
        SafetyFloorsResult: ["mold_min", "mold_capped", "dewpoint", "health_updates"],
        ScheduleGateResult: ["sched", "forecast_request"],
        SchedulePresenceResult: [
            "home",
            "presence",
            "base",
            "preheating",
            "preheat_outdoor",
            "coasting",
        ],
        OperativeResult: [
            "ext_num",
            "ext_ok",
            "operative_active",
            "room_decide",
            "t_mrt_decide",
            "health_updates",
        ],
        PresenceLevelResult: [
            "level",
            "absent_min",
            "occupied",
            "eco_widen",
            "cool_ceiling",
        ],
        WriteTargetResult: [
            "act_state",
            "actuator_online",
            "cool_ac",
            "idle_park_mode",
            "eff_cool",
            "target",
            "mode",
            "norm_binding",
            "binding_precedence",
            "override_clamped",
        ],
        ClimateBandResult: ["climate_diag", "hum_action"],
        IntentsResult: ["heating", "cooling"],
        ModeResolutionResult: [
            "final_mode",
            "act_modes",
            "guard_pol",
            "g_min_off",
            "g_mode_hold",
            "guard_block",
            "mode_nudge_blocked",
        ],
        HoldRoutingResult: [
            "own_change",
            "off_held",
            "hold_resumed",
            "mode_adopt_reason",
            "sp_adopt_reason",
        ],
        ModeAdoptionResult: ["desired_hvac", "mode_adopt_reason"],
        ModeNudgeResult: ["mode_nudge", "guard_block", "mode_nudge_blocked"],
        SetpointObservation: [
            "actual_sp",
            "step",
            "mode_changed",
            "reg_throttled",
            "adopted_sp",
            # Phase 7 S2 (K3 unification): the reason travels with the
            # decision, computed by the ONE observe call.
            "sp_adopt_reason",
        ],
        # Phase 8 (S2): finalize_tick's stage split along the plan-5.6 map.
        ShadowStageResult: [
            "operative",
            "binding",
            "cover_peak",
            "cover_pos",
            "cover_reason",
            "shadow_objs",
        ],
        ValveHealthResult: [
            "closing_steps",
            "idle_steps",
            "valve_health",
            "health_updates",
        ],
    }
    for cls, fields in expected.items():
        assert [f.name for f in dataclasses.fields(cls)] == fields, cls.__name__


def test_stage_results_carry_health_updates() -> None:
    # Phase 6a (S4, finding 13): the four collecting stage results (ingest,
    # observe, safety floors, operative) carry their HealthUpdates for the
    # coordinator's stage-end checkpoints; the field defaults to ``()`` so
    # non-collecting constructions stay valid.
    update = HealthUpdate(
        issue_id="mould_protection_inactive_x",
        active=True,
        translation_key="mould_protection_inactive",
        placeholders={"entity": "sensor.rh"},
    )
    assert _ingest_result().health_updates == ()
    assert _observation_result().health_updates == ()
    floors = SafetyFloorsResult(
        mold_min=None, mold_capped=False, dewpoint=None, health_updates=(update,)
    )
    assert floors.health_updates == (update,)
    op = OperativeResult(
        ext_num=None,
        ext_ok=False,
        operative_active=False,
        room_decide=21.2,
        t_mrt_decide=20.9,
        health_updates=(update,),
    )
    assert op.health_updates[0].issue_id == "mould_protection_inactive_x"
    assert op.health_updates[0].placeholders == {"entity": "sensor.rh"}


def test_stage_results_construct_and_are_frozen() -> None:
    # Construction smoke for the S2 stage results not covered by the
    # builders above, plus the frozen (immutable) contract.
    gate = ScheduleGateResult(
        sched=ScheduleState(True, 0, 0.0, 120),
        forecast_request=ForecastRequest(horizon_min=45.0, fallback=5.0),
    )
    assert gate.forecast_request is not None
    sp = SchedulePresenceResult(
        home=True,
        presence=PresenceSnapshot(home=(True,), occupancy=(False,)),
        base=21.0,
        preheating=False,
        preheat_outdoor=None,
        coasting=False,
    )
    assert sp.home is True
    lvl = PresenceLevelResult(
        level=PresenceLevel.COMFORT,
        absent_min=0.0,
        occupied=True,
        eco_widen=0.0,
        cool_ceiling=None,
    )
    assert lvl.level is PresenceLevel.COMFORT
    op = OperativeResult(
        ext_num=None,
        ext_ok=False,
        operative_active=False,
        room_decide=21.2,
        t_mrt_decide=20.9,
    )
    wt = WriteTargetResult(
        act_state=None,
        actuator_online=True,
        cool_ac=None,
        idle_park_mode=None,
        eff_cool=25.0,
        target=21.0,
        mode="heat",
        norm_binding="en16798",
        binding_precedence="comfort",
        override_clamped=False,
    )
    band = ClimateBandResult(climate_diag={"dry_active": False}, hum_action="idle")
    intents = IntentsResult(heating=True, cooling=False)
    res = ModeResolutionResult(
        final_mode="heat",
        act_modes=["heat", "off"],
        guard_pol=None,
        g_min_off=0.0,
        g_mode_hold=0.0,
        guard_block=None,
        mode_nudge_blocked="",
    )
    routing = HoldRoutingResult(
        own_change=False,
        off_held=False,
        hold_resumed=False,
        mode_adopt_reason="",
        sp_adopt_reason="",
    )
    adoption = ModeAdoptionResult(desired_hvac="heat", mode_adopt_reason="")
    nudge = ModeNudgeResult(mode_nudge=False, guard_block=None, mode_nudge_blocked="")
    spo = SetpointObservation(
        actual_sp=21.0,
        step=0.5,
        mode_changed=False,
        reg_throttled=False,
        adopted_sp=None,
    )
    assert op.room_decide == 21.2
    assert band.hum_action == "idle"
    assert intents.heating and not intents.cooling
    assert routing.mode_adopt_reason == ""
    assert adoption.desired_hvac == "heat"
    assert nudge.mode_nudge is False
    assert spo.step == 0.5
    with pytest.raises(dataclasses.FrozenInstanceError):
        wt.target = 22.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.final_mode = "cool"  # type: ignore[misc]


def test_finalize_stage_results_construct_and_are_frozen() -> None:
    # Phase 8 (S2): finalize_tick's stage split — the shadow result doubles
    # as the neutral seed (its shadow_objs is the degraded payload WITHOUT
    # the two compressor_gate_* keys, phase-0 finding 3); the valve result
    # carries the segment's only HealthUpdate for the caller's immediate
    # emission at the historical position (finding 13).
    shadow = ShadowStageResult(
        operative=21.3,
        binding="en16798",
        cover_peak=21.3,
        cover_pos=0.0,
        cover_reason="",
        shadow_objs={"tpi_duty": None, "multi_reason": "shadow_error"},
    )
    assert shadow.operative == 21.3
    assert shadow.binding == "en16798"
    assert shadow.shadow_objs["multi_reason"] == "shadow_error"
    assert "compressor_gate_would_block" not in shadow.shadow_objs
    valve = ValveHealthResult(closing_steps=12.0, idle_steps=40.0, valve_health="ok")
    assert valve.health_updates == ()  # defaulted for direct constructions
    update = HealthUpdate(
        issue_id="valve_stuck_x",
        active=True,
        translation_key="valve_stuck",
        placeholders={"entity": "number.valve"},
    )
    stuck = ValveHealthResult(
        closing_steps=0.0,
        idle_steps=40.0,
        valve_health="stuck",
        health_updates=(update,),
    )
    assert stuck.health_updates[0].issue_id == "valve_stuck_x"
    assert stuck.health_updates[0].placeholders == {"entity": "number.valve"}
    with pytest.raises(dataclasses.FrozenInstanceError):
        shadow.binding = "mold"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        valve.valve_health = "stuck"  # type: ignore[misc]


def test_finalize_context_value_semantics_and_frozen() -> None:
    # Phase 6a (S1): the context is an honest value object — two identical
    # constructions compare equal, and it is immutable.
    ctx = _finalize_context()
    assert ctx == _finalize_context()
    assert ctx.reading_source is Source.MEASURED
    assert ctx.decision.heat_sp == 21.0
    assert ctx.sched.is_comfort is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.room = 25.0  # type: ignore[misc]


def test_finalize_context_field_set_is_pinned() -> None:
    # Phase 6a (S1): the field set IS the prepare→finalize contract — it was
    # established by an AST free-variable scan of the post-savepoint segment
    # (50 names; ``reading`` narrowed to ``reading_source``). Adding or
    # removing a field is a contract change and must update this pin.
    assert [f.name for f in dataclasses.fields(FinalizeContext)] == [
        "now",
        "room",
        "room_decide",
        "reading_source",
        "rh",
        "dewpoint",
        "mold_min",
        "mold_capped",
        "t_out_eff",
        "t_rm_eff",
        "t_rm_source",
        "q_solar",
        "q_solar_source",
        "q_solar_internal",
        "t_mrt",
        "mrt_source",
        "mrt_internal",
        "sched",
        "frozen",
        "window_open",
        "decision",
        "eff_cool",
        "mode",
        "target",
        "final_mode",
        "norm_binding",
        "binding_precedence",
        "override_clamped",
        "heating",
        "cooling",
        "failed",
        "adaptive_cool",
        "preheating",
        "preheat_outdoor",
        "coasting",
        "act_state",
        "guard_pol",
        "g_min_off",
        "g_mode_hold",
        "guard_block",
        "mode_nudge_blocked",
        "idle_park_mode",
        "mode_adopt_reason",
        "sp_adopt_reason",
        "climate_diag",
        "sched_active",
        "fault_active",
        "heat_source_suspect",
        "ext_num",
        "operative_active",
    ]


# ---------------------------------------------------------------------------
# TickPlan
# ---------------------------------------------------------------------------


def test_tick_plan_construction() -> None:
    plan = _tick_plan()
    assert plan.actuator_plan == _actuator_plan()
    assert plan.pre_events == (OverrideEnded("hold_expired"),)
    assert plan.post_actions == (EndHold("frost_rescue"),)
    assert plan.persistence is PersistencePhase.AFTER_EXECUTION
    assert plan.control_data["final_mode"] == "heat"
    assert plan.finalize_context == _finalize_context()


def test_tick_plan_unavailable_shape() -> None:
    # Finding 4+12: an unavailable tick may carry no writes but still flush
    # dirty state BEFORE any (safe-state) execution. Phase 6a (S3): the
    # short-circuit carries NO finalize context (no finalize segment —
    # minimal present) and no actuator plan (the SafeStatePlan decision is
    # positioned AFTER the BEFORE_EXECUTION save; documented reorder-proof
    # gap in ``_run_unavailable_tick``).
    plan = TickPlan(
        actuator_plan=None,
        external_temperature_plan=None,
        pre_events=(),
        post_actions=(),
        persistence=PersistencePhase.BEFORE_EXECUTION,
        control_data={},
        finalize_context=None,
    )
    assert plan.actuator_plan is None
    assert plan.external_temperature_plan is None
    assert plan.persistence is PersistencePhase.BEFORE_EXECUTION
    assert plan.finalize_context is None


# ---------------------------------------------------------------------------
# ExecutionReport and CommitResult
# ---------------------------------------------------------------------------


def _execution(effect_id: str, *, success: bool = True) -> EffectExecution:
    return EffectExecution(
        effect_id=effect_id,
        attempted=True,
        success=success,
        context_id=f"ctx-{effect_id}",
        pre_write_value=20.5,
        commanded_value=21.5,
    )


def test_execution_report_preserves_call_order() -> None:
    # Finding 9: the commit folds strictly in actual call order.
    first = _execution("set_mode")
    second = _execution("set_setpoint", success=False)
    third = _execution("external_feed")
    report = ExecutionReport(executions=(first, second, third))
    assert report.executions == (first, second, third)
    assert [e.effect_id for e in report.executions] == [
        "set_mode",
        "set_setpoint",
        "external_feed",
    ]
    assert report.executions[1].attempted is True
    assert report.executions[1].success is False


def test_effect_execution_attempt_fields() -> None:
    execution = _execution("set_setpoint")
    assert execution.context_id == "ctx-set_setpoint"
    assert execution.pre_write_value == 20.5
    assert execution.commanded_value == 21.5


def test_effect_execution_mode_fields_default() -> None:
    # Phase 5B additions stay OPTIONAL: a six-field construction (the phase-1
    # shape) must keep working, with the mode transport defaulted off.
    execution = _execution("ext_feed")
    assert execution.commanded_mode is None
    assert execution.mode_changed is False


def test_effect_execution_carries_mode_transport() -> None:
    # Phase 5B: mode STRINGS travel next to the float value — the tick
    # setpoint write stamps ``last_written_mode`` (a mode string on a
    # setpoint effect) and its M2 flag is evaluated at dispatch time.
    execution = EffectExecution(
        effect_id="setpoint_write",
        attempted=True,
        success=True,
        context_id="ctx-1",
        pre_write_value=19.5,
        commanded_value=21.5,
        commanded_mode="heat",
        mode_changed=True,
    )
    assert execution.commanded_mode == "heat"
    assert execution.mode_changed is True
    assert execution.commanded_value == 21.5  # both transports coexist


def test_effect_execution_is_frozen_with_slots() -> None:
    execution = _execution("mode_nudge")
    with pytest.raises(dataclasses.FrozenInstanceError):
        execution.success = False  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        execution.commanded_mode = "cool"  # type: ignore[misc]
    assert not hasattr(execution, "__dict__")  # slots: no stray attributes


def test_commit_result_defaults_empty() -> None:
    assert CommitResult().events == ()
    result = CommitResult(events=(OverrideEnded("frost_rescue"),))
    assert result.events[0].reason == "frost_rescue"


# ---------------------------------------------------------------------------
# Public data contract (both Literal forms) and TickOutcome
# ---------------------------------------------------------------------------


def _available() -> AvailableTickData:
    return AvailableTickData(
        mono_ts=1234.5,
        heating=True,
        sensor_frozen=False,
        current_temperature=20.8,
        heat_sp=21.5,
        tpi_duty=0.4,
        heat_demand=0.6,
    )


def test_available_tick_data_literal_and_hub_contract() -> None:
    data = _available()
    assert data.available is True  # Literal[True], defaulted
    assert data.mono_ts == 1234.5
    assert data.heating is True
    assert data.sensor_frozen is False
    assert data.current_temperature == 20.8
    assert data.heat_sp == 21.5
    assert data.tpi_duty == 0.4
    assert data.heat_demand == 0.6


def test_available_tick_data_optional_fields_accept_none() -> None:
    data = AvailableTickData(
        mono_ts=0.0,
        heating=False,
        sensor_frozen=True,
        current_temperature=None,
        heat_sp=None,
        tpi_duty=None,
        heat_demand=0.0,
    )
    assert data.current_temperature is None
    assert data.heat_sp is None
    assert data.tpi_duty is None


def test_unavailable_tick_data_literal_form() -> None:
    data = UnavailableTickData(unavailable_safe=True)
    assert data.available is False  # Literal[False], defaulted
    assert data.unavailable_safe is True
    assert UnavailableTickData(unavailable_safe=False).available is False


def test_tick_data_forms_are_frozen() -> None:
    available = _available()
    with pytest.raises(dataclasses.FrozenInstanceError):
        available.heating = False  # type: ignore[misc]
    unavailable = UnavailableTickData(unavailable_safe=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        unavailable.unavailable_safe = True  # type: ignore[misc]


def test_tick_outcome_wraps_both_data_forms() -> None:
    available = TickOutcome(
        data=_available(),
        diagnostics={"mpc_shadow": None},
        trace_record={"schema": 2},
    )
    assert isinstance(available.data, AvailableTickData)
    assert available.diagnostics["mpc_shadow"] is None
    assert available.trace_record is not None
    assert available.trace_record["schema"] == 2

    unavailable = TickOutcome(
        data=UnavailableTickData(unavailable_safe=False),
        diagnostics={},
        trace_record=None,
    )
    assert isinstance(unavailable.data, UnavailableTickData)
    assert unavailable.trace_record is None
