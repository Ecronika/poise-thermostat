"""Phase-1 contract tests for ``runtime/tick_result.py`` (pure, no HA).

The types are behaviour-free shells; these tests pin the contract itself:
construction of every type, enum values, frozen-ness, the ``EndHold`` default
(``require_success=False`` — phase-0 frost-rescue matrix), report ordering,
``TickStageError`` transport and the two ``Literal`` data forms.
"""

from __future__ import annotations

import dataclasses

import pytest

from custom_components.poise.runtime.tick_result import (
    ActuatorPlan,
    AvailableTickData,
    CommandResult,
    CommitResult,
    EffectExecution,
    EndHold,
    ExecutionReport,
    ExternalTemperaturePlan,
    FinalizeContext,
    ForecastRequest,
    HealthUpdate,
    OverrideEnded,
    PersistencePhase,
    PostExecutionAction,
    PrepareContinuation,
    PreparedState,
    TickOutcome,
    TickPlan,
    TickStageError,
    UnavailableTickData,
)


def _actuator_plan() -> ActuatorPlan:
    return ActuatorPlan(
        write_mode=True,
        hvac_mode="heat",
        write_setpoint=True,
        snapped_setpoint=21.5,
        reason="tick",
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
        finalize_context=FinalizeContext(),
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
    prep = PrepareContinuation(forecast_request=request, prepared_state=PreparedState())
    assert prep.forecast_request is not None
    assert prep.forecast_request is request
    assert prep.forecast_request.horizon_min == 45.0
    assert prep.forecast_request.fallback == 5.0


def test_prepare_continuation_without_forecast_request() -> None:
    # Non-predictive ticks request no forecast at all (finding 5).
    prep = PrepareContinuation(forecast_request=None, prepared_state=PreparedState())
    assert prep.forecast_request is None
    assert isinstance(prep.prepared_state, PreparedState)


def test_context_placeholders_are_frozen_and_equal() -> None:
    # Field-less phase-1 placeholders: value semantics, immutable.
    assert FinalizeContext() == FinalizeContext()
    assert PreparedState() == PreparedState()


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
    assert plan.finalize_context == FinalizeContext()


def test_tick_plan_unavailable_shape() -> None:
    # Finding 4+12: an unavailable tick may carry no writes but still flush
    # dirty state BEFORE any (safe-state) execution.
    plan = TickPlan(
        actuator_plan=None,
        external_temperature_plan=None,
        pre_events=(),
        post_actions=(),
        persistence=PersistencePhase.BEFORE_EXECUTION,
        control_data={},
        finalize_context=FinalizeContext(),
    )
    assert plan.actuator_plan is None
    assert plan.external_temperature_plan is None
    assert plan.persistence is PersistencePhase.BEFORE_EXECUTION


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
