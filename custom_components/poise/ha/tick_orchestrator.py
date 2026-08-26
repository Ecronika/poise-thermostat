"""Tick SEQUENCER — the per-tick program's order, seams and checkpoints.

``coordinator.py`` keeps only the HA coupling (``DataUpdateCoordinator``
lifecycle, the tick lock, ``tick_ms``/``TickBudget``, persistence, health
issues and the entity-facing command API).  Everything between "the lock is
held" and "a payload is returned" is driven from here — but since plan step
O.5 the STAGE BODIES live in four phase modules and this class is only their
sequencer:

    ha/phase_prepare.py   PreparePhase   17 stages, await-free
    ha/phase_actuate.py   ActuatePhase   14 stages + the unavailable safe-state
                                         body; ALL eight executor awaits
    ha/phase_shadow.py    ShadowPhase     9 segments, await-free
    ha/phase_report.py    ReportPhase     2 assembly stages, await-free

What stays HERE: ``_run_once``, ``prepare_until_forecast``, ``resume_prepare``,
``finalize_tick``, ``_run_unavailable_tick``, ``_build_finalize_context``, the
trace ownership (``_maybe_record_trace``, ``flush_traces``,
``_trace_recorder``/``_trace_slug``) and ``_write_unavailable_safe_state`` as a
THIN FACADE onto ``ActuatePhase`` (see the method's docstring for the chain).

WHY THE CUT RUNS HERE (plan section 5).  The phase boundary follows the AWAIT
TOPOLOGY, not a wished-for domain taxonomy: the await positions, the commit
positions and the fact that the prepare/shadow/report halves contain no I/O at
all are what the behaviour proofs rest on.  The forecast seam
(``prepare_until_forecast`` / ``resume_prepare``) is an orchestration hook in
THIS class, not a phase boundary — the stages on both sides of it belong to
``PreparePhase``.

Receiver rules (binding): collaborators are the injected attributes, every
coordinator EFFECT goes through ``self._ports.<x>`` (a ``SequencerPorts`` view
— eight capabilities, and deliberately no ``commit_execution``: nothing in the
sequencer commits any more) and the two per-tick read views through
``self._source`` (both from ``ha/tick_ports.py``); the logger is the injected
``self._log`` (the logger CHANNEL is behaviour: records must keep the name
``custom_components.poise.coordinator``).  Await positions, commit positions,
event/emission positions and checkpoint positions are behaviour.

Error boundaries are narrow by design (ADR-0065) and travelled with their
bodies: one boundary per shadow segment in ``ShadowPhase``, two independent
boundaries in ``PreparePhase._stage_climate_band``.  The trace append is queued
off the lock (ADR-0063), the forecast fetch is a background refresh (ADR-0063)
and the persistence checkpoint sits behind ``finalize_tick`` (ADR-0064).

PATCH SURFACE (binding, plan O.4/O.5).  **Patch where the name is looked up,
not where it is defined.**  The nine owner-module fault-injection points moved
with their stages — eight to ``ha/phase_prepare.py``, one
(``control.cover_shading.predict_peak_operative``) to ``ha/phase_shadow.py`` —
and their patch targets are UNCHANGED by that move, because each names the
OWNING module rather than the caller.  That property is exactly why O.4 chose
the form; ``tests/integration/test_o4_patch_surface.py`` proves per name that
the patch still bites.  This module keeps ONE patch target of its own,
``build_tick_record``: it belongs to the trace function, not to a stage, so it
is still bound and patched here
(``…poise.ha.tick_orchestrator.build_tick_record``).

DISPATCH BACK THROUGH THE COORDINATOR (binding).  Every call a test may replace
on the coordinator INSTANCE is resolved there at CALL time — in the port
adapter now, no longer here.  The six targets (plan section 4.4):
``_write_unavailable_safe_state`` (test_phase0_persistence_checkpoint),
``_maybe_record_trace`` (test_phase8_presenter), ``_forecast_outdoor``
(test_forecast_backoff / test_glue_coverage4 / test_phase5a_wiring),
``commit_execution`` (test_phase5b_sequences), ``_maybe_save`` (the persistence
checkpoint) and ``_health.emit`` (the health checkpoint — a HealthReporter
method, resolved through ``coordinator._health`` and therefore substituted by
replacing the REPORTER, not the method).  Nothing may snapshot any of them as a
bound method; ``ha/tick_ports.py`` carries that duty and
``tests/integration/test_o3_late_binding.py`` proves per target that a
replacement takes effect.

PER-TICK READ VIEWS (plan O.2/O.3).  The 39 attributes the tick only READS are
gone: ``ZoneBindings`` (wiring, 9) and ``TickConfigSnapshot`` (tick-stable
policy, 30) are built once per tick through ``self._source`` and handed on
EXPLICITLY — ``bindings`` as a parameter, ``config`` as a field of
``PreparedState``/``FinalizeContext``.  Neither is ever stored on ``self``: an
implicit ``self._config`` would only rename the coupling this removes.  Both
build positions are behaviour, proven in ``_run_once`` (bindings, before the
availability gate) and ``prepare_until_forecast`` (config, after it).

PORTS INSTEAD OF A BACKREFERENCE (plan O.3/O.5).  ``self._c`` is gone.  The 20
coordinator capabilities the tick INVOKES are five narrow ``Protocol`` views in
``ha/tick_ports.py``, one per phase; since O.5 each holder is typed against
just its own view and the transitional union is gone.  This class sees
``SequencerPorts`` (8) and nothing else.  The stable collaborators are injected
constructively instead of being read off the coordinator: ``self._hass`` and
``self._reader`` — which already WAS the coordinator's ``_input_reader``.

CAPABILITY NARROWING (binding, plan section 9).  This module holds no
``ActuatorExecutor``, no ``ForecastProvider`` and no ``DiagnosticsCollector``:
each went to the single phase that uses it (actuate / prepare / report).  The
composition root ``coordinator.py`` builds the four phase objects and hands
them in, so the sequencer cannot reach past the phase it is calling.

STATE OWNED HERE.  ``_trace_recorder`` (the lazily built ADR-0011 trace
writer) and ``_trace_slug`` (the ADR-0022 salted slug in production; the
coordinator seeds it) belong to this class — the only reader,
``_maybe_record_trace``, lives here.  Nothing outside may read them (pinned
by ``tests/integration/test_phase6b_state_move.py``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..comfort.dual_setpoint import ComfortDecision
from ..comfort.operative import operative_temperature
from ..const import (
    DEFAULT_TRACE_MAX_BYTES,
    UNAVAILABLE_SAFE_AFTER_S,
)
from ..diagnostics.shadows import (
    neutral_shadow_objs,
)
from ..diagnostics.trace import build_tick_record
from ..estimation.thermal_ekf import ThermalModel
from ..runtime.tick_result import (
    ActuatorPlan,
    AvailableTickData,
    CalibrationPlan,
    ClimateBandResult,
    ExternalTemperaturePlan,
    FinalizeContext,
    HealthUpdate,
    IntentsResult,
    ModeResolutionResult,
    OperativeResult,
    PersistencePhase,
    PrepareContinuation,
    PreparedState,
    SchedulePresenceResult,
    ShadowStageResult,
    TickOutcome,
    TickPlan,
    TickStageError,
    UnavailableTickData,
    WriteTargetResult,
)
from ..runtime.zone_runtime import ZoneRuntime
from ..safety.sensor_watchdog import (
    unavailable_safe_engaged,
)
from ..trace.recorder import TraceRecorder
from .input_reader import InputReader
from .presenter import present as _present
from .tick_snapshot import TickConfigSnapshot, ZoneBindings

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from .phase_actuate import ActuatePhase
    from .phase_prepare import PreparePhase
    from .phase_report import ReportPhase
    from .phase_shadow import ShadowPhase
    from .tick_ports import SequencerPorts, TickSnapshotSource


class TickOrchestrator:
    """Sequences the per-tick program; one instance per ``PoiseCoordinator``.

    Constructed at the very end of ``PoiseCoordinator.__init__`` so every
    collaborator below already exists.  All of them are assigned exactly once
    in that ``__init__`` and never rebound, so snapshotting the references here
    cannot drift from the coordinator's own view.

    The four phase objects are built by that same composition root and handed
    in ready-made (plan O.5): this class owns the ORDER of the stages, the
    seams between them and the checkpoints, never a stage body.
    """

    __slots__ = (
        "_actuate",
        "_hass",
        "_log",
        "_ports",
        "_prepare",
        "_reader",
        "_report",
        "_runtime",
        "_shadow",
        "_source",
        "_trace_recorder",
        "_trace_slug",
    )

    def __init__(
        self,
        ports: SequencerPorts,
        *,
        source: TickSnapshotSource,
        hass: HomeAssistant,
        logger: logging.Logger,
        runtime: ZoneRuntime,
        input_reader: InputReader,
        prepare: PreparePhase,
        actuate: ActuatePhase,
        shadow: ShadowPhase,
        report: ReportPhase,
        trace_slug: str,
    ) -> None:
        # The eight sequencer capabilities and the two per-tick read views —
        # see ``ha/tick_ports.py``.
        self._ports = ports
        self._source = source
        # The coordinator module's own logger: the channel
        # ``custom_components.poise.coordinator`` is behaviour, so it is
        # injected rather than created here.
        self._log = logger
        self._runtime = runtime
        self._hass = hass
        self._reader = input_reader
        # The four phase objects (plan O.5). Each holds its own narrow port
        # view and its own collaborators; the executor, the forecast provider
        # and the diagnostics collector are deliberately NOT reachable from
        # here any more.
        self._prepare = prepare
        self._actuate = actuate
        self._shadow = shadow
        self._report = report
        # No checkpoint is snapshotted here: the six late-binding targets stay
        # resolvable on the coordinator instance, which is the port adapter's
        # duty (see the module docstring's dispatch rules).
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
        config: TickConfigSnapshot,
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
        if not config.trace_enabled:
            return
        try:
            if self._trace_recorder is None:
                path = self._hass.config.path(
                    "poise_traces", f"{self._trace_slug}.jsonl"
                )
                self._trace_recorder = TraceRecorder(
                    self._hass, path, DEFAULT_TRACE_MAX_BYTES
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

    async def _write_unavailable_safe_state(self, bindings: ZoneBindings) -> None:
        """Thin facade onto ``ActuatePhase.write_unavailable_safe_state`` (O.5).

        The BODY of this node -- the safe-state resolve, the executor sequence
        and the commit -- is an actuation body and lives with the other five
        executor awaits in ``ha/phase_actuate.py``: within the tick execution
        only ``ActuatePhase`` may hold the executor (capability narrowing, plan
        section 9). What stays HERE is the position and the dispatch node, so
        the replaceable stop on the chain is exactly the one it always was:

            _run_unavailable_tick
              -> SequencerPorts.write_unavailable_safe_state()
              -> PoiseCoordinator._write_unavailable_safe_state()  # THE patch
              -> this facade
              -> ActuatePhase.write_unavailable_safe_state()       # the body

        ``tests/integration/test_o3_late_binding.py`` and
        ``test_phase0_persistence_checkpoint.py`` pin that chain per link.
        """
        await self._actuate.write_unavailable_safe_state(bindings)

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

        ``bindings`` is built HERE, before the availability gate (plan O.2):
        the gate's first HA state read IS ``bindings.temp``, the unavailable
        short-circuit needs ``temp``/``actuator``/``zone_name``, and a
        constructor copy would be stale (``async_bootstrap``
        resets ``_trv_ext_temp`` at bootstrap). It reads attributes only — no
        HA read, no I/O — so nothing observable moves ahead of the gate.
        """
        bindings = self._source.bindings()
        try:
            prep = self.prepare_until_forecast(bindings)
            if isinstance(prep, TickPlan):
                # Unavailable short-circuit: the plan carries the DIRTY_ONLY
                # persistence directive, and that checkpoint runs at the END
                # of the short-circuit (see ``_run_unavailable_tick``).
                return await self._run_unavailable_tick(prep, bindings)
            # Forecast handshake: the await runs under the tick lock, under
            # exactly the condition ``forecast_request`` exists iff the
            # ``predictive`` gate held and the upcoming schedule transition
            # exists (P2.1 None-contract) -- and with the tick-current lead
            # horizon plus the fallback value. The await stays in the adapter
            # so the prepare phase itself performs no I/O; F-FORECAST
            # (phase 10) is the only place this may ever move.
            if prep.forecast_request is not None:
                forecast: float | None = await self._ports.forecast_outdoor(
                    prep.forecast_request.horizon_min, prep.forecast_request.fallback
                )
            else:
                forecast = None
            plan = await self.resume_prepare(prep, forecast, bindings)

            # pre_events seam: the hold-expiry and preheat-edge events fire
            # IMMEDIATELY inside the prepare stages, synchronously under the
            # lock — and a synchronous bus listener MAY write coordinator
            # state that later prepare stages read. Deferring those fires to
            # this seam is therefore NOT provably unobservable; the events
            # keep firing at their in-stage positions and ``pre_events`` stays
            # an EMPTY structural seam.
            for event in plan.pre_events:
                self._ports.fire_override_ended(event.reason)

            # apply → commit(post_actions) → CommitResult.events: already
            # executed as the ordered in-stage program (``resume_prepare``);
            # the frost-rescue segment fired its ``CommitResult.events`` after
            # the rescue writes.
            ctx = plan.finalize_context
            assert ctx is not None  # resume_prepare always builds it
            outcome = await self.finalize_tick(ctx, bindings)

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
                await self._ports.save_if_due()
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
        self._ports.emit_health(pending)
        raise cause

    async def _run_unavailable_tick(
        self, plan: TickPlan, bindings: ZoneBindings
    ) -> dict[str, Any]:
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
        if not self._ports.unavailable_logged:
            self._log.warning(
                "Poise %s: room temperature sensor %s is unavailable; "
                "holding the entity in its last state until it returns",
                bindings.zone_name,
                bindings.temp,
            )
            self._ports.unavailable_logged = True
        # A sustained loss must not hold a stale comfort setpoint indefinitely
        # (critical in external-feed mode). After the timeout, degrade to the
        # frost/mould floor -- the same safe state as a frozen sensor (fail
        # toward warmth).
        engaged = unavailable_safe_engaged(
            now_mono - self._runtime.safety.unavailable_since,
            UNAVAILABLE_SAFE_AFTER_S,
        )
        if engaged:
            await self._ports.write_unavailable_safe_state(bindings)
        # A user intent set via the switch/select (enabled / preset / mode)
        # while the room sensor is down must still be persisted — this path
        # never reaches the normal checkpoint. DIRTY_ONLY: no periodic cadence
        # save while the sensor is down, and positioned AFTER the safe-state
        # write so its ``has_actuated`` flip goes to disk with it (F-SAVEPOINT).
        if plan.persistence is PersistencePhase.DIRTY_ONLY and self._runtime.dirty:
            await self._ports.save_if_due()
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

    def prepare_until_forecast(
        self, bindings: ZoneBindings
    ) -> PrepareContinuation | TickPlan:
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

        ``config`` (the ``TickConfigSnapshot``) is built HERE, after the gate
        passed and just before the pre-await snapshot (plan O.2). Proof: the
        unavailable short-circuit reads NO snapshot field — it and
        ``_write_unavailable_safe_state`` touch only bindings and ports — so
        an earlier build would be blind work on the commonest degraded path;
        it does no HA read, so its exact position is unobservable anyway.
        """
        # Positioned first read: the availability gate must run BEFORE the
        # pre-await snapshot — on an unavailable tick neither the guard
        # discovery nor any other read of the segment runs, and that error
        # path stays read-for-read identical.
        air = self._reader.read(bindings.temp)
        # Availability-gate checkpoint [1]: emitted at its EXACT statement
        # position (trivially position-identical), both directions. The
        # constraint holds by construction: the checkpoint lies BEFORE every
        # await of the tick and — on the unavailable path — BEFORE the
        # short-circuit return, hence before ``_run_once``'s persistence/apply
        # evaluation and the DIRTY_ONLY dirty-flush save.
        self._ports.emit_health(
            (
                HealthUpdate(
                    issue_id=f"sensor_unavailable_{bindings.entry_id}",
                    active=air is None,
                    translation_key="sensor_unavailable",
                    placeholders={"entity": bindings.temp},
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
        if self._ports.unavailable_logged:
            self._log.info(
                "Poise %s: room temperature sensor %s is back; resuming control",
                bindings.zone_name,
                bindings.temp,
            )
            self._ports.unavailable_logged = False
        # The tick's config view — see the position proof in the docstring.
        config = self._source.config()
        # ONE snapshot bundles the contiguous pre-first-await read block.
        # Within this await-free segment nothing can change between reads, so
        # the re-read of the room here is provably the value the gate above
        # saw, and the segment's ad-hoc clock reads unify onto the snapshot
        # instants (sub-ms, unobservable). Every read AFTER the first await
        # stays a positioned InputReader call at exactly its place in the tick.
        inputs = self._reader.snapshot()
        ing = self._prepare._stage_ingest(inputs, air, bindings)
        # Ingest checkpoint [2-8]: the seven device-health updates, emitted at
        # the stage boundary within the same await-free segment (position
        # proof in the docstring above).
        self._ports.emit_health(ing.health_updates)
        obs = self._prepare._stage_observe(inputs, ing, bindings, config)
        # Observe checkpoint: window_sensor_unavailable, emitted mid-stage
        # before the reset — same await-free-segment proof.
        self._ports.emit_health(obs.health_updates)
        floors = self._prepare._stage_safety_floors(ing, bindings)
        # Safety-floors checkpoint: mould_protection_inactive, emitted at the
        # end of the block — same proof.
        self._ports.emit_health(floors.health_updates)
        gate = self._prepare._stage_schedule_gate(inputs, ing, obs, config)
        return PrepareContinuation(
            forecast_request=gate.forecast_request,
            prepared_state=PreparedState(
                inputs=inputs,
                ingest=ing,
                observation=obs,
                floors=floors,
                sched=gate.sched,
                config=config,
            ),
        )

    async def resume_prepare(
        self, prep: PrepareContinuation, forecast: float | None, bindings: ZoneBindings
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
        # Plan O.2: the config view crossed the forecast seam inside the
        # carrier; every stage below takes it as an explicit parameter.
        config = state.config
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
        sp = self._prepare._stage_schedule_presence(
            ing, obs, sched, config, t_out_lead=t_out_lead, model=model
        )
        op = self._prepare._stage_operative_mode(inputs, ing, bindings, config)
        # Operative checkpoint: operative_unsupported, emitted mid-stage.
        # POSITION PROOF: that position and this checkpoint sit in the SAME
        # await-free window (between the forecast await and the
        # failure-detect/mode-nudge dispatches) — no suspension point between
        # them, so no other task can interleave; same
        # single-thread/registry-listener rationale as the prepare
        # checkpoints (``prepare_until_forecast`` docstring).
        self._ports.emit_health(op.health_updates)
        lvl = self._prepare._stage_presence_level(ing, obs, sched, sp, config)
        decision = self._prepare._stage_comfort_solve(
            ing, obs, floors, sp, op, lvl, config
        )
        wt = self._prepare._stage_write_target(ing, obs, floors, op, decision, config)
        band = self._prepare._stage_climate_band(
            ing, obs, sp, lvl, op, decision, wt, bindings, config
        )
        intents = self._prepare._stage_intents(ing, obs, wt)
        # ``_notify_failure``'s body is purely synchronous (awaiting a
        # never-suspending coroutine runs it to completion on the calling task
        # without yielding to the loop), so the plain call is
        # scheduling-identical at this position.
        failed = self._prepare._stage_failure_detect(ing, wt, intents)
        ff = self._prepare._stage_fan_first(ing, obs, sched, sp, op, wt, config)
        res = self._actuate._stage_mode_resolution(
            ing, obs, op, wt, band, config, fan_first_requested=ff.requested
        )
        routing = self._actuate._stage_hold_routing(wt)
        # Branch-dependent values: the defaults from the resolution and
        # routing stages hold on the disabled / off-held path; the enabled
        # path's stages return the updated values.
        guard_block = res.guard_block
        mode_nudge_blocked = res.mode_nudge_blocked
        mode_adopt_reason = routing.mode_adopt_reason
        sp_adopt_reason = routing.sp_adopt_reason
        actuator_plan: ActuatorPlan | None = None
        ext_plan: ExternalTemperaturePlan | None = None
        cal_plan: CalibrationPlan | None = None
        if self._runtime.user.enabled and not routing.off_held:
            adoption = self._actuate._stage_mode_adoption(
                ing, obs, wt, res, routing, config
            )
            mode_adopt_reason = adoption.mode_adopt_reason
            nudge = await self._actuate._stage_mode_nudge(
                ing,
                obs,
                wt,
                res,
                adoption,
                bindings,
                mode_nudge_blocked=mode_nudge_blocked,
            )
            guard_block = nudge.guard_block
            mode_nudge_blocked = nudge.mode_nudge_blocked
            await self._actuate._stage_fan_write(ing, wt, band, ff, bindings, config)
            spo = self._actuate._stage_setpoint_observe(
                ing, obs, wt, res, routing, nudge, config
            )
            sp_adopt_reason = self._actuate._stage_setpoint_adopt(
                ing, obs, routing, spo, bindings, mode_adopt_reason=mode_adopt_reason
            )
            actuator_plan = await self._actuate._stage_setpoint_write(
                ing, wt, res, adoption, nudge, spo, bindings
            )
            # C.8: convergence checkpoint emission — synchronous, directly
            # after the setpoint segment folded this tick's evidence (same
            # in-flow emission style as ``_notify_failure``).
            self._ports.notify_convergence(
                self._runtime.safety.convergence.escalated(now=ing.now)
            )
            # Segment H (P1.4): the fail-closed calibration ownership handoff
            # sits BETWEEN the setpoint write and the ext-temp feed (D3). Its
            # health updates are emitted right after the stage call (F19).
            handoff = await self._actuate._stage_calibration_handoff(
                ing, op, wt, bindings, config
            )
            self._ports.emit_health(handoff.health_updates)
            if not handoff.handoff_pending:
                # While the handoff is pending the successor compensation
                # must not start on the still-active offset — the ext-temp
                # feed (and later the P3 valve segment, which must honour
                # the same handoff_pending skip) waits this tick out.
                ext_plan = await self._actuate._stage_ext_temp_feed(ing, op)
            # Segment W (P1.4): the calibration regulation write, after the
            # ext-temp segment (mutually exclusive with a handoff dispatch —
            # W runs only when calibration IS the live path).
            calw = await self._actuate._stage_calibration_write(
                ing, op, wt, bindings, config
            )
            self._ports.emit_health(calw.health_updates)
            cal_plan = handoff.plan if handoff.plan is not None else calw.plan
            # Display latches for the report phase: the verdicts travel in
            # the typed stage results and the SEQUENCER stamps the latches —
            # the calibration stages themselves stay report-pure (their only
            # domain mutations are the commit and the two pre-I/O folds).
            self._runtime.diagnostics.cal_handoff_pending = handoff.handoff_pending
            self._runtime.diagnostics.cal_diverged = calw.diverged
        else:
            # C.8: the disabled/off-hold/rescue path regulates nothing — the
            # rescue writes are safety floors, never folded as convergence
            # evidence — so no convergence claim survives here: end both
            # episodes and CLEAR the issue (transition-only would otherwise
            # hold it forever on this path, including one re-adopted from
            # the store after a restart). Re-arms from fresh evidence within
            # ~CONV_FAIL_WRITES ticks + CONV_FAIL_MIN_S after re-enable.
            self._runtime.safety.convergence.reset()
            self._ports.notify_convergence(False)
            # P1.4: the calibration segments run only on the enabled path —
            # reset the per-tick display latches so a stale verdict from the
            # last enabled tick never survives into the disabled display.
            self._runtime.diagnostics.cal_handoff_pending = False
            self._runtime.diagnostics.cal_diverged = False
            actuator_plan = await self._actuate._stage_frost_rescue(
                ing, obs, floors, wt, routing, bindings
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
            calibration_plan=cal_plan,
        )

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

        Body in ``pipeline_finalize.build_finalize_context`` via the runtime; the
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

    async def finalize_tick(
        self, ctx: FinalizeContext, bindings: ZoneBindings
    ) -> TickOutcome:
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
        shadow = self._shadow._stage_shadow_domain(ctx, neutral, bindings)
        valve = self._shadow._stage_valve_health(bindings)
        # Valve checkpoint: kept at its EXACT position — the ORDER relative
        # to the stages around it is behaviour. No ``TickStageError`` wrap
        # either: the emission is immediate, nothing can be stranded.
        self._ports.emit_health(valve.health_updates)
        outcome_diag = self._report._stage_outcome_diag(ctx)
        _tick_data = self._report._stage_assemble_tick_data(
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
        await self._ports.record_trace(
            _tick_data,
            room=room,
            t_out=t_out_eff,
            rh=rh,
            t_rm=t_rm_eff,
            now=now,
            config=ctx.config,
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
