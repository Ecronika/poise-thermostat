"""Tick orchestrator — the whole per-tick program, lifted out of the coordinator.

``coordinator.py`` keeps only the HA coupling (``DataUpdateCoordinator``
lifecycle, the tick lock, ``tick_ms``/``TickBudget``, persistence, health
issues and the entity-facing command API).  Everything between "the lock is
held" and "a payload is returned" lives here: the tick methods
(``_run_once``, ``prepare_until_forecast``, ``resume_prepare``,
``finalize_tick``, ``_run_unavailable_tick``, ``_write_unavailable_safe_state``,
``_build_finalize_context``, ``_maybe_record_trace``, ``flush_traces``) and
the ``_stage_*`` methods.

Receiver rules (binding): collaborators are the injected attributes, every
other coordinator read is ``self._c.<x>``, the logger is the injected
``self._log`` (the logger CHANNEL is behaviour: records must keep the name
``custom_components.poise.coordinator``), and the patch-surface globals are
``self._g.<name>``.  Await positions, commit positions, event/emission
positions and checkpoint positions are behaviour.

Error boundaries are narrow by design (ADR-0065): one boundary per shadow
segment in ``_stage_shadow_domain``, two independent boundaries in
``_stage_climate_band``; the trace append is queued off the lock (ADR-0063),
the forecast fetch is a background refresh (ADR-0063) and the persistence
checkpoint sits behind ``finalize_tick`` (ADR-0064).

PATCH SURFACE (binding).  Phase-0/6 fault-injection tests patch module globals
of ``custom_components.poise.coordinator`` — e.g.
``patch("custom_components.poise.coordinator.is_frozen")``.  Importing those
names HERE would patch a dead name: the test would still pass while testing
nothing.  So this module never imports them.  ``_CoordinatorGlobals`` resolves
them at CALL TIME through the injected coordinator module object, which keeps
every existing patch target working unchanged.  The set is:

* patched by tests today — ``is_frozen``, ``ingest_temperature``,
  ``effective_window_open``, ``psychro_dewpoint``, ``comfort_decide``,
  ``resolve_write_target``, ``humidity_decide``, ``predict_peak_operative``,
  ``plan_preheat``;
* documented as patch surface, not patched yet — ``resolve_desired_mode``,
  ``mode_adopt_reason``, ``setpoint_adopt_reason``, ``shading_target_position``,
  ``evaluate_thermal_shadow``, ``_lifecycle``.

Whoever adds a name to that list must import it in ``coordinator.py`` (with a
``noqa: F401``) and read it through ``self._g`` here — never import it into
this module.  The ``if TYPE_CHECKING`` block below imports the same symbols a
SECOND time for typing only: those imports are never executed, bind no runtime
name in this module and therefore create no second (dead) patch target, but
they let ``mypy --strict`` check every ``self._g.<name>(...)`` call site
against the real signature.

DISPATCH BACK THROUGH THE COORDINATOR (binding).  Every call that a test may
replace on the coordinator INSTANCE is resolved through ``self._c`` at call
time, so the replacement is seen: ``self._c._write_unavailable_safe_state()``
(test_phase0_persistence_checkpoint), ``self._c._maybe_record_trace(...)``
(test_phase8_presenter) and ``self._c._forecast_outdoor(...)``
(test_forecast_backoff / test_glue_coverage4 / test_phase5a_wiring).
``commit_execution`` likewise stays a coordinator method (test_phase5b_sequences
drives it directly) and is called through ``self._c``.  The two CHECKPOINT
primitives obey the same rule instead of being snapshotted as bound methods in
``__init__``: the persistence checkpoint is ``self._c._maybe_save()`` and the
health checkpoint is ``self._c._health.emit(...)``.  Both must stay resolved
through the coordinator instance on every call; nothing here may snapshot
them.

TRANSITIONAL COORDINATOR BACKREFERENCE.  ``self._c`` is a documented transition
form.  It carries (a) the coordinator's config/tuning attributes that the moved
bodies read verbatim (``_optimal_start``, ``_comfort_base``, ``_schedule``,
``_category``, ``_priority``, ``_windows``, ``_cool_*``/``_heat_*``, ...),
(b) the writes the moved bodies still perform on adapter-owned state
(``_unavailable_logged``, ``_mpc_params`` via ``_set_mpc_params``), and (c) the
coordinator methods listed above plus the override/hold commands
(``set_override``, ``_set_mode_override``, ``_end_hold``,
``_expire_timed_states``, ``_fire_override_ended``, ``_notify_failure``) and
the suggestion-issue facades (``_sync_suggestion_issue``,
``_sync_clo_suggestion_issue``, ``_sync_season_hint_issue``).
A later step narrows it; nothing here may rely on it growing.

STATE OWNED HERE.  ``_trace_recorder`` (the lazily built ADR-0011 trace
writer) and ``_trace_slug`` (seeded from ``entry.entry_id``) belong to this
class — the only reader, ``_maybe_record_trace``, lives here.  Nothing
outside may read them (pinned by
``tests/integration/test_phase6b_state_move.py``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import ModuleType
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification
from homeassistant.util import dt as dt_util

from ..adaptive_cool import adaptive_cool_mode
from ..comfort.dual_setpoint import ComfortDecision
from ..comfort.en16798 import HEATING_LOWER, HEATING_UPPER
from ..comfort.humidity import HumidityDecision
from ..comfort.operative import operative_temperature
from ..comfort.pmv import PMV_MODEL_REV, pmv_setpoint_offset
from ..comfort.presence import (
    PresenceLevel,
    any_present,
    resolve_presence,
    step_room_absence,
)
from ..comfort.readiness import (
    pmv_control_ready,
    presence_control_ready,
    room_present,
)
from ..comfort.schedule import ScheduleState
from ..comfort.thermal_shock import adaptive_cool_setpoint, rate_limit
from ..comfort.ventilation import advice_transition
from ..const import (
    DEFAULT_TRACE_MAX_BYTES,
    DEVICE_MAX_C,
    EVENT_VENT_ADVICE,
    EXTERNAL_FEED_KEEPALIVE_S,
    FROST_FLOOR_C,
    TICK_INTERVAL_S,
    UNAVAILABLE_SAFE_AFTER_S,
    WINDOW_MOULD_SUPPRESS_S,
    WRITE_DEADBAND_C,
)
from ..contracts import ActuatorCommand, ActuatorPath
from ..control.comfort_activation import (
    ComfortActivation,
    activation_signature,
    cascade_after_invalidation,
    may_dwell,
    step_tier,
)
from ..control.dynamics import PROFILES
from ..control.external_override import note_device_fan, observe_fan_foreign
from ..control.fan_first import (
    FanFirstDecision,
    FanFirstState,
    fan_first_decision,
)
from ..control.feedback import clo_suggestion_reason, detect_feedback_pattern
from ..control.hub_aggregate import zone_heat_demand
from ..control.lifecycle import resolve_safe_state
from ..control.mpc_shadow import evaluate_shadow
from ..control.optimal_start import latched_forecast_day
from ..control.outcome_scoring import observe_session
from ..control.override import OverrideMode, hold_ends_at_preheat, mode_comfort_base
from ..control.pi_shadow import evaluate_pi_shadow
from ..control.reference_offset import update_offset
from ..control.regulation_quality import (
    FLIP_TIER_COMFORT,
    ca_tick_scorable,
    flip_metric_ok,
)
from ..control.scoring_expectation import model_expected_minutes
from ..control.suggestion import (
    detect_override_pattern,
    resolve_suggestion_conflict,
    season_gate_floor,
    season_hint_t_rm,
    season_mode_hint,
    suggestion_suppressed,
)
from ..control.tick_resolve import (
    external_feed_due,
    frost_rescue_target,
    idle_park,
    needs_mode_nudge,
)
from ..control.tpi_shadow import evaluate_tpi_shadow
from ..diagnostics.collector import DiagnosticsCollector
from ..diagnostics.shadows import (
    arbitration_shadow_objs,
    build_outcome_diag,
    capped_elapsed_min,
    compose_climate_band,
    evaluate_cover_shadow,
    evaluate_multi_shadow,
    lifecycle_shadow_objs,
    mpc_shadow_objs,
    neutral_shadow_objs,
    pi_shadow_objs,
    tpi_shadow_objs,
)
from ..diagnostics.trace import build_tick_record
from ..estimation.psychrometrics import humidity_ratio
from ..estimation.tau_settle import update_settle
from ..estimation.thermal_ekf import ThermalModel
from ..ingestion import parse_finite
from ..multi.model import DeviceHealth, Direction
from ..runtime.tick_inputs import TickInputs
from ..runtime.tick_result import (
    ActuatorPlan,
    AvailableTickData,
    ClimateBandResult,
    ClimateHumidityResult,
    EndHold,
    ExternalTemperaturePlan,
    FinalizeContext,
    HealthUpdate,
    HoldRoutingResult,
    IngestResult,
    IntentsResult,
    LifecycleFoldResult,
    ModeAdoptionResult,
    ModeNudgeResult,
    ModeResolutionResult,
    ObservationResult,
    OperativeResult,
    PersistencePhase,
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
from ..runtime.zone_runtime import ZoneRuntime
from ..safety.heating_failure import actuator_running
from ..safety.sensor_watchdog import (
    frozen_safe_target,
    unavailable_safe_engaged,
    valve_stuck,
)
from ..trace.recorder import TraceRecorder
from .actuator_executor import ActuatorExecutor
from .input_reader import InputReader, parse_attr_number
from .presenter import iso_utc as _iso_utc
from .presenter import present as _present

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    # The patch surface, imported for TYPING ONLY (see the module docstring).
    # These statements never run, so no name is bound in this module at
    # runtime and no second patch target is created; they exist so that
    # ``mypy --strict`` checks every ``self._g.<name>(...)`` call site against
    # the real signature instead of ``Any``.
    from ..comfort.dual_setpoint import decide as _t_comfort_decide
    from ..comfort.humidity import humidity_decide as _t_humidity_decide
    from ..control.cover_shading import (
        predict_peak_operative as _t_predict_peak_operative,
    )
    from ..control.cover_shading import (
        shading_target_position as _t_shading_target_position,
    )
    from ..control.optimal_start import plan_preheat as _t_plan_preheat
    from ..control.override import mode_adopt_reason as _t_mode_adopt_reason
    from ..control.override import setpoint_adopt_reason as _t_setpoint_adopt_reason
    from ..control.tick_resolve import resolve_desired_mode as _t_resolve_desired_mode
    from ..control.tick_resolve import resolve_write_target as _t_resolve_write_target
    from ..control.window_auto import effective_window_open as _t_effective_window_open
    from ..coordinator import PoiseCoordinator
    from ..estimation.psychrometrics import dewpoint as _t_psychro_dewpoint
    from ..ingestion import ingest_temperature as _t_ingest_temperature
    from ..multi.lifecycle import LifecyclePolicy as _t_LifecyclePolicy
    from ..multi.lifecycle import compressor_running as _t_compressor_running
    from ..multi.lifecycle import guard_block_reason as _t_guard_block_reason
    from ..multi.lifecycle import min_off_remaining as _t_min_off_remaining
    from ..multi.lifecycle import mode_hold_remaining as _t_mode_hold_remaining
    from ..multi.lifecycle import observe as _t_lifecycle_observe
    from ..multi.lifecycle import to_runtime as _t_to_runtime
    from ..multi.shadow import evaluate_thermal_shadow as _t_evaluate_thermal_shadow
    from ..safety.sensor_watchdog import is_frozen as _t_is_frozen

    class _LifecycleModule:
        """Static view of the ``multi.lifecycle`` MODULE object.

        ``_lifecycle`` is the one patch-surface entry that is a module, not a
        function, so it gets a typing-only mirror of exactly the members the
        moved bodies call.  Adding a ``self._g._lifecycle.<x>`` call means
        adding ``<x>`` here.
        """

        LifecyclePolicy = _t_LifecyclePolicy
        compressor_running = staticmethod(_t_compressor_running)
        guard_block_reason = staticmethod(_t_guard_block_reason)
        min_off_remaining = staticmethod(_t_min_off_remaining)
        mode_hold_remaining = staticmethod(_t_mode_hold_remaining)
        observe = staticmethod(_t_lifecycle_observe)
        to_runtime = staticmethod(_t_to_runtime)


# Comfort mode -> thermal-arbitration direction (ADR-0046 P1 shadow). "idle" and
# any other value map to None (no thermal demand).
_THERMAL_DIR: dict[str, Direction] = {"heat": Direction.HEAT, "cool": Direction.COOL}

# The published ``humidity_reason`` when the LIVE humidity segment failed
# (ADR-0065): the failure is named instead of the key silently vanishing.
_HUM_FAILED_REASON = "humidity block failed"

# ADR-0066 B.5: notification wording per reason token (English, concise —
# persistent notifications have no i18n rail; the stable token itself travels
# on the bus event for automations).
_VENT_REASON_TEXT = {
    "mold_risk": "sustained surface humidity, mould risk",
    "moisture_out": "outside air is drier, airing removes moisture",
    "co2": "CO₂ is elevated",
}


class _CoordinatorGlobals:
    """Call-time view onto the ``coordinator`` module's patch surface.

    Reading ``self._g.<name>`` is exactly ``getattr(coordinator_module, name)``
    evaluated at the moment of the call, so a
    ``patch("custom_components.poise.coordinator.<name>")`` installed after the
    coordinator was constructed is honoured — which is the whole point of not
    importing those names here (see the module docstring).

    The resolution is dynamic, the TYPES are not: the ``if TYPE_CHECKING``
    block below declares every patch-surface symbol with its real signature,
    so ``mypy --strict`` checks the call sites exactly as it did while the
    stages still lived in ``coordinator.py`` and read module-level imports.
    The declarations are erased at runtime (the block never executes), where
    ``__getattr__`` does the work.  A symbol that is NOT declared falls back to
    ``Any`` — so a new one must be added in three places: the ``noqa: F401``
    import in ``coordinator.py``, the typing-only import above and the
    declaration here.
    """

    __slots__ = ("_module",)

    if TYPE_CHECKING:
        comfort_decide = staticmethod(_t_comfort_decide)
        effective_window_open = staticmethod(_t_effective_window_open)
        evaluate_thermal_shadow = staticmethod(_t_evaluate_thermal_shadow)
        humidity_decide = staticmethod(_t_humidity_decide)
        ingest_temperature = staticmethod(_t_ingest_temperature)
        is_frozen = staticmethod(_t_is_frozen)
        mode_adopt_reason = staticmethod(_t_mode_adopt_reason)
        plan_preheat = staticmethod(_t_plan_preheat)
        predict_peak_operative = staticmethod(_t_predict_peak_operative)
        psychro_dewpoint = staticmethod(_t_psychro_dewpoint)
        resolve_desired_mode = staticmethod(_t_resolve_desired_mode)
        resolve_write_target = staticmethod(_t_resolve_write_target)
        setpoint_adopt_reason = staticmethod(_t_setpoint_adopt_reason)
        shading_target_position = staticmethod(_t_shading_target_position)
        _lifecycle: _LifecycleModule

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)


class TickOrchestrator:
    """Owns the per-tick program; one instance per ``PoiseCoordinator``.

    Constructed at the very end of ``PoiseCoordinator.__init__`` so every
    collaborator below already exists.  All of them are assigned exactly once
    in that ``__init__`` and never rebound, so snapshotting the references here
    cannot drift from the coordinator's own view.

    ``forecast_provider`` is deliberately NOT a collaborator: the forecast await
    keeps running through ``PoiseCoordinator._forecast_outdoor``, which stays a
    coordinator method because integration tests drive it directly.
    """

    __slots__ = (
        "_c",
        "_diag",
        "_executor",
        "_g",
        "_log",
        "_reader",
        "_runtime",
        "_trace_recorder",
        "_trace_slug",
    )

    def __init__(
        self,
        coordinator: PoiseCoordinator,
        *,
        coordinator_module: ModuleType,
        logger: logging.Logger,
        runtime: ZoneRuntime,
        input_reader: InputReader,
        actuator_executor: ActuatorExecutor,
        diag_collector: DiagnosticsCollector,
        trace_slug: str,
    ) -> None:
        # Transitional backreference for the config/tuning attributes and the
        # coordinator-owned commands — see the module docstring.
        self._c = coordinator
        # Call-time dispatch onto the coordinator module's patch surface.
        self._g = _CoordinatorGlobals(coordinator_module)
        # The coordinator module's own logger: the channel
        # ``custom_components.poise.coordinator`` is behaviour, so it is
        # injected rather than created here.
        self._log = logger
        self._runtime = runtime
        self._reader = input_reader
        self._executor = actuator_executor
        self._diag = diag_collector
        # The health checkpoint (``self._c._health.emit``) and the
        # persistence checkpoint (``self._c._maybe_save``) are deliberately
        # NOT snapshotted here — they are resolved through the coordinator
        # instance on every call (see the module docstring's dispatch rules).
        #
        # opt-in field-trace recorder (ADR-0011 golden-file replay); default
        # off, lazily constructed inside ``_maybe_record_trace``.
        self._trace_recorder: TraceRecorder | None = None
        self._trace_slug = trace_slug

    async def _maybe_record_trace(
        self,
        data: dict[str, Any],
        *,
        room: float,
        t_out: float,
        rh: float | None,
        t_rm: float | None,
        now: float,
    ) -> None:
        """Queue this tick for the opt-in field trace (ADR-0011 golden-file
        replay). Best-effort pure observation (ADR-0026): the EKF drive inputs +
        model snapshot make it replay-sufficient, and any failure is swallowed so
        trace capture can never disturb control.

        F-TRACEIO (phase 10): the record is still BUILT here, inside the
        swallow boundary — moving the build out would put a build failure on
        the tick's error path — but the file append is only ENQUEUED. It runs
        on a background drain task, so trace I/O no longer counts into
        ``tick_ms``. The method stays ``async`` because ``finalize_tick``
        dispatches it through the coordinator instance and test_phase8_presenter
        wraps it with an async spy.
        """
        if not self._c._trace_enabled:
            return
        try:
            if self._trace_recorder is None:
                path = self._c.hass.config.path(
                    "poise_traces", f"{self._trace_slug}.jsonl"
                )
                self._trace_recorder = TraceRecorder(
                    self._c.hass, path, DEFAULT_TRACE_MAX_BYTES
                )
            # The snapshot+build sequence lives in the pure
            # ``diagnostics.trace.build_tick_record``. The ``ts=`` clock read
            # precedes the snapshot build — a documented unobservable
            # micro-reorder, see the module docstring there.
            record = build_tick_record(
                data,
                self._runtime.learning.ekf,
                ts=dt_util.utcnow().timestamp(),
                mono=now,
                room=room,
                t_out=t_out,
                u_h=self._runtime.learning.last_u_h,
                u_c=self._runtime.learning.last_u_c,
                q_solar=self._runtime.learning.last_q_solar,
                rh=rh,
                t_rm=t_rm,
            )
            self._trace_recorder.enqueue(record.to_json_line())
        except Exception:  # noqa: BLE001 - trace capture must never break the tick
            self._log.debug("Poise trace capture failed", exc_info=True)

    async def flush_traces(self) -> None:
        """Unload checkpoint for the queued trace lines (F-TRACEIO).

        No-op when tracing was never switched on (no recorder was ever built).
        Swallowing is the caller's contract here too: an unload must not fail
        because a trace line could not be written.
        """
        if self._trace_recorder is None:
            return
        try:
            await self._trace_recorder.flush_on_unload()
        except Exception:  # noqa: BLE001 - trace capture must never break unload
            self._log.debug("Poise trace flush on unload failed", exc_info=True)

    async def _write_unavailable_safe_state(self) -> None:
        """Command the frost/mould floor after a sustained room-sensor loss.

        A heat-capable actuator degrades to the health floor in heat (frost
        protection held by its own sensor -- fail toward warmth); a cool-only
        actuator is commanded off (it must not cool the room to the floor).
        Mirrors the frozen-sensor safe state for a fully unavailable sensor.
        The floor is clamped up to the device ``min_temp`` so a high-min AC
        does not thrash on an echo it cannot honour. Best-effort + idempotent;
        a failure must never break the tick.

        This is the unavailable path's plan_actuation + apply + commit node —
        ``resolve_safe_state`` produces the ``SafeStatePlan`` (or None =
        already safe), the executor sequence applies it, the commit folds the
        stamps. The actuator read below is await-relative behaviour, so the
        plan cannot be resolved in the prepare phase.
        """
        # Positioned read: the dirty flush follows this write (F-SAVEPOINT,
        # ADR-0064), so this read sees the device state at tick start.
        act = self._reader.actuator_state()
        modes = (
            [str(m) for m in (act.attributes.get("hvac_modes") or [])] if act else []
        )
        # Decide mode + setpoint together (pure), so a device in cool/auto/off
        # actually receives the set_hvac_mode('heat') it needs and does not
        # keep cooling toward the floor. Mode and setpoint writes are
        # independent and each idempotent.
        plan = resolve_safe_state(
            hvac_modes=modes,
            device_state=act.state if act is not None else None,
            device_setpoint=parse_attr_number(act, "temperature"),
            device_min=parse_attr_number(act, "min_temp"),
            floor=FROST_FLOOR_C,
        )
        if plan is None:
            return  # already in the safe state -> no re-write (idempotent)
        # The executor sequence owns the ONE shared boundary (a mode dispatch
        # error skips the setpoint write; splitting the boundary is the open
        # F-SAFESEQ), both payloads (untagged; tagging is the open F-CONTEXT)
        # and the boundary log; the
        # commit right here folds the stamps. Mode part: ``last_written_mode``
        # only after a real nudge (our own safe-state mode is never a user
        # change — mode echo). Setpoint part: ``last_target``; clear the
        # adoption baseline (``last_written_sp=None``) so our own safe-state
        # setpoint is never re-read as a user hold on recovery;
        # ``_mark_actuated``. No timestamp on this path: the commit needs no
        # ``now=``.
        report = await self._executor.run_unavailable_safe(
            plan, entity_id=self._c._actuator, zone_name=self._c.zone_name
        )
        self._c.commit_execution(report)

    async def _run_once(self) -> dict[str, Any]:
        """One tick under the lock — the architecture-diagram target flow.

        ``prepare_until_forecast`` (owns the availability gate + snapshot) →
        unavailable short-circuit OR [forecast resolve if requested] →
        ``resume_prepare`` → ``TickPlan`` → pre_events → apply/commit →
        ``finalize_tick`` → [save] → present. The apply/commit node runs as an
        ORDERED multi-segment program INSIDE ``resume_prepare`` (each segment:
        plan → exec → commit at its position) because the one-block
        ``apply(plan)`` hoist is not provably unobservable — the per-dependency
        proofs live in ``resume_prepare``'s docstring. ``_async_update_data``
        keeps measuring the tick wall-time around this whole method.

        Stages collect ``HealthUpdate``s and the prepare flow emits them at
        stage-end checkpoints. A stage that aborts mid-body AFTER collecting
        updates raises ``TickStageError(cause, pending_health_updates)``; the
        handler below emits the pending updates (exactly the transitions the
        inline code had already written before the failure point) and
        re-raises the ORIGINAL exception object, so the failure counting and
        DataUpdateCoordinator's error handling in ``_async_update_data`` see
        the unchanged exception class/message/identity.
        """
        try:
            prep = self.prepare_until_forecast()
            if isinstance(prep, TickPlan):
                # Unavailable short-circuit: the plan carries the DIRTY_ONLY
                # persistence directive, and that checkpoint runs at the END
                # of the short-circuit (see ``_run_unavailable_tick``).
                return await self._run_unavailable_tick(prep)
            # Forecast handshake: the await runs under the tick lock, under
            # exactly the condition ``forecast_request`` exists iff the
            # ``predictive`` gate held -- and with the tick-current lead
            # horizon plus the fallback value. The await stays in the adapter
            # so the prepare phase itself performs no I/O; F-FORECAST
            # (phase 10) is the only place this may ever move.
            if prep.forecast_request is not None:
                forecast: float | None = await self._c._forecast_outdoor(
                    prep.forecast_request.horizon_min, prep.forecast_request.fallback
                )
            else:
                forecast = None
            plan = await self.resume_prepare(prep, forecast)

            # pre_events seam: the hold-expiry and preheat-edge events fire
            # IMMEDIATELY inside the prepare stages, synchronously under the
            # lock — and a synchronous bus listener MAY write coordinator
            # state that later prepare stages read. Deferring those fires to
            # this seam is therefore NOT provably unobservable; the events
            # keep firing at their in-stage positions and ``pre_events`` stays
            # an EMPTY structural seam.
            for event in plan.pre_events:
                self._c._fire_override_ended(event.reason)

            # apply → commit(post_actions) → CommitResult.events: already
            # executed as the ordered in-stage program (``resume_prepare``);
            # the frost-rescue segment fired its ``CommitResult.events`` after
            # the rescue writes.
            ctx = plan.finalize_context
            assert ctx is not None  # resume_prepare always builds it
            outcome = await self.finalize_tick(ctx)

            # INVARIANT (F-SAVEPOINT, phase 10): the checkpoint sits at the END
            # of the tick, AFTER ``finalize_tick``. A save therefore carries
            # the state and the metrics of the SAME tick — the compressor
            # lifecycle fold, the outcome/HDH/RegQ folds and the ref-offset /
            # tau-settle updates included — instead of the previous tick's.
            # Pinned by test_phase0_persistence_checkpoint.py.
            # Accepted trade-off: if ``finalize_tick`` raises, this tick saves
            # nothing. Nothing is lost — ``dirty`` is only cleared by a
            # successful save, so a pending user intent is written by the next
            # tick instead of this one.
            if plan.persistence is PersistencePhase.ALWAYS:
                await self._c._maybe_save()
            # ``present`` lives in ``ha/presenter.py`` — for the available
            # form it returns ``outcome.diagnostics`` AS THE SAME OBJECT
            # (aliasing contract), see the module docstring.
            return _present(outcome)
        except TickStageError as err:
            pending = err.pending_health_updates
            cause = err.cause
        # Stage-abort checkpoint (pinned by test_phase0_health_emission incl.
        # the delete direction, exercised by test_phase6_health_checkpoints):
        # emit the transported updates, then re-raise the original. POSITION
        # PROOF: exception unwinding — also through the async frames — is
        # synchronous, so this emission runs in the SAME event-loop turn as
        # the failure, with no suspension point between the "already emitted
        # before the failure" state and this checkpoint. The raise sits
        # OUTSIDE the except block so no implicit exception context is chained
        # onto ``cause`` — its ``__context__``/``__cause__``/
        # ``__suppress_context__`` stay exactly as they were at the original
        # raise site. Known residual (documented): the traceback frame list
        # of an abort WITH pending updates loses the intermediate stage-call
        # frames (the exception object is re-raised from here); class,
        # message and identity are unchanged, and aborts WITHOUT pending
        # updates propagate bare and byte-identically (stages only wrap when
        # they have something to transport — nothing else changed on the
        # failure path, and the inline ``try`` adds no frame).
        self._c._health.emit(pending)
        raise cause

    async def _run_unavailable_tick(self, plan: TickPlan) -> dict[str, Any]:
        """Unavailable short-circuit: safe-state plan/apply/commit →
        [DIRTY_ONLY save] → present(minimal).

        The anchor resets already ran inside ``prepare_until_forecast``. The
        ``SafeStatePlan`` is resolved inside ``_write_unavailable_safe_state``
        (that is why the short-circuit ``TickPlan.actuator_plan`` is None): its
        actuator read is await-relative and cannot move into the prepare phase.

        INVARIANT (F-SAVEPOINT, ADR-0064): the dirty flush runs at the END of
        this path, so the same tick persists both the pending user intent AND
        the ``has_actuated`` flip the safe-state write produces. Accepted
        consequences: the outage clock read and the safe-state actuator read
        happen a save-duration earlier than the flush (the safe state engages
        marginally sooner on a saving tick, and the plan is resolved against
        a marginally earlier device snapshot).
        """
        now_mono = self._runtime.clock.monotonic()
        if self._runtime.safety.unavailable_since is None:
            self._runtime.safety.unavailable_since = now_mono
        if not self._c._unavailable_logged:
            self._log.warning(
                "Poise %s: room temperature sensor %s is unavailable; "
                "holding the entity in its last state until it returns",
                self._c.zone_name,
                self._c._temp,
            )
            self._c._unavailable_logged = True
        # A sustained loss must not hold a stale comfort setpoint indefinitely
        # (critical in external-feed mode). After the timeout, degrade to the
        # frost/mould floor -- the same safe state as a frozen sensor (fail
        # toward warmth).
        engaged = unavailable_safe_engaged(
            now_mono - self._runtime.safety.unavailable_since,
            UNAVAILABLE_SAFE_AFTER_S,
        )
        if engaged:
            await self._c._write_unavailable_safe_state()
        # A user intent set via the switch/select (enabled / preset / mode)
        # while the room sensor is down must still be persisted — this path
        # never reaches the normal checkpoint. DIRTY_ONLY: no periodic cadence
        # save while the sensor is down, and positioned AFTER the safe-state
        # write so its ``has_actuated`` flip goes to disk with it (F-SAVEPOINT).
        if plan.persistence is PersistencePhase.DIRTY_ONLY and self._runtime.dirty:
            await self._c._maybe_save()
        # ``unavailable_safe`` is returned UNCONDITIONALLY once engaged —
        # independent of the safe plan (idempotent skip) and of dispatch
        # success.
        return _present(
            TickOutcome(
                data=UnavailableTickData(unavailable_safe=engaged),
                diagnostics={},
                trace_record=None,
            )
        )

    def prepare_until_forecast(self) -> PrepareContinuation | TickPlan:
        """Prepare phase up to the forecast seam — or the unavailable
        short-circuit.

        Owns the availability gate and the snapshot: on an unavailable tick
        it returns the short-circuit ``TickPlan`` (``persistence=DIRTY_ONLY``)
        right after the anchor resets — the ``actuator_plan`` is deliberately
        None because the safe-state decision needs an await-relative actuator
        read (see ``_run_unavailable_tick``). Otherwise the await-free prepare stages
        run (ingest -> observe -> safety floors -> schedule gate) and stop at
        the predictive decision; ``air`` stays the positioned pre-snapshot
        room read -- provably equal to ``inputs.room.value``
        (await-free-window proof) -- passed into the ingest stage so its body
        stays unchanged.

        Health checkpoints: the stages collect ``HealthUpdate``s and this
        orchestrator emits them at the stage-end checkpoints below. POSITION
        PROOF (valid for every checkpoint in this method): this entire phase
        is await-free, so between a stage's in-body emission point and its
        stage-end checkpoint no suspension point exists — on the
        single-threaded event loop no other task can interleave, and the
        registry sees the identical transitions in the identical order within
        the same loop turn. Residual (accepted): synchronous listeners of the
        repairs-registry-updated event run a few statements later in the same
        turn; that event is HA-internal housekeeping with no synchronous
        integration listeners — unlike the public ``poise_override_ended`` bus
        event, whose in-stage firing position is preserved (see
        ``_run_once``'s pre_events note).
        """
        # Positioned first read: the availability gate must run BEFORE the
        # pre-await snapshot — on an unavailable tick neither the guard
        # discovery nor any other read of the segment runs, and that error
        # path stays read-for-read identical.
        air = self._reader.read(self._c._temp)
        # Availability-gate checkpoint [1]: emitted at its EXACT statement
        # position (trivially position-identical), both directions. The
        # constraint holds by construction: the checkpoint lies BEFORE every
        # await of the tick and — on the unavailable path — BEFORE the
        # short-circuit return, hence before ``_run_once``'s persistence/apply
        # evaluation and the DIRTY_ONLY dirty-flush save.
        self._c._health.emit(
            (
                HealthUpdate(
                    issue_id=f"sensor_unavailable_{self._c._entry_id}",
                    active=air is None,
                    translation_key="sensor_unavailable",
                    placeholders={"entity": self._c._temp},
                ),
            )
        )
        if air is None:
            # A fully unavailable room sensor is at least as untrustworthy as
            # an open window or a frozen reading, so it must drop the same
            # learning/window-auto anchors as the pause branch below --
            # otherwise the eventual reconnect re-anchors
            # ``_last_mono``/``_prev_room_mono`` across the whole outage and
            # the EKF integrates a real-looking dt over an interval it never
            # actually observed (ADR-0012/0024). The slope detector's own
            # reference point is reset too (``_wa_ref_*``, ``_wa_prev_mono``):
            # letting it survive an outage would let the next good sample
            # compute a rate/dt across the *sensor* gap rather than real room
            # movement, which is exactly the false-open risk the
            # quantized-slope anchor was built to avoid.
            self._runtime.learning.last_mono = None
            self._runtime.learning.prev_room = None
            self._runtime.learning.prev_room_mono = None
            self._runtime.learning.heatup_acc.reset()
            self._runtime.window.wa_ref_room = None
            self._runtime.window.wa_ref_mono = None
            self._runtime.window.wa_prev_mono = None
            return TickPlan(
                actuator_plan=None,
                external_temperature_plan=None,
                pre_events=(),
                post_actions=(),
                persistence=PersistencePhase.DIRTY_ONLY,
                control_data={},
                finalize_context=None,
            )
        self._runtime.safety.unavailable_since = None
        if self._c._unavailable_logged:
            self._log.info(
                "Poise %s: room temperature sensor %s is back; resuming control",
                self._c.zone_name,
                self._c._temp,
            )
            self._c._unavailable_logged = False
        # ONE snapshot bundles the contiguous pre-first-await read block.
        # Within this await-free segment nothing can change between reads, so
        # the re-read of the room here is provably the value the gate above
        # saw, and the segment's ad-hoc clock reads unify onto the snapshot
        # instants (sub-ms, unobservable). Every read AFTER the first await
        # stays a positioned InputReader call at exactly its place in the tick.
        inputs = self._reader.snapshot()
        ing = self._stage_ingest(inputs, air)
        # Ingest checkpoint [2-8]: the seven device-health updates, emitted at
        # the stage boundary within the same await-free segment (position
        # proof in the docstring above).
        self._c._health.emit(ing.health_updates)
        obs = self._stage_observe(inputs, ing)
        # Observe checkpoint: window_sensor_unavailable, emitted mid-stage
        # before the reset — same await-free-segment proof.
        self._c._health.emit(obs.health_updates)
        floors = self._stage_safety_floors(ing)
        # Safety-floors checkpoint: mould_protection_inactive, emitted at the
        # end of the block — same proof.
        self._c._health.emit(floors.health_updates)
        gate = self._stage_schedule_gate(inputs, ing, obs)
        return PrepareContinuation(
            forecast_request=gate.forecast_request,
            prepared_state=PreparedState(
                inputs=inputs,
                ingest=ing,
                observation=obs,
                floors=floors,
                sched=gate.sched,
            ),
        )

    def _stage_ingest(self, inputs: TickInputs, air: float) -> IngestResult:
        """Health flags + temperature/environment ingest.

        Body in ``tick_pipeline.stage_ingest`` via the runtime (incl. the
        device-health evaluation, whose InputReader DISCOVERY entity ids —
        static bootstrap results, no live read — are injected here).
        ``is_frozen`` (patch surface for test_phase0_safety_precedence) and
        ``ingest_temperature`` (test_phase6_health_checkpoints) dispatch
        through THIS module's globals at call time, so patches on
        ``custom_components.poise.coordinator`` keep hitting every call.
        """
        reader = self._reader
        return self._runtime.stage_ingest(
            inputs,
            air,
            entry_id=self._c._entry_id,
            temp_entity=self._c._temp,
            actuator_entity=self._c._actuator,
            sched_entity=reader.sched_entity,
            adaptive_mode_entity=reader.adaptive_mode_entity,
            fault_entity=reader.fault_entity,
            battery_entity=reader.battery_entity,
            is_frozen_fn=self._g.is_frozen,
            ingest_temperature_fn=self._g.ingest_temperature,
        )

    def _stage_observe(
        self, inputs: TickInputs, ing: IngestResult
    ) -> ObservationResult:
        """Window signals, capability, dynamics retune, EKF learn gate and
        window-auto observation.

        Body in ``tick_pipeline.stage_observe`` via the runtime (learn,
        window-auto and seasonless observations). ``effective_window_open``
        (test_phase6_health_checkpoints) dispatches through THIS module's
        globals at call time; the module ``_LOGGER`` is injected so both
        swallow-boundary records keep the channel
        ``custom_components.poise.coordinator``.
        """
        return self._runtime.stage_observe(
            inputs,
            ing,
            entry_id=self._c._entry_id,
            windows=self._c._windows,
            actuator_entity=self._c._actuator,
            window_auto_cfg=self._c._window_auto_cfg,
            adaptive_cool_cfg=self._c._adaptive_cool_cfg,
            dynamics_override=self._c._dynamics_override,
            effective_window_open_fn=self._g.effective_window_open,
            set_mpc_params=self._c._set_mpc_params,
            logger=self._log,
        )

    def _stage_safety_floors(self, ing: IngestResult) -> SafetyFloorsResult:
        """Mould floor + dewpoint cap from humidity.

        Body in ``tick_pipeline.stage_safety_floors`` via the runtime;
        ``psychro_dewpoint`` (test_phase6_health_checkpoints) dispatches
        through THIS module's globals at call time.
        """
        return self._runtime.stage_safety_floors(
            ing,
            entry_id=self._c._entry_id,
            humidity_entity=self._c._humidity,
            psychro_dewpoint_fn=self._g.psychro_dewpoint,
        )

    def _stage_schedule_gate(
        self, inputs: TickInputs, ing: IngestResult, obs: ObservationResult
    ) -> ScheduleGateResult:
        """Schedule state + predictive decision -- the forecast seam.

        Body in ``tick_pipeline.stage_schedule_gate`` via the runtime (no
        patch surface; config schedule/optimal-start/-stop injected).
        """
        return self._runtime.stage_schedule_gate(
            inputs,
            ing,
            obs,
            schedule=self._c._schedule,
            optimal_start=self._c._optimal_start,
            optimal_stop=self._c._optimal_stop,
        )

    async def resume_prepare(
        self, prep: PrepareContinuation, forecast: float | None
    ) -> TickPlan:
        """Prepare phase after the forecast seam, through the write path;
        returns the tick's ``TickPlan``.

        Continues at the post-await position. The actuation is an ORDERED
        multi-segment program — Nudge-Plan→Nudge-Exec+Commit → Echo/Adoption
        → Setpoint-Gate/Plan→Setpoint-Exec+Commit →
        Ext-Temp-Read/Plan→Exec+Commit (or, on the disabled/off-held path,
        Rescue-Plan→Exec+Commit+Events) — NOT one ``apply(plan)`` block after
        all decisions. Reorder verdict, one proof-of-dependency per segment
        boundary (all verified against the executed code):

        1. The §4 regulation throttle (``_stage_setpoint_observe``) reads
           ``runtime.user.override`` AFTER the mode-nudge await, while the
           guard's ``is_safety`` gate (``_stage_mode_nudge``) reads it BEFORE
           that await. ``set_override`` is synchronous and lock-free — a user
           service call landing during the nudge dispatch is seen by the
           throttle but not by the guard. Both read positions are
           load-bearing → the nudge exec cannot move behind the setpoint
           decision, nor the decision ahead of the nudge.
        2. The setpoint write gate reads ``runtime.user.mode_override`` after
           the nudge await (same concurrency window, plus this-tick mutations
           by ``_stage_mode_adoption``'s ``_set_mode_override``/
           ``_end_hold``) → the gate stays after nudge + adoption.
        3. The adoption (``_stage_setpoint_adopt``) is a domain mutation
           BETWEEN the writes: ``set_override`` stamps the hold expiry with
           ``dt_util.utcnow()`` — wall time advanced by the nudge-dispatch
           duration is observable in ``override_expires_at`` — and moves
           the echo baselines (``runtime.external.pre_write_sp``/
           ``last_written_sp``/``last_sp_write_ts``/``prev_device_sp``) the
           write gate and next tick consume (the adopted setpoint skips this
           tick's write).
        4. The ext-temp select state is a positioned FRESH read after the
           mode/setpoint awaits → the ext segment stays last.

        The positioned post-await reads keep their places INSIDE their stages
        (presence, ext-feed probe, THE actuator read, device_min, the
        ext-select fresh read). Ends with the fully built ``TickPlan``.
        """
        state = prep.prepared_state
        inputs = state.inputs
        ing = state.ingest
        obs = state.observation
        floors = state.floors
        sched = state.sched
        # The two arms of the ``if predictive:`` seam (the await itself moved
        # to ``_run_once``): ``forecast`` is non-None on the request arm --
        # ``_forecast_outdoor`` returns ``fallback`` on every failure -- so
        # the degenerate mypy guard degrades to exactly that same fallback
        # value and is unreachable in practice.
        if prep.forecast_request is not None:
            t_out_lead = forecast if forecast is not None else ing.t_out_eff
            model: ThermalModel | None = self._runtime.learning.ekf.get_model()
        else:
            t_out_lead, model = ing.t_out_eff, None
        sp = self._stage_schedule_presence(
            ing, obs, sched, t_out_lead=t_out_lead, model=model
        )
        op = self._stage_operative_mode(inputs, ing)
        # Operative checkpoint: operative_unsupported, emitted mid-stage.
        # POSITION PROOF: that position and this checkpoint sit in the SAME
        # await-free window (between the forecast await and the
        # failure-detect/mode-nudge dispatches) — no suspension point between
        # them, so no other task can interleave; same
        # single-thread/registry-listener rationale as the prepare
        # checkpoints (``prepare_until_forecast`` docstring).
        self._c._health.emit(op.health_updates)
        lvl = self._stage_presence_level(ing, obs, sched, sp)
        decision = self._stage_comfort_solve(ing, obs, floors, sp, op, lvl)
        wt = self._stage_write_target(ing, obs, floors, op, decision)
        band = self._stage_climate_band(ing, obs, sp, lvl, op, decision, wt)
        intents = self._stage_intents(ing, obs, wt)
        # ``_notify_failure``'s body is purely synchronous (awaiting a
        # never-suspending coroutine runs it to completion on the calling task
        # without yielding to the loop), so the plain call is
        # scheduling-identical at this position.
        failed = self._stage_failure_detect(ing, wt, intents)
        # ADR-0068 U6: the fan-first FSM — computed BEFORE the mode
        # resolution so its candidate can intercept a NORMAL cool at the
        # seam (the seam re-derives the provenance and stays the single mode
        # authority). Defensive: comfort glue must never break the tick.
        _ff = FanFirstDecision(state=FanFirstState(), command="none", reason="disabled")
        _ff_requested = False
        _act_ff = wt.act_state
        _fan_modes_ff: tuple[str, ...] = ()
        _device_fan_ff: str | None = None
        _foreign_fan_ff = False
        _presence_ok_ff = False
        try:
            _fan_modes_ff = (
                tuple(_act_ff.attributes.get("fan_modes") or ())
                if _act_ff is not None
                else ()
            )
            _device_fan_ff = (
                _act_ff.attributes.get("fan_mode") if _act_ff is not None else None
            )
            _own_fan_ff = (
                _act_ff is not None
                and _act_ff.context is not None
                and _act_ff.context.id in self._runtime.external.own_write_ctx_ids
            )
            _foreign_fan_ff = observe_fan_foreign(
                self._runtime.external,
                device_fan=_device_fan_ff,
                own_change=_own_fan_ff,
                now=ing.now,
            )
            note_device_fan(
                self._runtime.external, device_fan=_device_fan_ff, now=ing.now
            )
            _occ_ff = sp.presence.occupancy
            _presence_ok_ff = presence_control_ready(_occ_ff) and room_present(_occ_ff)
            if self._c._active_comfort:
                _ff = fan_first_decision(
                    self._runtime.latches.fan_first,
                    now=ing.now,
                    cool_requested=wt.mode == "cool",
                    fan_first_allowed=(
                        not obs.window_open
                        and not ing.frozen
                        and self._runtime.user.override is None
                        and self._runtime.user.mode_override is None
                    ),
                    fan_only_capable=(
                        "fan_only"
                        in (
                            (_act_ff.attributes.get("hvac_modes") or [])
                            if _act_ff is not None
                            else []
                        )
                    ),
                    observed_hvac_mode=_act_ff.state if _act_ff is not None else None,
                    observed_hvac_action=(
                        _act_ff.attributes.get("hvac_action")
                        if _act_ff is not None
                        else None
                    ),
                    observed_fan_mode=_device_fan_ff,
                    advertised_modes=_fan_modes_ff,
                    operative_c=op.room_decide,
                    room_c=ing.room,
                    presence_ok=_presence_ok_ff,
                    window_open=obs.window_open,
                    in_comfort_window=sched.is_comfort,
                    foreign_fan_change=_foreign_fan_ff,
                )
            self._runtime.latches.fan_first = _ff.state
            self._runtime.diagnostics.fan_first_reason = _ff.reason
            _ff_requested = _ff.command == "fan_only" or _ff.state.phase in (
                "await_fan_only",
                "await_stage",
                "dwell",
            )
        except Exception:  # noqa: BLE001 - fan glue must never break the tick
            self._log.debug("Poise fan-first evaluation failed", exc_info=True)
        res = self._stage_mode_resolution(
            ing, obs, op, wt, band, fan_first_requested=_ff_requested
        )
        routing = self._stage_hold_routing(wt)
        # Branch-dependent values: the defaults from the resolution and
        # routing stages hold on the disabled / off-held path; the enabled
        # path's stages return the updated values.
        guard_block = res.guard_block
        mode_nudge_blocked = res.mode_nudge_blocked
        mode_adopt_reason = routing.mode_adopt_reason
        sp_adopt_reason = routing.sp_adopt_reason
        actuator_plan: ActuatorPlan | None = None
        ext_plan: ExternalTemperaturePlan | None = None
        if self._runtime.user.enabled and not routing.off_held:
            adoption = self._stage_mode_adoption(ing, obs, wt, res, routing)
            mode_adopt_reason = adoption.mode_adopt_reason
            nudge = await self._stage_mode_nudge(
                ing, obs, wt, res, adoption, mode_nudge_blocked=mode_nudge_blocked
            )
            guard_block = nudge.guard_block
            mode_nudge_blocked = nudge.mode_nudge_blocked
            # ADR-0068 U6: the fan-stage write of the fan-first sequence
            # (echo-gated by the FSM: only after fan_only was OBSERVED) and
            # the ADR-0053 idle circulation over the SAME single path —
            # exactly one live path moves the fan.
            _fan_cmd: str | None = None
            if _ff.command == "stage" and _ff.state.stage is not None:
                _fan_cmd = _ff.state.stage
            elif _ff.restore_stage is not None:
                # Exit restore (field decision): put the stage back to the
                # pre-sequence value ("auto" fallback) — once, never fighting.
                _fan_cmd = _ff.restore_stage
            elif (
                self._c._active_comfort
                and _ff.state.phase == "idle"
                and _act_ff is not None
                and _act_ff.state == "fan_only"
                and not _foreign_fan_ff
                and _presence_ok_ff
                and band.climate_diag.get("fan_circ_shadow") == "fan_low"
                and "low" in {m.lower() for m in _fan_modes_ff}
                and (_device_fan_ff or "").lower() != "low"
                and self._runtime.external.last_commanded_fan != "low"
            ):
                _fan_cmd = "low"
            if _fan_cmd is not None:
                fan_report = await self._executor.run_fan_write(
                    self._c._actuator,
                    _fan_cmd,
                    fan_changed=(_fan_cmd != self._runtime.external.last_commanded_fan),
                )
                self._c.commit_execution(fan_report, now=ing.now)
            spo = self._stage_setpoint_observe(ing, obs, wt, res, routing, nudge)
            sp_adopt_reason = self._stage_setpoint_adopt(
                ing, obs, routing, spo, mode_adopt_reason=mode_adopt_reason
            )
            actuator_plan = await self._stage_setpoint_write(
                ing, wt, res, adoption, nudge, spo
            )
            ext_plan = await self._stage_ext_temp_feed(ing, op)
        else:
            actuator_plan = await self._stage_frost_rescue(
                ing, obs, floors, wt, routing
            )
        ctx = self._build_finalize_context(
            state=state,
            sp=sp,
            op=op,
            decision=decision,
            wt=wt,
            band=band,
            intents=intents,
            failed=failed,
            res=res,
            guard_block=guard_block,
            mode_nudge_blocked=mode_nudge_blocked,
            mode_adopt_reason=mode_adopt_reason,
            sp_adopt_reason=sp_adopt_reason,
        )
        # TickPlan assembly — pure frozen construction like the
        # FinalizeContext build above (same reorder proof: only
        # already-computed stage values, no ``self`` reads, no I/O, no
        # logging). ``pre_events``/``post_actions`` are EMPTY structural
        # seams: the expiry/preheat events fired at their in-stage positions
        # (deferral has no unobservability proof, see ``_run_once``) and the
        # rescue ``EndHold`` was applied by the rescue segment's own commit
        # (its events fired there too — Rescue-Plan→Exec+Commit+Events).
        # ``control_data`` stays empty: the FinalizeContext is the live
        # handover; the presenter/collector split populates it.
        return TickPlan(
            actuator_plan=actuator_plan,
            external_temperature_plan=ext_plan,
            pre_events=(),
            post_actions=(),
            persistence=PersistencePhase.ALWAYS,
            control_data={},
            finalize_context=ctx,
        )

    def _stage_schedule_presence(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sched: ScheduleState,
        *,
        t_out_lead: float,
        model: ThermalModel | None,
    ) -> SchedulePresenceResult:
        """House-presence gate, timed-state expiry, preheat/coast plan
        (ADR-0058/0059, ADR-0025/0034).

        INVARIANT (pinned): the timed-state expiry runs BEFORE the preset is
        read (``_expire_timed_states`` before ``_base_preset``); the presence
        read is the positioned read AFTER the forecast await.
        """
        room = ing.room
        can_heat = obs.can_heat
        lo, hi = HEATING_LOWER[self._c._category], HEATING_UPPER[self._c._category]

        # ADR-0058 presence coupling. Resolve the house gate BEFORE the preheat
        # plan: an empty house (home is False) or a manual Away preset means
        # "away", whose depth is carried by the Eco band-widen below (not a base
        # shift), so we feed a NEUTRAL preset base into the plan to avoid a
        # cooling-edge double-dip, and an empty house is never preheated.
        # Positioned read AFTER the forecast await: a presence flip during the
        # fetch is observable and must remain so. The reader resolves the
        # presence tristates (a person/device_tracker reporting a named zone
        # is a confident "not home"); home and occupancy sit in the same
        # await-free window, so the merged PresenceSnapshot read is equivalent.
        _presence = self._reader.read_presence()
        _home = any_present(_presence.home)
        # ADR-0059 §1/§2: expire the timed Boost + manual hold here, once the house
        # gate is known and before the preset/override feed the plan and solver. A
        # Boost restore must land before _is_away/_base_preset read the preset.
        self._c._expire_timed_states(_home)
        _is_away = self._runtime.user.preset is OverrideMode.AWAY or _home is False
        _base_preset = OverrideMode.NONE if _is_away else self._runtime.user.preset
        _comfort_target = mode_comfort_base(
            _base_preset, self._c._comfort_base, self._c._override_cfg
        )
        plan = self._g.plan_preheat(
            comfort_base=_comfort_target,
            is_comfort=sched.is_comfort,
            setback_offset=sched.setback_offset,
            minutes_to_comfort=float(sched.minutes_to_comfort),
            optimal_start_enabled=self._c._optimal_start and not _is_away,
            can_heat=can_heat,
            identified=self._runtime.learning.ekf.identified,
            model=model,
            room=room,
            t_out_lead=t_out_lead,
            heat_lower=lo,
            heat_upper=hi,
            optimal_stop_enabled=self._c._optimal_stop,
            minutes_to_setback=float(sched.minutes_to_setback),
            coast_lower=lo,
            was_preheating=self._runtime.latches.was_preheating,
            was_coasting=self._runtime.latches.was_coasting,
            max_lead_h=PROFILES[self._runtime.compressor.dynamics].max_lead_h,
        )
        base = plan.base
        preheating = plan.preheating
        preheat_outdoor = plan.preheat_outdoor
        coasting = plan.coasting
        # ADR-0059 §3: end a schedule-hold the moment optimal-start *begins*
        # preheating toward the comfort window its expiry points at, when the
        # preheat target is warmer than the held value -- so the room is warm at
        # comfort time instead of the hold clamping the preheat into a cold
        # block-start (Danfoss schedule_with_preheat). Rising edge only (so a hold
        # set *during* an active preheat is respected); runs before the latch below.
        if self._runtime.user.override is not None and hold_ends_at_preheat(
            policy=self._c._override_policy,
            preheat_started=preheating and not self._runtime.latches.was_preheating,
            expiry_is_switchpoint=self._runtime.user.override_expiry_is_switchpoint,
            preheat_target=_comfort_target,
            held_value=self._runtime.user.override,
        ):
            self._c._end_hold("schedule_point")
        # ADR-0025/0034 latch: carry this tick's engage state to the next tick so
        # the planner can hold instead of re-chattering at the deadline boundary.
        self._runtime.latches.was_preheating = preheating
        self._runtime.latches.was_coasting = coasting
        return SchedulePresenceResult(
            home=_home,
            presence=_presence,
            base=base,
            preheating=preheating,
            preheat_outdoor=preheat_outdoor,
            coasting=coasting,
        )

    def _stage_operative_mode(
        self, inputs: TickInputs, ing: IngestResult
    ) -> OperativeResult:
        """Operative TRV-input mode (ADR-0029). The ext-feed target probe is
        the positioned read after the forecast await.

        operative_unsupported is collected at its evaluation position and
        returned for the stage-end checkpoint; the ``TickStageError`` wrap
        transports it out of a mid-body abort (empty-pending aborts propagate
        bare).
        """
        pending: list[HealthUpdate] = []
        try:
            room = ing.room
            t_mrt = ing.t_mrt
            # operative TRV-input mode (ADR-0029): write the operative target
            # and feed the operative temperature, IF the thermostat can be
            # calibrated to an external sensor (i.e. a valid
            # external-temperature input). Otherwise fall back to air-side
            # control and flag a repair issue (fault tolerance).
            # external-temp input: explicit config, else auto-detected on the
            # device (pavax-verified). The number is write-only, so a
            # "unknown" state is fine; only "unavailable" means the device is
            # offline (ADR-0029).
            ext_num = self._c._trv_ext_temp or (
                inputs.device_guards.ext_temp_number
                if self._c._operative_input
                else None
            )
            # Positioned read: the feed target's availability is probed here,
            # after the forecast await.
            ext_ok = self._reader.ext_feed_target_ok(ext_num)
            operative_active = self._c._operative_input and ext_ok
            pending.append(
                HealthUpdate(
                    issue_id=f"operative_unsupported_{self._c._entry_id}",
                    active=self._c._operative_input and not ext_ok,
                    translation_key="operative_unsupported",
                    placeholders={"entity": ext_num or "—"},
                )
            )
            if operative_active:
                room_decide = operative_temperature(room, t_mrt)
                t_mrt_decide: float | None = None  # MRT lives in the fed values
            else:
                room_decide = room
                t_mrt_decide = t_mrt
            return OperativeResult(
                ext_num=ext_num,
                ext_ok=ext_ok,
                operative_active=operative_active,
                room_decide=room_decide,
                t_mrt_decide=t_mrt_decide,
                health_updates=tuple(pending),
            )
        except BaseException as err:  # transport-only; unwrapped in _run_once
            if pending:
                raise TickStageError(err, tuple(pending)) from err
            raise

    def _stage_presence_level(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sched: ScheduleState,
        sp: SchedulePresenceResult,
    ) -> PresenceLevelResult:
        """Presence level, room absence, window episode, eco widen (ADR-0058)."""
        now = ing.now
        window_open = obs.window_open
        preheating = sp.preheating
        _presence = sp.presence
        _home = sp.home
        # ADR-0058: resolve the presence level (the house gate is already folded
        # into _is_away above). Room-absence only modulates inside the comfort
        # window and never overrides a preheat. Level -> (occupied, eco_widen,
        # cool ceiling): COMFORT keeps the base behaviour; ROOM_ECO widens by the
        # Eco delta capped at the cool hard cap; AWAY widens by the away offset up
        # to the device max. No base shift -- the widen carries the whole depth.
        _presence_now = dt_util.utcnow().timestamp()
        _room_present = any_present(_presence.occupancy)
        self._runtime.presence.room_absent_since = step_room_absence(
            self._runtime.presence.room_absent_since,
            present=_room_present,
            now=_presence_now,
        )
        _absent_min = (
            (_presence_now - self._runtime.presence.room_absent_since) / 60.0
            if self._runtime.presence.room_absent_since is not None
            else 0.0
        )
        _level = resolve_presence(
            home=_home,
            room_absent_min=_absent_min,
            is_comfort=sched.is_comfort,
            preheating=preheating,
            cfg=self._c._presence_cfg,
        )
        # ADR-0059 §5: cache the presence level + window state so a user setpoint
        # nudge recorded in set_override (no tick context) can skip AWAY/window.
        self._runtime.presence.last_presence_level = _level.value
        # Track the rising edge of the open-window episode on the tick's
        # monotonic clock (``now``) so the mould floor can be suppressed for
        # its first WINDOW_MOULD_SUPPRESS_S below.
        if window_open:
            if self._runtime.window.window_open_since is None:
                self._runtime.window.window_open_since = now
        else:
            self._runtime.window.window_open_since = None
        self._runtime.window.last_window_open = window_open
        _eco_widen: float
        _cool_ceiling: float | None
        if _level is PresenceLevel.AWAY:
            _occupied = False
            _eco_widen = self._c._override_cfg.away_offset
            _cool_ceiling = DEVICE_MAX_C
        elif _level is PresenceLevel.ROOM_ECO:
            _occupied = False
            _eco_widen = self._c._presence_cfg.eco_delta
            _cool_ceiling = self._c._cool_hard_cap
        else:  # COMFORT
            _occupied = sched.is_comfort or preheating
            _eco_widen = 0.0
            _cool_ceiling = None
        return PresenceLevelResult(
            level=_level,
            absent_min=_absent_min,
            occupied=_occupied,
            eco_widen=_eco_widen,
            cool_ceiling=_cool_ceiling,
        )

    def _stage_comfort_solve(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        sp: SchedulePresenceResult,
        op: OperativeResult,
        lvl: PresenceLevelResult,
    ) -> ComfortDecision:
        """The central comfort solver (already pure).

        Body in ``tick_pipeline.stage_comfort_solve`` via the runtime;
        ``comfort_decide`` (patch surface for test_phase0_health_emission and
        test_review_v161_fixes) dispatches through THIS module's globals at
        call time — resolved per call, never bound at construction, so patches
        keep hitting.
        """
        return self._runtime.stage_comfort_solve(
            ing,
            obs,
            floors,
            sp,
            op,
            lvl,
            category=self._c._category,
            cool_min_outdoor=self._c._cool_min_outdoor,
            cool_lockout_enabled=self._c._cool_lockout_enabled,
            heat_max_outdoor=self._c._heat_max_outdoor,
            heat_lockout_enabled=self._c._heat_lockout_enabled,
            priority=self._c._priority,
            cool_hard_cap=self._c._cool_hard_cap,
            comfort_decide_fn=self._g.comfort_decide,
        )

    def _stage_write_target(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        op: OperativeResult,
        decision: ComfortDecision,
    ) -> WriteTargetResult:
        """Actuator snapshot, cool raise, idle park, write-target resolution
        and frozen degradation (ADR-0051).

        ``act_state`` is THE central positioned actuator read (after the
        forecast await); safety-beats-override (frozen) replaces the resolved
        target.
        """
        now = ing.now
        frozen = ing.frozen
        t_out_eff = ing.t_out_eff
        t_rm_eff = ing.t_rm_eff
        window_open = obs.window_open
        can_heat = obs.can_heat
        can_cool = obs.can_cool
        device_max = obs.device_max
        mold_min = floors.mold_min
        room_decide = op.room_decide
        # Positioned read: THE central actuator read stays exactly here, after
        # the forecast await — a device change during the fetch is observable;
        # every later attribute access this tick reads this ONE State object,
        # never a fresh read.
        act_state = self._reader.actuator_state()
        # A genuinely offline actuator (state=="unavailable") reports no
        # trustworthy setpoint, so should_write()'s "actual is None -> write"
        # rule would fire on EVERY tick -- a write storm into a dead
        # Zigbee/MQTT device. Setpoint (and mode-nudge) writes are gated on
        # this below.
        _actuator_online = act_state is not None and act_state.state != "unavailable"
        # ADR-0051 activation: on a hot day raise the cooling setpoint toward the
        # EN adaptive upper (capped; the default ASR-26 cap makes it a no-op
        # until the cap is raised), rate-limited <=0.5 K/tick. Cooling-only:
        # decide_mode gates "cool" on can_cool, so a heat-only TRV never sees it.
        eff_cool = decision.cool_sp
        _cool_ac = None
        try:
            _cool_ac = adaptive_cool_setpoint(
                cool_sp_en=decision.cool_sp,
                t_out_smooth=t_out_eff,
                t_rm=t_rm_eff,
                category=self._c._category,
                device_max=device_max,
                hard_cap=self._c._cool_hard_cap,
                delta_k=self._c._thermal_shock_delta,
            )
            eff_cool = rate_limit(
                self._runtime.latches.cool_sp_eff_prev, _cool_ac.cool_sp_eff, 0.5
            )
            self._runtime.latches.cool_sp_eff_prev = eff_cool
        except Exception:  # noqa: BLE001 - the cool raise must never break the tick
            self._log.debug("Poise cool-raise activation failed", exc_info=True)
        # Idle-park: when idle, park toward the edge the room is closest to —
        # a warm reversible AC parks in cool at the cool edge, not in heat at
        # the low heat idle-hold (which needs a many-K drop to act and never
        # responds to a warming room). ONE decision drives both the written
        # value and the mode nudge (idle_park_mode below) so they never
        # disagree; a heat-only TRV always parks in heat (can_cool False ->
        # unchanged).
        _idle_park_mode: str | None = None
        if decision.mode == "cool":
            cool_write = eff_cool
        elif decision.mode == "idle":
            _idle_park_mode, cool_write = idle_park(
                room=room_decide,
                heat_sp=decision.heat_sp,
                cool_sp=eff_cool,
                can_heat=can_heat,
                can_cool=can_cool,
                can_fan_only=(
                    act_state is not None
                    and "fan_only" in (act_state.attributes.get("hvac_modes") or [])
                ),
                current_mode=act_state.state if act_state else None,
            )
        else:
            cool_write = decision.write_setpoint
        # DIN 4108-2 is a steady-state criterion. Under an open window the
        # write target collapses to the floor (= max(frost, mould)); a humid
        # room would then heat toward ~24 C against the ventilation. Suppress
        # only the mould component for the first WINDOW_MOULD_SUPPRESS_S of the
        # episode -- the frost floor (FROST_FLOOR_C) is NEVER suppressed.
        # Diagnostics keep the real ``mold_min`` (see the ``mould_floor``
        # attribute below).
        mold_min_write = (
            None
            if (
                window_open
                and self._runtime.window.window_open_since is not None
                and (now - self._runtime.window.window_open_since)
                < WINDOW_MOULD_SUPPRESS_S
            )
            else mold_min
        )
        wt = self._g.resolve_write_target(
            window_open=window_open,
            override=self._runtime.user.override,
            heat_sp=decision.heat_sp,
            cool_sp=eff_cool,
            write_setpoint=cool_write,
            comfort_mode=decision.mode,
            frost_floor=FROST_FLOOR_C,
            mold_min=mold_min_write,
            device_max=device_max,
            # Fresh read — same await-free window as the central actuator
            # read above.
            device_min=self._reader.device_min(),
        )
        target, mode, norm_binding = wt.target, wt.mode, wt.norm_binding
        binding_precedence = wt.binding_precedence
        # Surface a silently band-clamped manual override (moot when frozen,
        # where the frost floor below replaces the override target entirely).
        override_clamped = wt.override_clamped and not frozen
        if frozen:
            # The room sensor is stale -> do not chase a comfort target on a
            # dead value. A heat-capable device degrades to the health floor
            # in heat (frost protection, held by the actuator's own sensor,
            # fail toward warmth); a cool-only device must NOT be pinned to
            # the floor in cool (it would cool the room to ~7 C) -> command off.
            if can_heat:
                target = frozen_safe_target(FROST_FLOOR_C, mold_min)
                mode = "heat"
            else:
                mode = "off"
            self._runtime.actuator.last_target = target
        return WriteTargetResult(
            act_state=act_state,
            actuator_online=_actuator_online,
            cool_ac=_cool_ac,
            idle_park_mode=_idle_park_mode,
            eff_cool=eff_cool,
            target=target,
            mode=mode,
            norm_binding=norm_binding,
            binding_precedence=binding_precedence,
            override_clamped=override_clamped,
        )

    def _stage_climate_band(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sp: SchedulePresenceResult,
        lvl: PresenceLevelResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
    ) -> ClimateBandResult:
        """Comfort stage, climate band — TWO independent boundaries
        (ADR-0065).

        ADR-0050/0051: a mostly-diagnostic block, but NOT "no writes" — the
        humidity action it computes drives the LIVE dry mode-nudge
        (mode_arbitration). Each half owns its boundary: a failing humidity
        decision costs the dry nudge and marks its own three keys, while the
        shadow fields keep being published; a failing shadow composition
        leaves the live nudge untouched. Warn-once per boundary is preserved.
        """
        live = self._climate_humidity(ing, lvl, op, decision, wt)
        climate_diag = self._climate_shadows(ing, obs, sp, lvl, op, decision, wt, live)
        self._announce_vent_advice(climate_diag)
        return ClimateBandResult(
            climate_diag=climate_diag,
            hum_action=live.decision.action,
        )

    def _announce_vent_advice(self, diag: Mapping[str, Any]) -> None:
        """ADR-0066 B.5 emission rail: bus event on every advice-ACTION change
        plus the opt-in self-clearing notification for "open" episodes.

        The decision is pure (``advice_transition``); this method only tracks
        the previous token and DELIVERS. Its own boundary: a delivery failure
        must never break the tick and never poisons the shadow boundary above.
        """
        action = str(diag.get("vent_action") or "")
        if not action:
            return  # composition failed or produced no advice — nothing moved
        prev = self._runtime.humidity.vent_last_action
        self._runtime.humidity.vent_last_action = action
        try:
            em = advice_transition(prev, action, notify_opt_in=self._c._vent_notify)
            if not em.fire_event:
                return
            payload: dict[str, Any] = {
                "zone": self._c.zone_name,
                "entry_id": self._c._entry_id,
                "action": action,
                "reason": str(diag.get("vent_reason") or ""),
                "delta_gm3": diag.get("vent_delta_gm3"),
            }
            self._c.hass.bus.async_fire(EVENT_VENT_ADVICE, payload)
            notification_id = f"poise_vent_{self._c._entry_id}"
            if em.notify_create:
                reason_txt = _VENT_REASON_TEXT.get(payload["reason"], payload["reason"])
                delta = payload["delta_gm3"]
                delta_txt = (
                    f" (inside {delta:+.1f} g/m³ vs outside)"
                    if isinstance(delta, int | float)
                    else ""
                )
                persistent_notification.async_create(
                    self._c.hass,
                    f"Airing recommended — {reason_txt}{delta_txt}.",
                    title=f"Poise · {self._c.zone_name}",
                    notification_id=notification_id,
                )
            elif em.notify_dismiss:
                persistent_notification.async_dismiss(self._c.hass, notification_id)
        except Exception:  # noqa: BLE001 - announcement must never break the tick
            self._log.debug("Poise ventilation-advice emission failed", exc_info=True)

    def _outdoor_rh(self) -> float | None:
        """Outdoor-humidity ladder (ADR-0066 B.3). Stage 1: the dedicated
        outdoor-RH sensor when configured; stage 2: the ``humidity`` attribute
        of the ALREADY-configured weather entity — zero extra hardware or
        config. Without any source the advice degrades silently to ``no_data``
        (design §9). Both reads routed through the InputReader (phase-4 read
        boundary) — the only module allowed to touch hass.states."""
        dedicated = self._c._input_reader.read(self._c._outdoor_humidity)
        if dedicated is not None:
            return dedicated
        return self._c._input_reader.attr_number(self._c._weather, "humidity")

    def _climate_humidity(
        self,
        ing: IngestResult,
        lvl: PresenceLevelResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
    ) -> ClimateHumidityResult:
        """The LIVE humidity/dry decision (ADR-0050 S2c) behind its own narrow
        boundary — the only non-diagnostic part of the climate band:
        ``action`` drives the dry mode-nudge and ``dry_active`` is the next
        tick's hysteresis latch.

        On failure the nudge falls back to "idle" and the latch keeps its
        previous value; the shadow composition still runs against the neutral
        decision returned here (ADR-0065), so the three humidity keys stay
        published and say what happened instead of vanishing with the rest of
        the band.
        """
        act_state = wt.act_state
        # Seeded, then overwritten inside the boundary: the shadow segment
        # consumes both, so partial progress before a failure point must
        # survive (a raising ``humidity_decide`` still leaves them computed).
        modes: list[str] = []
        abs_gkg: float | None = None
        try:
            modes = (
                [str(m) for m in (act_state.attributes.get("hvac_modes") or [])]
                if act_state
                else []
            )
            # ADR-0050/0051 coherence: compose humidity + diagnostics against the
            # SAME config-based, rate-limited cool band that is actually written
            # (_cool_ac / eff_cool), not a second default-config computation.
            abs_gkg = (
                humidity_ratio(ing.room, ing.rh)
                if ing.rh is not None and ing.room is not None
                else None
            )
            hum = self._g.humidity_decide(
                rh=ing.rh,
                too_warm=op.room_decide > wt.eff_cool,
                in_deadband=decision.heat_sp <= op.room_decide <= wt.eff_cool,
                can_dry="dry" in modes,
                can_fan_only="fan_only" in modes,
                prev_dry_active=self._runtime.humidity.dry_active,
                category=self._c._category,
                abs_humidity_gkg=abs_gkg,
                occupied=lvl.occupied,
            )
            self._runtime.humidity.dry_active = hum.dry_active
        except Exception:  # noqa: BLE001 - must never break the tick
            # Not purely shadow — on failure the LIVE dry mode-nudge silently
            # falls back to "idle". Surface it at WARNING once, then DEBUG after.
            if not self._runtime.diagnostics.hum_shadow_warned:
                self._runtime.diagnostics.hum_shadow_warned = True
                self._log.warning(
                    "Poise %s: climate-band/humidity block failed; the live dry "
                    "mode-nudge falls back to idle this tick (further at DEBUG)",
                    self._c.zone_name,
                    exc_info=True,
                )
            else:
                self._log.debug("Poise climate-band shadow failed", exc_info=True)
            # The latch is deliberately carried over, not reset: a failed
            # decision is no evidence that dehumidification ended.
            hum = HumidityDecision(
                "idle", self._runtime.humidity.dry_active, _HUM_FAILED_REASON
            )
        return ClimateHumidityResult(
            decision=hum, hvac_modes=modes, abs_humidity_gkg=abs_gkg
        )

    def _climate_shadows(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sp: SchedulePresenceResult,
        lvl: PresenceLevelResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
        live: ClimateHumidityResult,
    ) -> dict[str, object]:
        """The pure free-running/fan/PMV shadows + the ``climate_diag``
        assembly behind their own boundary (F-HUMSHADOW).

        Composition lives in ``diagnostics/shadows.py``; the actuator-attribute
        reads are hoisted into the (side-effect-free) argument construction of
        this guarded position. Nothing here writes runtime state, so a failure
        costs exactly the published diagnostic keys — never the dry nudge.
        """
        act_state = wt.act_state
        try:
            # ADR-0054 Nachtrag V1: today's forecast daily mean for the clo
            # blend, latched once per local day from the optimal-start cache
            # (empty cache -> None -> pure running-mean clo).
            diag_rt = self._runtime.diagnostics
            diag_rt.clo_forecast_key, diag_rt.clo_forecast_day = latched_forecast_day(
                diag_rt.clo_forecast_key,
                diag_rt.clo_forecast_day,
                dt_util.now().date().isoformat(),
                self._c._forecast_provider.forecast,
            )
            band = compose_climate_band(
                heat_sp=decision.heat_sp,
                cool_sp=decision.cool_sp,
                room=ing.room,
                room_decide=op.room_decide,
                t_rm_eff=ing.t_rm_eff,
                t_mrt=ing.t_mrt,
                rh=ing.rh,
                eff_cool=wt.eff_cool,
                mode=wt.mode,
                window_open=obs.window_open,
                occupied=lvl.occupied,
                presence_level=lvl.level.value,
                absent_min=lvl.absent_min,
                home_present=sp.home,
                category=self._c._category,
                cool_hard_cap=self._c._cool_hard_cap,
                cool_ac=wt.cool_ac,
                hum=live.decision,
                abs_humidity_gkg=live.abs_humidity_gkg,
                hvac_modes=live.hvac_modes,
                has_fan_modes=bool(act_state and act_state.attributes.get("fan_modes")),
                fan_mode=act_state.attributes.get("fan_mode") if act_state else None,
                hvac_action=(
                    act_state.attributes.get("hvac_action") if act_state else None
                ),
                # ADR-0066 humidity axis (advice/monitor only). One tick minute
                # per call feeds the surface-RH EWMA — against tau = 48 h the
                # event-refresh error is negligible (Poise tick = 60 s,
                # ADR-0020); a real elapsed anchor is the cost increment's job.
                t_out_eff=ing.t_out_eff,
                rh_out=self._outdoor_rh(),
                surface_rh_mean_prev=self._runtime.humidity.surface_rh_mean,
                surface_elapsed_min=1.0,
                co2=None,  # ADR-0049 §1 backend not built yet -> rule 4 inert
                prev_vent_active=self._runtime.humidity.vent_active,
                prev_vent_reason=self._runtime.humidity.vent_reason,
                t_forecast_day=diag_rt.clo_forecast_day,
                room_profile=self._c._room_profile,
                clo_offset=self._c._clo_offset,
            )
            # Fold the advice latch + persisted surface mean back (ADR-0066).
            self._runtime.humidity.vent_active = bool(
                band.get("vent_advice_active", False)
            )
            # Rule 3t dT hysteresis anchor (transient, restart -> dt_on again).
            self._runtime.humidity.vent_reason = str(band.get("vent_reason") or "")
            mean = band.get("surface_rh_mean")
            if isinstance(mean, int | float):
                self._runtime.humidity.surface_rh_mean = float(mean)
            return band
        except Exception:  # noqa: BLE001 - must never break the tick
            if not self._runtime.diagnostics.climate_shadow_warned:
                self._runtime.diagnostics.climate_shadow_warned = True
                self._log.warning(
                    "Poise %s: climate-band shadow composition failed; the live "
                    "dry decision stands, the band diagnostics degrade this tick "
                    "(further at DEBUG)",
                    self._c.zone_name,
                    exc_info=True,
                )
            else:
                self._log.debug("Poise climate-band shadow failed", exc_info=True)
            return {}

    def _stage_intents(
        self, ing: IngestResult, obs: ObservationResult, wt: WriteTargetResult
    ) -> IntentsResult:
        """Heat/cool intent + EKF drive latches (ADR-0024).

        Body in ``tick_pipeline.stage_intents`` via the runtime (no patch
        surface, no config parameter)."""
        return self._runtime.stage_intents(ing, obs, wt)

    def _stage_failure_detect(
        self, ing: IngestResult, wt: WriteTargetResult, intents: IntentsResult
    ) -> bool:
        """Heating-failure detector + notification.

        ``_notify_failure`` runs as a synchronous checkpoint emission at its
        position below (its body is purely synchronous, no suspension point,
        so the stage is an ordinary sync call). No stage-end deferral and no
        ``TickStageError`` wrap needed: the emission is immediate, so a later
        abort in this stage can never strand a pending update.
        """
        now = ing.now
        room = ing.room
        fault_active = ing.fault_active
        act_state = wt.act_state
        target = wt.target
        heating = intents.heating
        # The failure detector keys on the actuator's real running state
        # (hvac_action) when reported, not just our heat intent.
        running = actuator_running(
            act_state.attributes.get("hvac_action") if act_state else None,
            fallback=heating,
        )
        failed = (
            self._runtime.safety.failure.update(
                now_h=now / 3600.0,
                room=room,
                setpoint=target,
                running=running,
            )
            or fault_active
        )
        self._c._notify_failure(failed)
        # Latch for the NEXT tick's learn gate (this tick's gate already ran).
        self._runtime.safety.prev_heating_failed = failed
        return failed

    def _stage_mode_resolution(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        op: OperativeResult,
        wt: WriteTargetResult,
        band: ClimateBandResult,
        *,
        fan_first_requested: bool = False,
    ) -> ModeResolutionResult:
        """Mode arbitration + compressor-guard policy (ADR-0046 paragraph 8).

        Body in ``tick_pipeline.stage_mode_resolution`` via the runtime — the
        invariant (unconditional ``final_mode``/guard resolution, pinned by
        test_frost_rescue_disabled) lives in the moved body."""
        return self._runtime.stage_mode_resolution(
            ing,
            obs,
            op,
            wt,
            band,
            cool_min_outdoor=self._c._cool_min_outdoor,
            cool_lockout_enabled=self._c._cool_lockout_enabled,
            heat_max_outdoor=self._c._heat_max_outdoor,
            heat_lockout_enabled=self._c._heat_lockout_enabled,
            compressor_guard=self._c._compressor_guard,
            comp_min_off_opt=self._c._comp_min_off_opt,
            comp_mode_hold_opt=self._c._comp_mode_hold_opt,
            fan_first_requested=fan_first_requested,
        )

    def _stage_hold_routing(self, wt: WriteTargetResult) -> HoldRoutingResult:
        """Own-write echo + off-hold routing + user-resume escape.

        INVARIANT (pinned): the off-hold frost route keeps its one-tick delay
        -- ``off_held`` reads the persisted hold at tick start; the adopting
        tick still runs the enabled block.

        Body in ``external_override.stage_hold_routing`` via the runtime. The
        user-resume escape's ``_end_hold`` is injected, so its teardown +
        IMMEDIATE bus fire keep their in-stage position.
        """
        return self._runtime.stage_hold_routing(wt, end_hold_fn=self._c._end_hold)

    def _stage_mode_adoption(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
    ) -> ModeAdoptionResult:
        """External-mode adoption, guard-reference freeze, hold pinning.

        INVARIANT (pinned): an active mode-hold pins the desired mode unless
        window/frost took over this tick (safety beats hold).

        Body in ``external_override.stage_mode_adoption`` via the runtime,
        with the unified ONE-call observation (decision AND reason; see the
        module docstring there). ``resolve_desired_mode``/``mode_adopt_reason``
        resolve from THIS module's globals at call time (patch surface); the
        injected command facades keep the ``dt_util`` reads and the
        ``poise_override_ended`` fire at their in-stage positions.
        """
        return self._runtime.stage_mode_adoption(
            ing,
            obs,
            wt,
            res,
            routing,
            adopt_external_mode=self._c._adopt_external_mode,
            resolve_desired_mode_fn=self._g.resolve_desired_mode,
            mode_adopt_reason_fn=self._g.mode_adopt_reason,
            set_mode_override_fn=self._c._set_mode_override,
            end_hold_fn=self._c._end_hold,
        )

    async def _stage_mode_nudge(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        adoption: ModeAdoptionResult,
        *,
        mode_nudge_blocked: str,
    ) -> ModeNudgeResult:
        """Mode-nudge segment: Nudge-Plan → Nudge-Exec + Commit.

        The decision (nudge need + compressor-guard block) is resolved first
        and travels typed in ``ModeNudgeResult``; the ``ActuatorPlan`` later
        RECORDS it (``write_mode``/``hvac_mode``). This segment must execute
        BEFORE the setpoint observation/gate: the ``is_safety`` read of
        ``self._override`` below sits before the nudge await while the §4
        throttle's read sits after it — both positions are load-bearing
        (reorder proof 1 in ``resume_prepare``)."""
        now = ing.now
        frozen = ing.frozen
        window_open = obs.window_open
        act_state = wt.act_state
        _guard_pol = res.guard_pol
        act_modes = res.act_modes
        desired_hvac = adoption.desired_hvac
        _mode_nudge_blocked = mode_nudge_blocked
        # A device hvac_mode change this tick must carry its setpoint with it,
        # so it bypasses the §4 setpoint throttle below: a mode nudge without
        # its matching setpoint would e.g. flip an AC to cool while it still
        # holds the heat idle-hold (17.5) and overcool until the throttle clears
        # (idle-park heat->cool transition).
        _mode_nudge = needs_mode_nudge(
            act_state.state if act_state else None,
            desired_hvac,
            supported=desired_hvac in act_modes,
        )
        _guard_block = self._g._lifecycle.guard_block_reason(
            _guard_pol,
            self._runtime.compressor.multi_lifecycle,
            dt_util.utcnow().timestamp(),
            desired=desired_hvac,
            current=act_state.state if act_state else None,
            # An active manual override is deliberately exempt from the
            # compressor-guard hold, same as a genuine safety trip (open
            # window / frozen sensor) -- ADR-0046 states this explicitly
            # (is_safety covers window->off, frost, override and frozen, never
            # blocked). A user's manual intent must not be held hostage by a
            # min-off/mode-hold timer.
            is_safety=window_open or frozen or self._runtime.user.override is not None,
        )
        if _mode_nudge and _guard_block:
            _mode_nudge = False  # compressor protection: hold this tick's nudge
            _mode_nudge_blocked = _guard_block
        if _mode_nudge:
            # The executor sequence owns the boundary, the own-context
            # creation (tag our own mode change; the id reports even when the
            # dispatch throws — attempt state, test_phase0_attempt_success)
            # and the boundary log. The commit right HERE folds the stamps —
            # it must stay a SEPARATE commit from the setpoint write's below:
            # the code between the two sites reads the mode stamps. Stamp the
            # mode echo baseline so our own nudge is never re-read as an
            # external mode change next tick. Only re-arm the echo window on a
            # mode *change* -- re-arming on every identical re-nudge (a device
            # that never follows) would keep the window open forever and
            # permanently block adoption; evaluated at DISPATCH time, before
            # the stamp moves the ``_last_commanded_hvac`` baseline.
            report = await self._executor.run_mode_nudge(
                self._c._actuator,
                desired_hvac,
                mode_changed=desired_hvac != self._runtime.external.last_commanded_hvac,
            )
            self._c.commit_execution(report, now=now)
        return ModeNudgeResult(
            mode_nudge=_mode_nudge,
            guard_block=_guard_block,
            mode_nudge_blocked=_mode_nudge_blocked,
        )

    def _stage_setpoint_observe(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
        nudge: ModeNudgeResult,
    ) -> SetpointObservation:
        """Device setpoint observation, ADR-0052 paragraph-4 throttle,
        own-echo re-baseline and external-setpoint detection.

        Body in ``tick_pipeline.stage_setpoint_observe`` via the runtime. The
        two ``parse_attr_number`` reads of the tick's ONE actuator State
        object (incl. the ``or 0.1`` step fallback) are pre-parsed here: the
        helper lives in ``ha/`` and importing it into the pipeline would pull
        homeassistant into the pure py310 suite. Both are side-effect-free
        reads of the same frozen State object the stage consumes, so the hoist
        to this call boundary is unobservable (no patch surface on either).

        The stage's ONE tracker observation yields the adoption decision AND
        the ``sp_adopt_reason`` (carried in the ``SetpointObservation``);
        ``setpoint_adopt_reason`` resolves from THIS module's globals at call
        time (patch surface).
        """
        return self._runtime.stage_setpoint_observe(
            ing,
            obs,
            wt,
            res,
            routing,
            nudge,
            actual_sp=parse_attr_number(wt.act_state, "temperature"),
            # ATTR_TARGET_TEMP_STEP: HA serialises the step as
            # "target_temp_step", not under the property name.
            step=parse_attr_number(wt.act_state, "target_temp_step") or 0.1,
            adopt_external_setpoint=self._c._adopt_external_setpoint,
            setpoint_adopt_reason_fn=self._g.setpoint_adopt_reason,
        )

    def _stage_setpoint_adopt(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        routing: HoldRoutingResult,
        spo: SetpointObservation,
        *,
        mode_adopt_reason: str,
    ) -> str:
        """Adoption-reason surfacing, debounced log, prev-update and the
        adoption itself.

        Returns the tick's ``sp_adopt_reason`` (the diagnosis string).

        Body in ``external_override.stage_setpoint_adopt`` via the runtime.
        The reason travels IN ``spo`` — computed together with the decision
        by the ONE observation in ``_stage_setpoint_observe`` from
        character-equal arguments (the re-derivation here saw the same
        ``prev_device_sp``: the prev-update sat AFTER the reason call).
        ``obs``/``routing`` stay in the pinned facade signature; the unified
        chain consumed them in the observe stage. ``set_override`` (full hold
        lifecycle + immediate events) is injected and runs at its in-stage
        position, the debounce log keeps this module's logger channel.
        """
        return self._runtime.stage_setpoint_adopt(
            ing,
            spo,
            mode_adopt_reason=mode_adopt_reason,
            actuator_entity=self._c._actuator,
            logger=self._log,
            set_override_fn=self._c.set_override,
        )

    def _plan_setpoint_write(
        self,
        wt: WriteTargetResult,
        adoption: ModeAdoptionResult,
        nudge: ModeNudgeResult,
        spo: SetpointObservation,
    ) -> ActuatorPlan:
        """Setpoint write gate → the tick's ``ActuatorPlan`` (gate position —
        see the reorder proofs in ``resume_prepare``).

        Body in ``tick_pipeline.plan_setpoint_write`` via the runtime."""
        return self._runtime.plan_setpoint_write(wt, adoption, nudge, spo)

    async def _stage_setpoint_write(
        self,
        ing: IngestResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        adoption: ModeAdoptionResult,
        nudge: ModeNudgeResult,
        spo: SetpointObservation,
    ) -> ActuatorPlan:
        """Setpoint segment: gate/plan → dispatch → commit.

        The write DECISION is the ``ActuatorPlan`` from
        ``_plan_setpoint_write`` (same reads, same order, same await-free
        window as the inline gate); the executor sequence dispatches it and
        the commit folds the stamps. Returns the plan as the tick's
        actuator-write record for the ``TickPlan``.
        """
        now = ing.now
        final_mode = res.final_mode
        actual_sp = spo.actual_sp
        plan = self._plan_setpoint_write(wt, adoption, nudge, spo)
        if plan.write_setpoint:
            # By construction: values + the intended device mode
            # (``adoption.desired_hvac``, always a str) are set whenever
            # write_setpoint is.
            assert plan.raw_setpoint is not None
            assert plan.snapped_setpoint is not None
            assert plan.hvac_mode is not None
            cmd = ActuatorCommand(
                actuator_id=self._c._actuator,
                path=ActuatorPath.SETPOINT,
                value=plan.raw_setpoint,  # RAW on the wire
                hvac_mode=plan.hvac_mode,
                reason=plan.reason,
            )
            # The executor sequence owns the boundary, the own-context
            # creation (tag the call so the resulting state change carries a
            # Context we recognise as our own next tick — echo / clamp) and
            # the boundary log; the commit right here folds the stamps.
            # Attempt state commits even when the dispatch throws:
            # ``pre_write_sp`` — the device's reported setpoint just before
            # this write, the only other value a legit in-window echo can
            # carry (poll lag), remembered for next tick's three-value
            # adoption test — and the context-id registration. Success stamps
            # the SNAPPED target as the echo baseline (the raw value went on
            # the wire).
            report = await self._executor.run_setpoint_write(
                cmd,
                pre_write_value=actual_sp,
                snapped_value=plan.snapped_setpoint,
                final_mode=final_mode,
            )
            self._c.commit_execution(report, now=now)
        return plan

    async def _stage_ext_temp_feed(
        self, ing: IngestResult, op: OperativeResult
    ) -> ExternalTemperaturePlan | None:
        """External-temperature segment: read → plan → dispatch → commit
        (ADR-0029). The select's state stays a positioned fresh read inside
        the write path, after the mode/setpoint awaits (reorder proof 4 in
        ``resume_prepare``). Returns the executed ``ExternalTemperaturePlan``
        (None when the segment did not run) as the record for the
        ``TickPlan``."""
        now = ing.now
        room = ing.room
        t_mrt = ing.t_mrt
        ext_num = op.ext_num
        ext_ok = op.ext_ok
        operative_active = op.operative_active
        # feed the true room temperature to a TRV external-temperature input
        # (ADR-0029): the thermostat then modulates against the real sensor.
        if ext_num and ext_ok:
            # ensure the TRV uses its external sensor (pavax-verified); on
            # the tick we switch it, skip the write so the device can settle
            # — the select-success -> feed-skip coupling is sequence-INTERNAL
            # and owned by the executor (``skip_feed_on_select_success``; a
            # failed select still feeds). It never surfaces as a commit stamp.
            # Positioned read: the select's state is read FRESH in the write
            # path, after the mode-nudge/setpoint awaits — a select change
            # during those service calls is observable and stays so. ``None``
            # covers both "no select discovered" and "no State object".
            _sel_state = self._reader.ext_select_state()
            _select_external = _sel_state is not None and _sel_state not in (
                "external",
                "unavailable",
            )
            fed = round(
                operative_temperature(room, t_mrt) if operative_active else room,
                1,
            )
            # Both plan gates are decided BEFORE the sequence runs.
            # ``external_feed_due`` is pure and reads only state the select
            # never touches (``_last_fed``/``_last_fed_ts``), so evaluating it
            # up front is unobservable; ``feed_value=None`` = no feed planned
            # this tick ("not due" — nothing dispatched, nothing stamped).
            # ``ext_select_state()`` returns non-None only when a sensor
            # select was discovered, so the proxied id is never None when the
            # select is planned. Both calls stay untagged (open F-CONTEXT);
            # the commit right here folds the feed stamps.
            plan = ExternalTemperaturePlan(
                select_external=_select_external,
                feed_value=(
                    fed
                    if external_feed_due(
                        self._runtime.actuator.last_fed,
                        fed,
                        last_fed_ts=self._runtime.actuator.last_fed_ts,
                        now=now,
                        keepalive_s=EXTERNAL_FEED_KEEPALIVE_S,
                        deadband=0.1,
                    )
                    else None
                ),
            )
            report = await self._executor.run_ext_temp(
                plan,
                select_entity_id=self._reader.sensor_select,
                number_entity_id=ext_num,
            )
            self._c.commit_execution(report, now=now)
            return plan
        return None

    async def _stage_frost_rescue(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        wt: WriteTargetResult,
        routing: HoldRoutingResult,
    ) -> ActuatorPlan | None:
        """Disabled/off-held path: Rescue-Plan → Exec + Commit + Events.

        The rescue gates (rescue_ok, ``frost_rescue_target``, the online
        gate, the heat-nudge need) decide the rescue ``ActuatorPlan``
        (``reason="frost_rescue"``: the floor travels raw; NO snapped echo
        baseline — the commit clears it). The ``EndHold("frost_rescue")``
        post-action stays decoupled from write success (pinned by the phase-0
        frost-rescue matrix); the events fire right here after the commit —
        after the write attempts, well before the end-of-tick savepoint —
        which is why this segment keeps them instead of the coordinator seam
        (Rescue-Plan→Exec+Commit+Events). Returns the executed plan (None when
        no rescue write ran) for the ``TickPlan``.
        """
        now = ing.now
        room = ing.room
        can_heat = obs.can_heat
        mold_min = floors.mold_min
        act_state = wt.act_state
        _actuator_online = wt.actuator_online
        _off_held = routing.off_held
        # A disabled zone still gets unconditional frost/mould protection
        # (README promise) — but rescue-only, so a reasonable manual setpoint
        # above the floor is never fought; a cool-only device has no frost
        # duty and is left alone (frost_rescue_target -> None). A user-held
        # ``off`` (device switched off via the remote, Poise still enabled) is
        # honoured like a disabled zone -- but unlike a truly disabled zone we
        # must NOT treat the warm off device as perpetual frost demand
        # (``frost_rescue_target`` rescues an off heater on principle), or we
        # would restart the device the user deliberately switched off. So an
        # off-HELD zone is rescued only when the ROOM is actually at the
        # frost/mould floor; a disabled zone keeps the unconditional rescue.
        _rescue_ok = (
            (not _off_held)
            or room <= FROST_FLOOR_C
            or (mold_min is not None and room <= mold_min)
        )
        rescue = (
            frost_rescue_target(
                can_heat=can_heat,
                actual_sp=parse_attr_number(act_state, "temperature"),
                device_state=act_state.state if act_state else None,
                frost_floor=FROST_FLOOR_C,
                mold_min=mold_min,
                deadband=WRITE_DEADBAND_C,
            )
            if _rescue_ok
            else None
        )
        # ``frost_rescue_target`` treats "unavailable" as "inactive" on
        # purpose (an off/unknown/unavailable device below the floor all
        # legitimately need the rescue floor) -- but that means it returns a
        # non-None target on EVERY tick for a genuinely offline actuator, so
        # unlike the enabled-branch setpoint write above, this write is gated
        # on ``_actuator_online``: otherwise a disabled zone with a dead
        # actuator would dispatch a real ``climate.set_temperature`` into the
        # void every tick. Off/unknown (actuator present, just not in "heat")
        # still get the rescue write.
        if rescue is not None and _actuator_online:
            _rmodes = (
                (act_state.attributes.get("hvac_modes") or []) if act_state else []
            )
            _cur = act_state.state if act_state else None
            # The decided rescue plan — the nudge need is evaluated directly
            # for the run_frost_rescue call.
            plan = ActuatorPlan(
                write_mode=_cur != "heat" and "heat" in _rmodes,
                hvac_mode="heat",
                write_setpoint=True,
                snapped_setpoint=None,  # no echo baseline for the floor
                raw_setpoint=rescue,
                reason="frost_rescue",
            )
            # The executor sequence owns the TWO INDEPENDENT boundaries — a
            # failed mode-nudge must never skip the safety setpoint write (the
            # floor still has to be sent) — plus both untagged payloads and
            # the boundary logs. The commit right here folds the stamps:
            # frost-rescue heat is our own safety mode, never a user change —
            # mode echo baseline, ts re-armed UNCONDITIONALLY; the frost floor
            # is our own value, not user intent -> ``last_written_sp=None``;
            # plus ``_mark_actuated``.
            report = await self._executor.run_frost_rescue(
                self._c._actuator,
                rescue,
                nudge=plan.write_mode,
            )
            # A frost/mould rescue that fires while an ``off`` hold is active
            # supersedes the user's off intent -- end the hold with an
            # accurate reason ("frost_rescue") instead of leaving the device
            # escape to end it next tick under the generic "user_resume". The
            # ``EndHold`` post-action (require_success=False) runs AFTER the
            # report fold and is never coupled to write success (phase-0
            # frost-rescue matrix, all four cells); the adapter fires the
            # returned ``poise_override_ended`` event right after the commit —
            # after the write attempts, well before the end-of-tick checkpoint.
            commit = self._c.commit_execution(
                report,
                post_actions=((EndHold("frost_rescue"),) if _off_held else ()),
                now=now,
            )
            for ev in commit.events:
                self._c._fire_override_ended(ev.reason)
            return plan
        return None

    def _build_finalize_context(
        self,
        *,
        state: PreparedState,
        sp: SchedulePresenceResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
        band: ClimateBandResult,
        intents: IntentsResult,
        failed: bool,
        res: ModeResolutionResult,
        guard_block: str | None,
        mode_nudge_blocked: str,
        mode_adopt_reason: str,
        sp_adopt_reason: str,
    ) -> FinalizeContext:
        """Assemble the prepare->finalize contract from the typed stage
        results (pure construction — no ``self`` reads, no I/O).

        Body in ``tick_pipeline.build_finalize_context`` via the runtime; the
        field set is pinned by test_phase1_tick_result."""
        return self._runtime.build_finalize_context(
            state=state,
            sp=sp,
            op=op,
            decision=decision,
            wt=wt,
            band=band,
            intents=intents,
            failed=failed,
            res=res,
            guard_block=guard_block,
            mode_nudge_blocked=mode_nudge_blocked,
            mode_adopt_reason=mode_adopt_reason,
            sp_adopt_reason=sp_adopt_reason,
        )

    async def finalize_tick(self, ctx: FinalizeContext) -> TickOutcome:
        """Everything after the apply/commit node, split into stage methods.

        Orchestrates the finalize stages in text order: the neutral shadow
        seed + the six independent shadow segments (``_stage_shadow_domain``),
        valve health with its immediate issue emission
        (``_stage_valve_health``), the outcome/HDH/RegQ/ref-offset/tau-settle
        collector boundary (``_stage_outcome_diag``), the ``_tick_data``
        assembly plus ``heat_demand`` (``_stage_assemble_tick_data``), then
        the trace record. Runs strictly BEFORE the save checkpoint since
        F-SAVEPOINT, so every runtime the stages advance (lifecycle fold, PI
        accumulator, outcome/HDH/RegQ/offset/settle) is captured by the SAME
        tick's save. Every stage is synchronous and, since F-TRACEIO, the whole
        segment is await-free: ``_maybe_record_trace`` only enqueues.
        """
        now, room, rh, t_mrt = ctx.now, ctx.room, ctx.rh, ctx.t_mrt
        t_out_eff, t_rm_eff, act_state = ctx.t_out_eff, ctx.t_rm_eff, ctx.act_state
        heating, frozen = ctx.heating, ctx.frozen
        operative = operative_temperature(room, t_mrt)
        # --- Diagnostics-only shadows ---------------------------------------
        # The setpoint is already written above. A failure in any predictive
        # shadow (e.g. a degenerate value from a not-yet-identified EKF) must
        # NEVER take control reporting offline — so the whole block is guarded and
        # degrades to neutral diagnostics while the written setpoint stands.
        # The neutral fallback literal lives in ``diagnostics/shadows.py`` —
        # WITHOUT the compressor_gate_* keys, which only the lifecycle fold
        # produces. The neutral values are the shadow stage's seed: each of the
        # six segments overwrites its OWN fragment on top of it, so a failing
        # segment costs exactly its own keys and nothing else.
        neutral = ShadowStageResult(
            operative=operative,
            binding="en16798",
            cover_peak=operative,
            cover_pos=0.0,
            cover_reason="",
            shadow_objs=neutral_shadow_objs(
                self._runtime.compressor.multi_lifecycle.health
            ),
        )
        shadow = self._stage_shadow_domain(ctx, neutral)
        valve = self._stage_valve_health()
        # Valve checkpoint: kept at its EXACT position — the ORDER relative
        # to the stages around it is behaviour. No ``TickStageError`` wrap
        # either: the emission is immediate, nothing can be stranded.
        self._c._health.emit(valve.health_updates)
        outcome_diag = self._stage_outcome_diag(ctx)
        _tick_data = self._stage_assemble_tick_data(
            ctx, shadow=shadow, valve=valve, outcome_diag=outcome_diag
        )
        # Capture the REAL actuator mode + action so a replayed trace can
        # explain a dehumidification episode — the thermal ``mode``
        # (idle/cool/heat/off) alone never carries the humidity/device axis,
        # so dry episodes would be invisible on disk.
        _tick_data["device_hvac_mode"] = act_state.state if act_state else ""
        _tick_data["hvac_action"] = (
            (act_state.attributes.get("hvac_action") or "") if act_state else ""
        )
        # INVARIANT: the trace enqueue inside this call is the LAST observable
        # statement of the tick under the lock. Only the queue append runs
        # here (``TraceRecorder.enqueue`` is sync and touches no file), so
        # trace I/O does not count into ``tick_ms`` (ADR-0063). The record
        # build stays fused with the enqueue inside ``_maybe_record_trace``'s
        # guarded boundary (``_trace_enabled`` gate + swallow-all): splitting
        # the build out as a pure pre-step would move a swallowed build
        # failure onto the tick's error path. Only the build INSTRUCTIONS
        # live in the pure ``diagnostics/trace.py``; the call site stays
        # inside that boundary and ``TickOutcome.trace_record`` stays
        # ``None``.
        await self._c._maybe_record_trace(
            _tick_data, room=room, t_out=t_out_eff, rh=rh, t_rm=t_rm_eff, now=now
        )
        # Pure, side-effect-free construction only below this point: the hub
        # contract fields are lifted from the assembled payload verbatim, and
        # ``diagnostics`` carries the payload dict itself (the presenter
        # pre-form returns the SAME object, so ``coordinator.data`` and the
        # traced dict stay identical).
        return TickOutcome(
            data=AvailableTickData(
                mono_ts=now,
                heating=heating,
                sensor_frozen=frozen,
                current_temperature=_tick_data["current_temperature"],
                heat_sp=_tick_data["heat_sp"],
                tpi_duty=_tick_data.get("tpi_duty"),
                heat_demand=_tick_data["heat_demand"],
            ),
            diagnostics=_tick_data,
            trace_record=None,
        )

    def _stage_shadow_domain(
        self, ctx: FinalizeContext, neutral: ShadowStageResult
    ) -> ShadowStageResult:
        """The finalize shadows as SIX INDEPENDENT segments (ADR-0065),
        pinned by test_phase0_fault_shadow_domain.

        Order: peak forecast → MPC → TPI → PI(+acc) → lifecycle fold →
        thermal arbitration → ``shadow_objs``. Each step owns its own
        boundary and contributes its own ``shadow_objs`` fragment on top of
        the neutral seed, so a failing segment costs exactly its own keys —
        ``tpi_duty`` (and with it ``heat_demand``), the lifecycle fold and
        the ``_pi.acc`` advance included.

        The execution ORDER is unchanged, and so is every side effect and its
        position. The ONE surviving cross-segment dependency is data-borne,
        not error-domain coupling: the thermal arbitration consumes the folded
        lifecycle's ``DeviceRuntime``, so it is skipped when the fold itself
        failed — never when an earlier shadow did.
        """
        objs: dict[str, Any] = dict(neutral.shadow_objs)
        cover_peak, cover_pos, cover_reason, binding = self._shadow_cover(ctx, neutral)
        objs.update(self._shadow_mpc(ctx))
        objs.update(self._shadow_tpi(ctx))
        objs.update(self._shadow_pi(ctx))
        fold = self._shadow_lifecycle(ctx)
        if fold is not None:
            objs.update(fold.objs)
            objs.update(self._shadow_arbitration(ctx, fold))
        return ShadowStageResult(
            operative=neutral.operative,
            binding=binding,
            cover_peak=cover_peak,
            cover_pos=cover_pos,
            cover_reason=cover_reason,
            shadow_objs=objs,
        )

    def _shadow_failed(self, segment: str) -> None:
        """One shadow segment failed. The wording ``shadow evaluation failed``
        is load-bearing (user log filters key on it); the segment name says
        which fragment degraded."""
        self._log.exception(
            "Poise: shadow evaluation failed (%s); the written setpoint stands, "
            "diagnostics degraded this tick",
            segment,
        )

    def _shadow_cover(
        self, ctx: FinalizeContext, neutral: ShadowStageResult
    ) -> tuple[float, float, str, str]:
        """Predictive solar-shading shadow (ADR-0043) + binding classification.

        Returns ``(peak, position, reason, binding)`` — the neutral seed's
        values on failure. Composition in ``diagnostics/shadows.py``; the two
        kernels are passed as ``*_fn`` resolved from the COORDINATOR module's
        globals at call time, so patching
        ``coordinator.predict_peak_operative``
        (test_phase0_fault_shadow_domain) keeps hitting the dispatch.
        """
        try:
            peak, pos, reason, binding = evaluate_cover_shadow(
                operative=neutral.operative,
                t_out_eff=ctx.t_out_eff,
                q_solar=ctx.q_solar,
                cool_sp=ctx.decision.cool_sp,
                heat_sp=ctx.decision.heat_sp,
                mold_min=ctx.mold_min,
                model=self._runtime.learning.ekf.get_model(),
                identified=self._runtime.learning.ekf.identified,
                temperature_std=self._runtime.learning.ekf.temperature_std,
                predict_peak_operative_fn=self._g.predict_peak_operative,
                shading_target_position_fn=self._g.shading_target_position,
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("cover")
            return (
                neutral.cover_peak,
                neutral.cover_pos,
                neutral.cover_reason,
                neutral.binding,
            )
        return peak, pos, reason, binding

    def _shadow_mpc(self, ctx: FinalizeContext) -> dict[str, Any]:
        """Shadow MPC (ADR-0033): what the predictive controller *would*
        command against the live EKF state; reported only, dormant until
        identified."""
        try:
            return mpc_shadow_objs(
                evaluate_shadow(
                    identified=self._runtime.learning.ekf.identified,
                    t_air=ctx.room,
                    t_out=ctx.t_out_eff,
                    t_rm=ctx.t_rm_eff,
                    tau_hours=self._runtime.learning.ekf.tau_hours,
                    model=self._runtime.learning.ekf.get_model(),
                    prediction_std=self._runtime.learning.ekf.temperature_std,
                    confidence=self._runtime.learning.ekf.confidence,
                    target=ctx.decision.heat_sp,
                    lower=ctx.decision.heat_sp,
                    upper=ctx.decision.cool_sp,
                    params=self._c._mpc_params,
                )
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("mpc")
            return {}

    def _shadow_tpi(self, ctx: FinalizeContext) -> dict[str, Any]:
        """Shadow direct-valve TPI duty (ADR-0036): computed + reported only.

        F-TPI: its own boundary, so ``tpi_duty`` — and with it the published
        ``heat_demand`` (the live duty while it exists) — survives a failure
        in any other shadow.
        """
        try:
            return tpi_shadow_objs(
                evaluate_tpi_shadow(
                    valve_available=self._reader.valve_entity is not None,
                    model=self._runtime.learning.ekf.get_model(),
                    # Shadow honesty: regulate toward the WRITE path's resolved
                    # target (incl. band/frost/mould clamps), not the raw
                    # corridor edge — a live TPI would have to honour it
                    # exactly like the setpoint write does, and ``heat_demand``
                    # (hub boiler demand, R13) is fed from this duty. "manual"
                    # is the override mode (tick_resolve); a below-room manual
                    # target is directionally safe (heating duty clamps to 0).
                    target=(
                        ctx.target
                        if ctx.mode in ("heat", "manual")
                        else ctx.decision.heat_sp
                    ),
                    room=ctx.room,
                    t_out=ctx.t_out_eff,
                )
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("tpi")
            return {}

    def _shadow_pi(self, ctx: FinalizeContext) -> dict[str, Any]:
        """PI-compensated setpoint shadow (ADR-0037): setpoint-only devices.

        F-PIACC: the integrator advance is the segment's own side effect
        behind its own boundary — only a failure of the PI evaluation itself
        freezes ``acc``.
        """
        try:
            pi = evaluate_pi_shadow(
                self._runtime.learning.pi,
                applies=self._reader.valve_entity is None,
                # Same shadow-honesty rule as the TPI branch above: the write
                # path's resolved target ("manual" = override mode, incl.
                # clamps), not the raw corridor edge.
                target=(
                    ctx.target
                    if ctx.mode in ("heat", "manual")
                    else ctx.decision.heat_sp
                ),
                room=ctx.room,
                external=ctx.t_out_eff,  # real outdoor temp
                dt_h=TICK_INTERVAL_S / 3600.0,
            )
            # The shadow is pure — advance the persisted integrator here,
            # exactly once per tick, instead of as a hidden side effect of the
            # read.
            if pi.next_acc is not None:
                self._runtime.learning.pi.acc = pi.next_acc
            return pi_shadow_objs(pi)
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("pi")
            return {}

    def _shadow_lifecycle(self, ctx: FinalizeContext) -> LifecycleFoldResult | None:
        """Compressor-lifecycle fold + its gate diagnostics (ADR-0046 §8).

        F-LIFECYCLE: the fold is LIVE state — it feeds the next tick's
        compressor guard — and runs behind its own boundary, independent of
        every diagnostic shadow before it. ``None`` means the fold itself failed: the
        pre-tick lifecycle survives, the two ``compressor_gate_*`` keys stay
        absent and the arbitration segment (which needs this runtime) is
        skipped.
        """
        act_state, final_mode = ctx.act_state, ctx.final_mode
        try:
            _act_avail = act_state is not None and act_state.state not in (
                "unavailable",
                "unknown",
            )
            # Fold the actuator's run-state into the per-device lifecycle on a
            # wall-clock basis, then derive the resolver's min-off / health gate.
            now_wall = dt_util.utcnow().timestamp()
            _act_action = act_state.attributes.get("hvac_action") if act_state else None
            # INVARIANT (K2b, ADR-0046 §9): lifecycle observe() runs after
            # guard diagnosis; the pre-observe gate mirrors the write-path
            # guard. Pinned by test_dry_nudge_when_humid_and_idle. Folding
            # observe first would let the guard judge against its own intent
            # and self-armed mode hold.
            # ADR-0046 §8 compressor protection (LIVE): the same decision the
            # write path above already applied (_guard_block), surfaced here
            # as a diagnostic; the display policy uses the effective timers so
            # the remaining-time attributes match the live gate.
            _comp_pol = ctx.guard_pol or self._g._lifecycle.LifecyclePolicy(
                min_off_s=ctx.g_min_off, min_mode_hold_s=ctx.g_mode_hold
            )
            # Fix the conditioning signal: an AC that reports no hvac_action (many
            # ESPHome/IR bridges) would otherwise read as permanently off and never
            # accrue a min-off lock. Fall back to Poise's intended mode (ADR-0024
            # cool-drive parity).
            self._runtime.compressor.multi_lifecycle = self._g._lifecycle.observe(
                self._runtime.compressor.multi_lifecycle,
                conditioning=self._g._lifecycle.compressor_running(
                    _act_action, final_mode
                ),
                mode=act_state.state if (act_state and _act_avail) else None,
                now=now_wall,
                health=(
                    DeviceHealth.OK.value
                    if _act_avail
                    else DeviceHealth.UNAVAILABLE.value
                ),
            )
            _multi_policy = self._g._lifecycle.LifecyclePolicy()
            objs = lifecycle_shadow_objs(
                lifecycle=self._runtime.compressor.multi_lifecycle,
                now_wall=now_wall,
                multi_policy=_multi_policy,
                comp_pol=_comp_pol,
                comp_block=ctx.guard_block,
                min_off_remaining_fn=self._g._lifecycle.min_off_remaining,
                mode_hold_remaining_fn=self._g._lifecycle.mode_hold_remaining,
            )
            runtime = self._g._lifecycle.to_runtime(
                self._runtime.compressor.multi_lifecycle, now_wall, _multi_policy
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("lifecycle")
            return None
        return LifecycleFoldResult(runtime=runtime, objs=objs)

    def _shadow_arbitration(
        self, ctx: FinalizeContext, fold: LifecycleFoldResult
    ) -> dict[str, Any]:
        """Phase-1/2 thermal-arbitration shadow (ADR-0046): transient
        ZoneDevice over the freshly folded lifecycle runtime.

        EntitySnapshot/ThermalDemand construction lives in
        ``diagnostics/shadows.py``; the kernel keeps dispatching through the
        COORDINATOR module's globals at call time.
        """
        act_state = ctx.act_state
        try:
            return arbitration_shadow_objs(
                evaluate_multi_shadow(
                    entity_id=self._c._actuator,
                    hvac_modes=(
                        (act_state.attributes.get("hvac_modes") or [])
                        if act_state
                        else []
                    ),
                    available=act_state is not None
                    and act_state.state not in ("unavailable", "unknown"),
                    direction=_THERMAL_DIR.get(ctx.decision.mode),
                    target=ctx.decision.target,
                    runtime=fold.runtime,
                    evaluate_thermal_shadow_fn=self._g.evaluate_thermal_shadow,
                )
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("arbitration")
            return {}

    def _stage_valve_health(self) -> ValveHealthResult:
        """Valve-stuck detection over a fresh read of the calibration
        counts. Returns the finalize segment's only ``HealthUpdate`` for the
        caller's immediate emission."""
        # valve health: a near-zero closing-step count means the motorised
        # valve failed calibration / is jammed — advisory diagnostic + repair
        # issue.
        closing_steps, idle_steps = self._reader.valve_steps()
        v_stuck = valve_stuck(closing_steps)
        valve_health = (
            "stuck" if v_stuck else ("ok" if closing_steps is not None else "unknown")
        )
        return ValveHealthResult(
            closing_steps=closing_steps,
            idle_steps=idle_steps,
            valve_health=valve_health,
            health_updates=(
                HealthUpdate(
                    issue_id=f"valve_stuck_{self._c._entry_id}",
                    active=v_stuck,
                    translation_key="valve_stuck",
                    placeholders={"entity": self._reader.valve_closing_steps or "—"},
                ),
            ),
        )

    def _stage_outcome_diag(self, ctx: FinalizeContext) -> dict[str, Any]:
        """ADR-0044/0045 outcome scoring + savings diagnostics behind the ONE
        collector boundary (``DiagnosticsCollector.safe_collect``). The
        returned mapping IS this stage's typed cross-stage value:
        ``safe_collect``'s replace-on-success dict — the full collected key
        set, or the defaults below on failure (the second observable
        key-shrink mechanism); a wrapper dataclass would only re-wrap the
        collector contract's own typed return."""
        now, room, heating = ctx.now, ctx.room, ctx.heating
        decision, t_out_eff, q_solar = ctx.decision, ctx.t_out_eff, ctx.q_solar
        sched, window_open, frozen = ctx.sched, ctx.window_open, ctx.frozen
        room_decide, eff_cool, mode = ctx.room_decide, ctx.eff_cool, ctx.mode
        act_state = ctx.act_state
        # ADR-0044 outcome scoring + ADR-0045 efficiency report (diagnostic only;
        # never raises — a scoring slip must not break the control tick).
        outcome_diag: dict[str, Any] = {
            "outcome_last_score": None,
            "outcome_ts_avg": None,
            "outcome_obs_avg": None,
            "outcome_n": 0,
            "savings_kwh_month": 0.0,
            "savings_eur_month": 0.0,
            "savings_pct": 0.0,
        }

        # The boundary itself is ``DiagnosticsCollector.safe_collect`` — the
        # closure below runs the five state folds + assembly in text order
        # INSIDE that one try, so an exception in fold N still leaves
        # ``outcome_diag`` on the defaults, skips folds N+1… and freezes the
        # metrics until the next healthy tick (the open F-OUTFOLD would
        # change that). The LIVE reads (``runtime.user.enabled``,
        # ``runtime.user.override``, ``dt_util.now().month``) stay at their
        # in-boundary positions and are evaluated at call time.
        def _collect_outcome_diag() -> dict[str, Any]:
            _tick_min = TICK_INTERVAL_S / 60.0
            # Real elapsed dt (event-driven refreshes book < 60 s, not a flat
            # tick -- same reasoning as the CA/offset dt below), capped so a
            # masked gap adds ~2 ticks instead of silently over/under-crediting
            # the HDH savings estimate and the outcome-session heating-time
            # integral.
            _hdh_dt = capped_elapsed_min(
                self._runtime.diagnostics.hdh_last_mono, now, _tick_min
            )
            self._runtime.diagnostics.hdh_last_mono = now
            self._runtime.diagnostics.hdh = self._runtime.diagnostics.hdh.observe(
                comfort=self._c._comfort_base,
                setpoint=decision.heat_sp,
                outdoor=t_out_eff,
                dt_min=_hdh_dt,
                now_month=dt_util.now().month,
                cfg=self._c._hdh_cfg,
            )
            self._runtime.diagnostics.outcome_session, _fin = observe_session(
                self._runtime.diagnostics.outcome_session,
                temp=room,
                target=decision.heat_sp,
                heating=heating,
                controlling=self._runtime.user.enabled,
                dt_min=_hdh_dt,
                expected_minutes=model_expected_minutes(
                    self._runtime.learning.ekf.get_model()
                    if self._runtime.learning.ekf.identified
                    else None,
                    room=room,
                    target=decision.heat_sp,
                    t_out=t_out_eff,
                    q_solar=q_solar,
                    fallback=float(sched.minutes_to_comfort),
                ),
                q_solar=q_solar,
                outdoor=t_out_eff,
            )
            if _fin is not None:
                self._runtime.diagnostics.outcome_stats = (
                    self._runtime.diagnostics.outcome_stats.observe(
                        _fin.score, _fin.controller
                    )
                )
            # ADR-0055 regulation-quality metric (EN 15500-1 CA): score only
            # unmasked comfort ticks (room_decide vs the effective band).
            # Field calibration 2026-08-08: additionally mask violations the
            # zone structurally cannot actuate against (heat-only zone above
            # the cool edge in a hot spell measures the weather, not the
            # controller) — ``ca_tick_scorable``, capability fairness.
            if (
                self._runtime.user.enabled
                and not window_open
                and not frozen
                and self._runtime.user.override is None
                and sched.is_comfort
                and ca_tick_scorable(
                    room=room_decide,
                    heat_sp=decision.heat_sp,
                    cool_sp=eff_cool,
                    can_heat=ctx.can_heat,
                    can_cool=ctx.can_cool,
                )
            ):
                # Real elapsed (event-driven refreshes book < 60 s, not a flat
                # tick), capped so a masked gap adds ~2 ticks.
                _ca_dt = capped_elapsed_min(
                    self._runtime.diagnostics.ca_last_mono, now, _tick_min
                )
                self._runtime.diagnostics.ca_last_mono = now
                self._runtime.diagnostics.regq = self._runtime.diagnostics.regq.observe(
                    room=room_decide,
                    heat_sp=decision.heat_sp,
                    cool_sp=eff_cool,
                    mode=mode,
                    dt_min=_ca_dt,
                )
            # ADR-0055 N1: time-weighted PPD — the comfort-flip gate
            # component. Same fairness mask as the CA fold above, additionally
            # gated on a VALID PMV (ISO 7730 domain, ADR-0054 V3); own elapsed
            # anchor because PMV validity and the CA mask diverge.
            _ppd_val = ctx.climate_diag.get("ppd")
            if (
                self._runtime.user.enabled
                and not window_open
                and not frozen
                and self._runtime.user.override is None
                and sched.is_comfort
                and ctx.climate_diag.get("pmv_valid") is True
                and isinstance(_ppd_val, (int, float))
            ):
                _ppd_dt = capped_elapsed_min(
                    self._runtime.diagnostics.ppd_last_mono, now, _tick_min
                )
                self._runtime.diagnostics.ppd_last_mono = now
                self._runtime.diagnostics.regq = (
                    self._runtime.diagnostics.regq.observe_ppd(
                        ppd=float(_ppd_val), dt_min=_ppd_dt
                    )
                )
            # ADR-0069 U7/U8: tier-2 activation stepping (persisted latch) +
            # the NEXT-tick solver inputs. Runs after the PPD fold so the
            # entry gate reads this tick's matured figures; the solver reads
            # the previous tick's latch (persisted state, never a per-tick
            # predicate) — same semantics as cool_sp_eff_prev.
            _t2_dt = capped_elapsed_min(
                self._runtime.diagnostics.tier2_last_mono, now, _tick_min
            )
            self._runtime.diagnostics.tier2_last_mono = now
            _ca0 = self._runtime.diagnostics.comfort_activation
            _t2_identified = self._runtime.learning.ekf.identified
            _t2_entry = flip_metric_ok(
                FLIP_TIER_COMFORT,
                self._runtime.diagnostics.regq,
                identified=_t2_identified,
            )
            _t2_ppd = self._runtime.diagnostics.regq.ppd
            _pmv_ready = pmv_control_ready(
                rh=ctx.rh, pmv_valid=ctx.climate_diag.get("pmv_valid") is True
            )
            _pred_impossible = (
                ctx.climate_diag.get("fan_circ_reason") == "no_fan_capability"
            )
            _t2_gen = _ca0.generation
            _fan_next = step_tier(
                _ca0.fan_ce,
                ready=self._c._active_comfort,
                entry_ok=_t2_entry,
                ppd=_t2_ppd,
                signature=activation_signature(
                    room_profile=self._c._room_profile,
                    clo_offset=self._c._clo_offset,
                    model_rev=PMV_MODEL_REV,
                    predecessors=(),
                ),
                dt_min=_t2_dt,
                allowed=may_dwell(
                    _ca0, "fan_ce", predecessor_impossible=_pred_impossible
                ),
                next_generation=_t2_gen + 1,
                # P1 field finding: a fan-less zone retires fan_ce to shadow
                # (also a STALE persisted eligible), so the serialization's
                # deadlock escape actually reaches pmv_offset.
                impossible=_pred_impossible,
            )
            if _fan_next.state == "live" and _ca0.fan_ce.state != "live":
                _t2_gen += 1
            _ca1 = ComfortActivation(
                fan_ce=_fan_next, pmv_offset=_ca0.pmv_offset, generation=_t2_gen
            )
            if _ca0.fan_ce.state == "live" and _fan_next.state != "live":
                # The ADR-0069 cascade: dependents re-baseline.
                _ca1 = cascade_after_invalidation(
                    _ca1, invalidated_generation=_ca0.fan_ce.generation
                )
            _pmv_next = step_tier(
                _ca1.pmv_offset,
                ready=self._c._active_comfort and _pmv_ready,
                entry_ok=_t2_entry,
                ppd=_t2_ppd,
                signature=activation_signature(
                    room_profile=self._c._room_profile,
                    clo_offset=self._c._clo_offset,
                    model_rev=PMV_MODEL_REV,
                    predecessors=(("fan_ce",) if _ca1.fan_ce.state == "live" else ()),
                ),
                dt_min=_t2_dt,
                allowed=may_dwell(
                    _ca1, "pmv_offset", predecessor_impossible=_pred_impossible
                ),
                next_generation=_t2_gen + 1,
            )
            if _pmv_next.state == "live" and _ca1.pmv_offset.state != "live":
                _t2_gen += 1
            self._runtime.diagnostics.comfort_activation = ComfortActivation(
                fan_ce=_ca1.fan_ce, pmv_offset=_pmv_next, generation=_t2_gen
            )
            # NEXT-tick solver inputs: the CE credit only against a CONFIRMED
            # fan run (the shadow's velocity is hvac_action-gated, ADR-0068
            # §6 — a still room yields 0.0), the PMV shift only with real
            # control readiness (ADR-0069 §4).
            _ce_val = ctx.climate_diag.get("fan_ce_k")
            self._runtime.latches.fan_ce_credit_k = (
                float(_ce_val)
                if _ca1.fan_ce.state == "live" and isinstance(_ce_val, (int, float))
                else 0.0
            )
            _pmv_val = ctx.climate_diag.get("pmv")
            self._runtime.latches.pmv_offset_k = (
                pmv_setpoint_offset(float(_pmv_val))
                if _pmv_next.state == "live"
                and _pmv_ready
                and isinstance(_pmv_val, (int, float))
                else 0.0
            )
            # ADR-0056 SHADOW: actuator<->room reference-frame offset (no writes).
            # Fold in a sample only while the actuator is actually conditioning
            # — its internal sensor carries the placement bias only under
            # active airflow/heat, so idle ticks would drag the offset toward
            # zero. Reuse the EKF drive signal (real hvac_action, intent
            # fallback); the warm-up therefore counts real conditioning time.
            # Diagnostic only: the write path stays room-referenced until
            # flip-gated live (ADR-0055).
            _ref_dt = capped_elapsed_min(
                self._runtime.learning.ref_last_mono, now, _tick_min
            )
            self._runtime.learning.ref_last_mono = now
            # parse_finite mirrors the actuator_snapshot contract (no
            # availability gate, finite rejection — a NaN used to poison the
            # deviation EWMA until restart, review B.5).
            _act_f = parse_finite(
                act_state.attributes.get("current_temperature") if act_state else None
            )
            _ref_conditioning = (
                self._runtime.learning.last_u_h > 0.0
                or self._runtime.learning.last_u_c > 0.0
            )
            self._runtime.learning.ref_offset = update_offset(
                self._runtime.learning.ref_offset,
                actuator_temp=_act_f,
                room_temp=room,
                dt_min=_ref_dt,
                conditioning=_ref_conditioning,
            )
            # SHADOW: settle-based τ-confidence — has α (=1/τ) actually
            # converged, not just been counted (ADR-0024)? Fed only on
            # learn-active ticks (the same excitation signal, where α can
            # move); diagnostic only, no writes, until it clamps the preheat
            # lead live (ADR-0055).
            _tau_dt = capped_elapsed_min(
                self._runtime.learning.tau_last_mono, now, _tick_min
            )
            self._runtime.learning.tau_last_mono = now
            self._runtime.learning.tau_settle = update_settle(
                self._runtime.learning.tau_settle,
                alpha=self._runtime.learning.ekf.x[1],
                dt_min=_tau_dt,
                learn_active=_ref_conditioning,
            )
            return build_outcome_diag(
                outcome_stats=self._runtime.diagnostics.outcome_stats,
                hdh=self._runtime.diagnostics.hdh,
                hdh_cfg=self._c._hdh_cfg,
                regq=self._runtime.diagnostics.regq,
                ref_offset=self._runtime.learning.ref_offset,
                ref_conditioning=_ref_conditioning,
                tau_settle=self._runtime.learning.tau_settle,
                eff_cool=eff_cool,
            )

        return self._diag.safe_collect(_collect_outcome_diag, outcome_diag)

    def _stage_assemble_tick_data(
        self,
        ctx: FinalizeContext,
        *,
        shadow: ShadowStageResult,
        valve: ValveHealthResult,
        outcome_diag: dict[str, Any],
    ) -> dict[str, Any]:
        """The ``_tick_data`` assembly (presenter pre-form) plus
        ``heat_demand``, which MUST follow the assembly — it reads
        ``tpi_duty`` back out of the dict. Returns THE dict object itself: the
        trace consumes it, ``TickOutcome.diagnostics`` carries it and
        ``_present`` republishes it, so ``coordinator.data`` stays identical
        BY OBJECT to the traced payload (aliasing contract; the ``tick_ms*``
        attach in ``_async_update_data`` builds on the same dict).

        This stage deliberately exceeds the soft ~150-line stage bound — the
        large dict literal is kept verbatim as the aliasing-contract proof
        body; a cosmetic split would weaken the verbatim evidence without
        shrinking the proof surface."""
        now, room, rh, target = ctx.now, ctx.room, ctx.rh, ctx.target
        t_out_eff, t_rm_eff, t_rm_source = ctx.t_out_eff, ctx.t_rm_eff, ctx.t_rm_source
        q_solar, q_solar_source = ctx.q_solar, ctx.q_solar_source
        q_solar_internal, t_mrt = ctx.q_solar_internal, ctx.t_mrt
        mrt_source, mrt_internal = ctx.mrt_source, ctx.mrt_internal
        decision, mode, adaptive_cool = ctx.decision, ctx.mode, ctx.adaptive_cool
        heating, cooling, final_mode = ctx.heating, ctx.cooling, ctx.final_mode
        act_state, window_open, failed = ctx.act_state, ctx.window_open, ctx.failed
        override_clamped, mold_capped = ctx.override_clamped, ctx.mold_capped
        mold_min, dewpoint, sched = ctx.mold_min, ctx.dewpoint, ctx.sched
        reading_source, preheating = ctx.reading_source, ctx.preheating
        preheat_outdoor, coasting = ctx.preheat_outdoor, ctx.coasting
        frozen, norm_binding = ctx.frozen, ctx.norm_binding
        binding_precedence, sched_active = ctx.binding_precedence, ctx.sched_active
        fault_active, heat_source_suspect = ctx.fault_active, ctx.heat_source_suspect
        ext_num, operative_active = ctx.ext_num, ctx.operative_active
        climate_diag = ctx.climate_diag
        _mode_nudge_blocked = ctx.mode_nudge_blocked
        _idle_park_mode = ctx.idle_park_mode
        _mode_adopt_reason = ctx.mode_adopt_reason
        _sp_adopt_reason = ctx.sp_adopt_reason
        operative, binding = shadow.operative, shadow.binding
        _cover_peak, _cover_pos = shadow.cover_peak, shadow.cover_pos
        _cover_reason, shadow_objs = shadow.cover_reason, shadow.shadow_objs
        valve_health, closing_steps = valve.valve_health, valve.closing_steps
        idle_steps = valve.idle_steps
        # ADR-0060 §2: advisory season-mode hint — the zone's own lockout
        # thresholds define "season-wrong", T_rm's multi-day memory is the
        # "persistently"; hysteresis anchor is transient runtime state.
        # Computed BEFORE the L2 detection: its history floors that reading.
        # ``season_hint_t_rm`` keeps the hint silent when only the fabricated
        # outdoor fallback is available (t_rm_source None).
        _sugg_now = dt_util.utcnow().timestamp()
        _season_hint = season_mode_hint(
            climate_mode=self._runtime.user.climate_mode,
            t_rm=season_hint_t_rm(t_rm_eff, t_rm_source),
            heat_max_outdoor=self._c._heat_max_outdoor,
            cool_min_outdoor=self._c._cool_min_outdoor,
            prev_hint=self._runtime.diagnostics.season_hint_prev,
        )
        self._runtime.diagnostics.season_hint_prev = _season_hint
        # ADR-0060 §3 season gate: overrides recorded while the zone is
        # season-wrong are mode signals, not comfort evidence.  The stamp is
        # not dirty-marked — the periodic (30-tick) save picks it up, a crash
        # loses minutes of it at most, and the hint usually re-raises anyway.
        if _season_hint is not None:
            self._runtime.user.season_hint_last_active_ts = _sugg_now
        _l2_floor = season_gate_floor(
            hint_active=_season_hint is not None,
            last_active_ts=self._runtime.user.season_hint_last_active_ts,
            now_ts=_sugg_now,
        )
        # ADR-0060 L2 SHADOW: the suggestion the L1 statistic would raise —
        # always computed and published (the §3 field-tuning round needs the
        # would-be suggestions); the repair-issue EMISSION alone is opt-in
        # gated inside _sync_suggestion_issue.  The reading is season-gate
        # floored (§3): the raw ungated view stays reconstructable from the
        # dump (statistics + floor stamp) via the replay instrument.
        _sugg = detect_override_pattern(
            self._runtime.user.override_stats, now_ts=_sugg_now, since_ts=_l2_floor
        )
        _sugg_suppressed = _sugg is not None and suggestion_suppressed(
            _sugg.key,
            self._runtime.user.suggestion_rejected_key,
            self._runtime.user.suggestion_rejected_at,
            _sugg_now,
        )
        # ADR-0067 F2: the clo-family reading + the #4 conflict resolution
        # (never two competing readings; an open family keeps its slot).
        _fb_sugg = detect_feedback_pattern(
            self._runtime.user.feedback_stats, now_ts=_sugg_now
        )
        _fb_reason = clo_suggestion_reason(
            _fb_sugg,
            l2_pending=False,  # the collision is resolved below with slot memory
            override_direction=_sugg.direction if _sugg is not None else None,
            rejected_key=self._runtime.user.clo_suggestion_rejected_key,
            rejected_at=self._runtime.user.clo_suggestion_rejected_at,
            now_ts=_sugg_now,
        )
        _emit_l2, _emit_clo, _family = resolve_suggestion_conflict(
            l2_pending=_sugg is not None and not _sugg_suppressed,
            clo_pending=_fb_reason == "",
            open_family=self._runtime.diagnostics.pending_suggestion_family,
        )
        self._runtime.diagnostics.pending_suggestion_family = _family
        if _fb_reason == "" and not _emit_clo:
            _fb_reason = "l2_pending"
        try:
            self._c._sync_suggestion_issue(_sugg, _sugg_suppressed or not _emit_l2)
            self._c._sync_clo_suggestion_issue(_fb_sugg if _emit_clo else None)
            self._c._sync_season_hint_issue(_season_hint)
        except Exception:  # noqa: BLE001 - suggestion glue must never break the tick
            self._log.debug("Poise suggestion issue sync failed", exc_info=True)
        _tick_data: dict[str, Any] = {
            "available": True,
            **outcome_diag,
            **climate_diag,
            "dynamics_profile": self._runtime.compressor.dynamics.value,
            "pi_integral_time_h": round(
                PROFILES[self._runtime.compressor.dynamics].integral_time_h, 3
            ),
            "reg_period_s": PROFILES[
                self._runtime.compressor.dynamics
            ].regulation_period_s,
            # ADR-0046 §8 (live): the compressor-guard suppression reason this tick
            # ("" = not blocked). When set, dry_active reads as intent (queued),
            # not "drying now" — the card shows "drying soon (compressor guard)".
            "mode_nudge_blocked": _mode_nudge_blocked,
            # ADR-0038: monotonic stamp of when this snapshot was produced, so
            # the system hub can detect a silently stale zone (age-based
            # staleness).
            "mono_ts": now,
            "current_temperature": round(room, 1),
            "current_humidity": round(rh, 1) if rh is not None else None,
            "target_temperature": target,
            "operative_temperature": round(operative, 1),
            "t_rm": round(t_rm_eff, 1),
            "t_rm_source": t_rm_source,
            "t_rm_internal": (
                round(self._runtime.learning.trm_tracker.current, 1)
                if self._runtime.learning.trm_tracker.current is not None
                else None
            ),
            "q_solar": round(q_solar, 3),
            "q_solar_source": q_solar_source,
            "q_solar_internal": round(q_solar_internal, 3),
            "beta_s": round(self._runtime.learning.ekf.get_model().beta_s, 3),
            "mrt": round(t_mrt, 1),
            "mrt_source": mrt_source,
            "mrt_internal": round(mrt_internal, 1),
            "heat_sp": decision.heat_sp,
            "cool_sp": decision.cool_sp,
            "mode": mode,
            "comfort_low": decision.heat_sp,
            "comfort_high": decision.cool_sp,
            "binding_lower_cause": binding,
            "category": self._c._category.value,
            "adaptive_cool": adaptive_cool,
            "adaptive_cool_mode": adaptive_cool_mode(self._c._adaptive_cool_cfg),
            "heating": heating,
            # Display contract: publish the arbitrated direction (final_mode)
            # and the actuator's own reported action so the entity's
            # hvac_action stays truthful during an override (where the raw
            # mode is "manual") and can prefer the device's real state.
            # "cooling" is published symmetric to "heating" (raw intent) to
            # close the asymmetry.
            "cooling": cooling,
            "final_mode": final_mode,
            "actuator_hvac_action": (
                act_state.attributes.get("hvac_action") if act_state else None
            ),
            "idle_park_mode": _idle_park_mode,
            "window_open": window_open,
            "window_auto_detected": self._runtime.window.window_auto.open,
            "window_auto_threshold": round(self._runtime.window.wa_open_threshold, 1),
            "window_bypass": self._runtime.user.window_bypass,
            "preset": self._runtime.user.preset.value,
            # A mode-hold (possibly without a setpoint) is an active hold too,
            # so the Card shows the pill / "gilt bis …" / resume for it.
            "override_active": (
                self._runtime.user.override is not None
                or self._runtime.user.mode_override is not None
            ),
            "mode_override": self._runtime.user.mode_override,
            # Hold origin (ui_setpoint / device_adopt_*) + why this tick
            # did/did not adopt a device change (diagnostics; "" when nothing
            # seen).
            "override_reason": self._runtime.user.override_reason,
            "mode_adopt_reason": _mode_adopt_reason,
            "sp_adopt_reason": _sp_adopt_reason,
            # ADR-0059 §4: the manual-hold lifecycle for the Card ("gilt bis …").
            "override_expires_at": _iso_utc(self._runtime.user.override_expires_at),
            "override_policy": self._c._override_policy,
            "override_requested": self._runtime.user.override_requested,
            # ADR-0069 U1: control-readiness shadow keys — future tier wiring
            # consumes these; the diagnostic signals (pmv_valid, occupied)
            # keep their meaning untouched.
            "pmv_control_ready": pmv_control_ready(
                rh=ctx.rh, pmv_valid=ctx.climate_diag.get("pmv_valid") is True
            ),
            "presence_control_ready": presence_control_ready(ctx.occupancy),
            "room_present": room_present(ctx.occupancy),
            # ADR-0059 §5: the persisted L1 nudge log (observe-only). A shadow key
            # (absent from _ATTRS) -> diagnostics-only, never a recorded attribute.
            "override_stats": list(self._runtime.user.override_stats),
            "feedback_stats": list(self._runtime.user.feedback_stats),
            # ADR-0060 L2: the would-be suggestion (shadow keys, not _ATTRS).
            "suggestion_kind": _sugg.kind if _sugg else None,
            "suggestion_direction": _sugg.direction if _sugg else None,
            "suggestion_value": (
                (
                    _sugg.step_k
                    if _sugg.step_k is not None
                    else float(_sugg.step_min or 0)
                )
                if _sugg
                else None
            ),
            "suggestion_evidence": _sugg.evidence if _sugg else 0,
            "suggestion_suppressed": _sugg_suppressed,
            "season_hint": _season_hint,
            # ADR-0060 §3: the gate floor stamp (shadow key, not _ATTRS) — the
            # diagnostics dump lifts it next to the statistics it floors.
            "season_hint_last_active_ts": (
                self._runtime.user.season_hint_last_active_ts
            ),
            # ADR-0068 U6: fan-first observability (shadow keys, not _ATTRS).
            "fan_first_phase": self._runtime.latches.fan_first.phase,
            "fan_first_reason": self._runtime.diagnostics.fan_first_reason,
            # ADR-0069 E7 (Card): the mechanism toggle, published so the card
            # can gate the active-measure display on the real config state.
            "active_comfort": self._c._active_comfort,
            # ADR-0069 U7/U8: tier-2 latch states + the applied inputs.
            "tier2_fan_ce": (self._runtime.diagnostics.comfort_activation.fan_ce.state),
            "tier2_pmv_offset": (
                self._runtime.diagnostics.comfort_activation.pmv_offset.state
            ),
            "fan_ce_credit_k": self._runtime.latches.fan_ce_credit_k,
            "pmv_offset_k": self._runtime.latches.pmv_offset_k,
            # ADR-0067 F2: the clo-family reading ("" reason = emittable).
            "clo_suggestion_direction": _fb_sugg.direction if _fb_sugg else None,
            "clo_suggestion_evidence": _fb_sugg.evidence if _fb_sugg else 0,
            "clo_suggestion_reason": _fb_reason,
            "boost_expires_at": _iso_utc(self._runtime.user.boost_expires_at),
            "override_clamped": override_clamped,
            "cover_predicted_peak": round(_cover_peak, 1),
            "cover_would_shade": _cover_pos > 0,
            "cover_shade_position": _cover_pos,
            "cover_shade_reason": _cover_reason,
            "window_auto_slope": self._runtime.window.window_auto.ema_slope,
            "heating_failure": failed,
            "mold_capped": mold_capped,  # mould floor clipped at 24 °C
            # ADR-0057: publish the mould-protection floor + dewpoint so the card
            # can draw the "Schimmel" tick on the dial (display only, no control).
            "mould_floor": round(mold_min, 1) if mold_min is not None else None,
            "dewpoint": round(dewpoint, 1) if dewpoint is not None else None,
            "source": reading_source.value,
            "tau_hours": round(self._runtime.learning.ekf.tau_hours, 1),
            "confidence": round(self._runtime.learning.ekf.confidence, 2),
            "identified": self._runtime.learning.ekf.identified,
            "learning_phase": self._runtime.learning.ekf.learning_phase,
            "identification_progress": round(self._runtime.learning.ekf.data_factor, 2),
            "schedule_state": "comfort" if sched.is_comfort else "setback",
            "minutes_to_comfort": sched.minutes_to_comfort,
            "preheating": preheating,
            "preheat_outdoor": preheat_outdoor,
            "coasting": coasting,
            "minutes_to_setback": sched.minutes_to_setback,
            "sensor_frozen": frozen,
            "norm_binding": norm_binding,
            "binding_precedence": binding_precedence,
            "device_schedule_active": sched_active,
            "device_alarm": fault_active,
            "sensor_placement_suspect": heat_source_suspect,
            "trv_input_mode": (
                "operative" if operative_active else ("air" if ext_num else "none")
            ),
            "valve_health": valve_health,
            "valve_closing_steps": closing_steps,
            "valve_idle_steps": idle_steps,
            **shadow_objs,
            "tpi_valve_entity": self._reader.valve_entity,
            "seasonless_phase": self._runtime.learning.seasonless.phase,
            "seasonless_rate": (
                round(p, 3)
                if (
                    p := self._runtime.learning.seasonless.heat_rate_prior(
                        decision.heat_sp, t_out_eff, dt_util.now().toordinal()
                    )
                )
                is not None
                else None
            ),
        }
        # Surface this zone's own boiler heat-demand (0..1) -- exactly the
        # value the hub aggregates from our data, so per-zone visibility can't
        # drift.
        _tick_data["heat_demand"] = zone_heat_demand(
            heating=heating,
            tpi_duty=_tick_data.get("tpi_duty"),
            frozen=frozen,
        )
        return _tick_data
