"""Owner of the zone's long-lived domain state.

``ZoneRuntime`` owns the eleven typed state groups of ``runtime.state`` plus
the injectable monotonic clock. The coordinator constructs exactly one
``ZoneRuntime`` per zone and keeps every pinned ``self._*``
attribute as a property proxy onto these groups, so tests and internal readers
see unchanged names while ownership is explicit.

The runtime also owns the PURE tick stages (delegating to their implementations
in ``control/tick_pipeline.py``), ``commit_execution`` (incl. the ``EndHold``
teardown and the ``mark_actuated`` flip), and ``restore(decoded)`` — the
decoded-store application plus the deferred domain hooks (echo-window
re-stamping via the owned clock, hold-expiry normalisation with the schedule
injected as a callable, and the EKF cold-start seeding as its own
bootstrap-positioned hook). This class stays free of Home Assistant imports,
reader/executor access and any I/O throughout; stages with positioned
reads/awaits/logging remain coordinator methods and reach this state through
the property proxies.

``dirty`` is the documented exception: the persistence-meta flag is
adapter-shaped, but ``commit_execution``/``teardown_hold``/``mark_actuated``
and the observe stage mutate it as part of their pure bodies — so the flag
lives here and the coordinator's ``_dirty`` becomes a property proxy, keeping
``_maybe_save``'s decision logic unchanged in the adapter.

The ``clock`` attribute is deliberately a plain, replaceable reference:
integration tests swap ``coordinator._clock`` for a fake AFTER setup, and the
coordinator's ``_clock`` property setter forwards that swap here so every
reader (coordinator, ``InputReader``/``ForecastProvider`` via their live
forwarders) follows the same instance.

``climate_mode`` is Store-owned user intent: the config entry's options/data
value seeds only the very first start, so the coordinator injects that seed at
construction instead of relying on the dataclass default ``"auto"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..clock import Clock
from ..const import SETPOINT_ADOPT_ECHO_WINDOW_S
from ..control import external_override as _external_override
from ..control import override_runtime as _override_runtime
from ..control import tick_pipeline as _pipeline
from ..control.override import resolve_hold_expiry
from .state import (
    ActuatorRuntime,
    CompressorRuntime,
    DiagnosticsRuntime,
    ExternalOverrideRuntime,
    HumidityRuntime,
    LearningRuntime,
    PipelineLatches,
    PresenceRuntime,
    SafetyRuntime,
    UserControlState,
    WindowRuntime,
)
from .tick_result import (
    CommitResult,
    EndHold,
    OverrideEnded,
)

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable, Sequence

    from ..comfort.dual_setpoint import ComfortDecision
    from ..comfort.en16798 import Category
    from ..comfort.schedule import ComfortSchedule
    from ..control.dynamics import DeviceDynamics
    from ..control.mpc import MpcParams
    from ..control.window_auto import WindowAutoConfig
    from ..persistence.codec import DecodedPersistence
    from .tick_inputs import TickInputs
    from .tick_result import (
        ActuatorPlan,
        ClimateBandResult,
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
        PostExecutionAction,
        PreparedState,
        PresenceLevelResult,
        SafetyFloorsResult,
        ScheduleGateResult,
        SchedulePresenceResult,
        SetpointObservation,
        WriteTargetResult,
    )


class ZoneRuntime:
    """The zone's domain-state root: eleven state groups + the clock."""

    __slots__ = (
        "clock",
        "dirty",
        "user",
        "external",
        "actuator",
        "learning",
        "window",
        "presence",
        "humidity",
        "compressor",
        "safety",
        "diagnostics",
        "latches",
    )

    def __init__(self, clock: Clock, *, climate_mode: str = "auto") -> None:
        self.clock: Clock = clock
        # Persistence-meta dirty flag — see module docstring; seeded False.
        self.dirty: bool = False
        # Store-owned user intention (enable/preset/holds/Boost, ADR-0059);
        # ``climate_mode`` seeded from the entry, never the default.
        self.user = UserControlState(climate_mode=climate_mode)
        # Echo-/adoption baselines, ONE object.
        self.external = ExternalOverrideRuntime()
        # Last actuator write results + external-feed anchor.
        self.actuator = ActuatorRuntime()
        # Thermal models and observation anchors (EKF, ADR-0002/0024).
        self.learning = LearningRuntime()
        # Window-open latch + sensorless slope detector (ADR-0041).
        self.window = WindowRuntime()
        # Presence flip tracking + room-absence anchor (ADR-0058).
        self.presence = PresenceRuntime()
        # Dry-active hysteresis latch.
        self.humidity = HumidityRuntime()
        # Compressor lifecycle fold + derived dynamics profile (ADR-0046).
        self.compressor = CompressorRuntime()
        # Failure detector / prev-fail latch / sustained-unavailability anchor.
        self.safety = SafetyRuntime()
        # Long-lived diagnostic accumulators (ADR-0044/0045/0055).
        self.diagnostics = DiagnosticsRuntime()
        # Transient anti-chatter latches (preheat/coast/cool-raise).
        self.latches = PipelineLatches()

    # ------------------------------------------------------------------
    # Commit path
    # ------------------------------------------------------------------

    def teardown_hold(self, reason: str) -> OverrideEnded:
        """Clear the hold state WITHOUT firing the bus event.

        The state teardown half of the coordinator's ``_end_hold``:
        ``commit_execution``'s ``EndHold`` post-action must mutate the hold
        state but leave the ``poise_override_ended`` firing to the adapter (via
        ``CommitResult.events``, AFTER the commit returns and BEFORE the
        ``_maybe_save`` checkpoint). Every other hold end keeps using
        ``_end_hold`` (teardown + immediate fire, unchanged).

        The field teardown is the ONE pure implementation in
        ``control.override_runtime.end_hold`` (same fields, same order); this
        method keeps translating its ``CommandResult`` into the runtime dirty
        flag for the commit/teardown path.
        """
        result = _override_runtime.end_hold(self.user, reason)
        if result.dirty:
            self.dirty = True
        return result.events[0]

    def mark_actuated(self) -> None:
        """Set the teardown-park gate, persisting the flip.

        A bare ``has_actuated = True`` never set ``dirty``, so a restart
        shortly after the FIRST actuation of a run (e.g. mid a sensor outage,
        where the periodic 30-tick save is not running either) could still
        restore ``has_actuated=False`` — teardown then would not park an
        actuator Poise had, in fact, already commanded. Only the first flip
        needs to persist; repeating it is a harmless no-op write skip.
        """
        if not self.actuator.has_actuated:
            self.dirty = True
        self.actuator.has_actuated = True

    def commit_execution(
        self,
        report: ExecutionReport,
        # Sequence (not an inline variadic tuple) on purpose: an ellipsis in
        # the def signature would match the coverage exclude regex ``\.\.\.``
        # (meant for protocol stubs) and silently exclude this whole method
        # from a coverage gate. Callers pass ``TickPlan.post_actions``
        # (a tuple) unchanged.
        post_actions: Sequence[PostExecutionAction] = (),
        *,
        now: float | None = None,
    ) -> CommitResult:
        """Fold an ordered ``ExecutionReport`` into the domain state.

        The one place that mutates domain state after I/O. It folds STRICTLY
        in actual call order (``for execution in report.executions`` — never
        grouped by effect type), then applies the ordered ``post_actions``.
        ``now`` is the tick's monotonic instant (``inputs.now_mono``) for the
        timestamp stamps; commits without a timestamp stamp may omit it.

        Attempt vs. success: attempt state (``pre_write_sp``, context-id
        registration) commits even when the dispatch threw; success state
        (baselines, ``has_actuated`` + dirty) only on ``success`` — which means
        "dispatched without a synchronous exception" (``blocking=False``),
        never device-side confirmation. The ADAPTER fires
        ``CommitResult.events`` on the bus AFTER this returns (and before the
        ``_maybe_save`` checkpoint); boundary logging already happened inside
        the executor sequences.
        """
        for execution in report.executions:
            effect_id = execution.effect_id
            if effect_id == "mode_nudge":
                # Attempt state: the context id is created before the dispatch
                # and registers even when the call threw.
                if execution.attempted and execution.context_id is not None:
                    self.external.own_write_ctx_ids.append(execution.context_id)
                if execution.success:
                    # Mode echo baseline; re-arm the echo window only on a real
                    # mode CHANGE (dispatch-time evaluation).
                    if execution.mode_changed:
                        if now is None:
                            raise ValueError("mode_nudge commit needs now=")
                        self.external.last_hvac_cmd_ts = now
                    self.external.last_commanded_hvac = execution.commanded_mode
            elif effect_id == "setpoint_write":
                if execution.attempted:
                    # The attempt stamp + context-id registration survive a
                    # failed dispatch.
                    self.external.pre_write_sp = execution.pre_write_value
                    if execution.context_id is not None:
                        self.external.own_write_ctx_ids.append(execution.context_id)
                if execution.success:
                    if now is None:
                        raise ValueError("setpoint_write commit needs now=")
                    self.actuator.last_written_mode = execution.commanded_mode
                    self.external.last_sp_write_ts = now
                    # Echo baseline: the SNAPPED value, never raw wire.
                    self.external.last_written_sp = execution.commanded_value
                    self.mark_actuated()  # persist the first-actuation flip
            elif effect_id == "ext_select":
                # No domain stamp: the select's success only gates the feed
                # INSIDE the executor sequence (switched flag, ADR-0029).
                pass
            elif effect_id == "ext_feed":
                if execution.success:
                    if now is None:
                        raise ValueError("ext_feed commit needs now=")
                    self.actuator.last_fed = execution.commanded_value
                    self.actuator.last_fed_ts = now
            elif effect_id == "rescue_nudge":
                if execution.success:
                    if now is None:
                        raise ValueError("rescue_nudge commit needs now=")
                    # Our own safety mode, never a user change. Unlike the tick
                    # mode_nudge the ts stamp is UNCONDITIONAL (not
                    # mode-change-gated; own effect id on purpose).
                    self.external.last_commanded_hvac = execution.commanded_mode
                    self.external.last_hvac_cmd_ts = now
            elif effect_id == "rescue_write":
                if execution.success:
                    # The frost floor is our own value, not user intent.
                    self.external.last_written_sp = None
                    self.mark_actuated()  # persist the first-actuation flip
            elif effect_id == "safe_mode":
                if execution.success:
                    self.actuator.last_written_mode = execution.commanded_mode
                    # Our own safe-state mode is never a user change.
                    self.external.last_commanded_hvac = execution.commanded_mode
            elif effect_id == "safe_setpoint":
                if execution.success:
                    self.actuator.last_target = execution.commanded_value
                    # Never re-read our own safe floor as a user hold.
                    self.external.last_written_sp = None
                    self.mark_actuated()  # persist the first-actuation flip
            else:
                raise ValueError(f"commit_execution: unknown effect_id {effect_id!r}")
        events: list[OverrideEnded] = []
        for action in post_actions:
            if isinstance(action, EndHold):
                if action.require_success:
                    raise NotImplementedError(
                        "EndHold(require_success=True) has no defined "
                        "semantics; the only current post-action is the "
                        "frost-rescue EndHold with require_success=False"
                    )
                # Hold-state teardown WITHOUT the bus fire: the adapter fires
                # the returned OverrideEnded after the commit.
                events.append(self.teardown_hold(action.reason))
            else:
                raise ValueError(f"commit_execution: unknown post action {action!r}")
        return CommitResult(events=tuple(events))

    # ------------------------------------------------------------------
    # Restore path (codec + the deferred domain hooks)
    # ------------------------------------------------------------------

    def restore(
        self,
        decoded: DecodedPersistence,
        *,
        override_policy: str,
        override_timer_h: float,
        override_max_h: float,
        minutes_to_switchpoint: Callable[[], float | None],
    ) -> None:
        """Apply a decoded v1 store onto the live state groups.

        The codec owns the FORMAT (gates and per-key coercions); this method
        owns the DOMAIN restore semantics in order — user intent first, the
        echo-window re-stamping next to the adoption baselines, the expiry
        recompute against the CONFIG policy, the learned models last. Fields
        the codec decoded as its "leave alone" sentinel (``None`` for
        ``climate_mode``/``dry_active`` and the model fields) keep the fresh
        construction value in place.

        The config-owned hold policy/timers arrive as parameters and the
        switchpoint recompute takes the schedule lookup as an injected
        callable, evaluated ONLY under the exact recompute condition (the
        lookup reads the wall clock, which stays the adapter's business). The
        echo re-stamping uses the runtime's own clock.
        """
        user = decoded.user_state
        hold = decoded.override_lifecycle
        base = decoded.adoption_baselines
        self.user.enabled = user.enabled
        self.user.preset = user.preset
        self.user.override = hold.override
        # A restored manual mode-hold shares the setpoint hold lifecycle, so it
        # expires on real elapsed wall-clock time.
        self.user.mode_override = hold.mode_override
        # The hold's origin ("device"/"app" provenance) survives the restart
        # only while a hold actually lives (gated in the codec).
        self.user.override_reason = hold.override_reason
        # INVARIANT (B5, ADR-0059 §9): restore the adoption baseline UNGATED by
        # the hold — it describes the actuator, not the hold; without it the
        # first post-restart device change misclassifies as no_baseline and the
        # next write reverts it. Pinned by test_override_bootstrap_fixes.py.
        self.external.last_written_sp = base.last_written_sp
        self.external.prev_device_sp = base.prev_device_sp
        self.external.last_commanded_hvac = base.last_commanded_hvac
        self.external.prev_device_mode = base.prev_device_mode
        # INVARIANT (B5, ADR-0059 §9): monotonic echo windows are process-local
        # — stamp them stale on restore (only where a baseline exists) so no
        # echo reads as in-flight and the ADR-0052 §4 throttle input stays
        # honest.
        _stale = self.clock.monotonic() - SETPOINT_ADOPT_ECHO_WINDOW_S * 2.0
        if self.external.last_written_sp is not None:
            self.external.last_sp_write_ts = _stale
        if self.external.last_commanded_hvac is not None:
            self.external.last_hvac_cmd_ts = _stale
        # The wall-clock hold + Boost lifecycle (ADR-0059; hold-gated in the
        # codec; ``override_requested`` carries the stricter setpoint-hold-only
        # gate there).
        self.user.override_set_wall = hold.override_set_wall
        self.user.override_requested = hold.override_requested
        # ``hold.override_policy`` (the stored copy) is decoded for
        # observability only and deliberately NOT applied -- it is a
        # config-entry OPTION already read by the shared parser; applying it
        # would silently revert a user's option change on every restart
        # (``codec.CONFIG_OWNED_KEYS``).
        self.user.override_expires_at = hold.override_expires_at
        self.user.override_expiry_is_switchpoint = hold.override_expiry_is_switchpoint
        # A hold persisted by a pre-ADR-0059 build (or one that otherwise lost
        # its expiry) restores with ``None`` -- not "permanent" but simply
        # never computed. Recompute it now the same way a fresh override-set
        # does (CONFIG policy + live schedule, never the store), so the hold
        # still expires on real elapsed time.
        if (
            hold.hold_active
            and self.user.override_expires_at is None
            and self.user.override_set_wall is not None
        ):
            self.user.override_expires_at = resolve_hold_expiry(
                policy=override_policy,
                set_at=self.user.override_set_wall,
                timer_h=override_timer_h,
                max_h=override_max_h,
                minutes_to_switchpoint=minutes_to_switchpoint(),
            )
        self.user.boost_prev_preset = hold.boost_prev_preset
        self.user.boost_expires_at = hold.boost_expires_at
        self.user.override_stats = hold.override_stats
        self.user.window_bypass = user.window_bypass
        if user.climate_mode is not None:
            self.user.climate_mode = user.climate_mode
        # The actuation latch keeps the teardown-park gate across the restart.
        self.actuator.has_actuated = user.has_actuated
        # Heavier learned models AFTER the user intent. ``None`` (key
        # absent/non-dict, or undecoded because the sequential model parse
        # stopped at an earlier key -- surfaced via ``decoded.model_error``)
        # keeps the fresh model from construction.
        learn = decoded.learning
        if learn.ekf is not None:
            self.learning.ekf = learn.ekf
        if learn.trm_tracker is not None:
            self.learning.trm_tracker = learn.trm_tracker
        if learn.seasonless is not None:
            self.learning.seasonless = learn.seasonless
        if learn.window_auto is not None:
            self.window.window_auto = learn.window_auto
        if learn.multi_lifecycle is not None:
            # ADR-0046: the wall-clock lifecycle keeps a compressor min-off
            # counting across a restart (future stamps were clamped against
            # the ``now_wall`` anchor injected into ``decode``).
            self.compressor.multi_lifecycle = learn.multi_lifecycle
        diag = decoded.diagnostics
        if diag.outcome_stats is not None:
            self.diagnostics.outcome_stats = diag.outcome_stats
        if diag.regq is not None:
            self.diagnostics.regq = diag.regq
        if learn.ref_offset is not None:
            self.learning.ref_offset = learn.ref_offset
        if learn.tau_settle is not None:
            self.learning.tau_settle = learn.tau_settle
        if diag.hdh is not None:
            self.diagnostics.hdh = diag.hdh
        if diag.dry_active is not None:
            self.humidity.dry_active = diag.dry_active  # survive restart

    def seed_ekf_cold_start(
        self,
        *,
        comfort_base: float,
        day_ordinal_fn: Callable[[], int],
    ) -> None:
        """Cold-start prior (ADR-0004): seed beta_h from the seasonless
        estimate only while the EKF has never observed heating (e.g. new
        season); once it learns from real heating it owns the parameter
        (never parallel).

        Run UNCONDITIONALLY after the restore boundary — also on the
        fresh/legacy/corrupt paths, so it is deliberately NOT folded into
        ``restore``. The calendar lookup arrives as a callable and is evaluated
        only under the exact seed condition.
        """
        if self.learning.ekf.n_heating == 0 and self.learning.seasonless.phase in (
            "learning",
            "mature",
        ):
            t_out = self.learning.seasonless.mean_outdoor
            if t_out is not None:
                prior = self.learning.seasonless.heat_rate_prior(
                    comfort_base, t_out, day_ordinal_fn()
                )
                if prior is not None:
                    self.learning.ekf.seed_beta_h(prior)

    # ------------------------------------------------------------------
    # Pure prepare stages (implementations in control/tick_pipeline.py)
    # ------------------------------------------------------------------

    def stage_ingest(
        self,
        inputs: TickInputs,
        air: float,
        *,
        entry_id: str,
        temp_entity: str,
        actuator_entity: str,
        sched_entity: str | None,
        adaptive_mode_entity: str | None,
        fault_entity: str | None,
        battery_entity: str | None,
        is_frozen_fn: Callable[[float | None, float], bool],
        ingest_temperature_fn: Callable[..., Any],
    ) -> IngestResult:
        """Health flags + temperature/environment ingest."""
        return _pipeline.stage_ingest(
            self,
            inputs,
            air,
            entry_id=entry_id,
            temp_entity=temp_entity,
            actuator_entity=actuator_entity,
            sched_entity=sched_entity,
            adaptive_mode_entity=adaptive_mode_entity,
            fault_entity=fault_entity,
            battery_entity=battery_entity,
            is_frozen_fn=is_frozen_fn,
            ingest_temperature_fn=ingest_temperature_fn,
        )

    def stage_observe(
        self,
        inputs: TickInputs,
        ing: IngestResult,
        *,
        entry_id: str,
        windows: list[str],
        actuator_entity: str,
        window_auto_cfg: WindowAutoConfig,
        adaptive_cool_cfg: str | bool,
        dynamics_override: DeviceDynamics | None,
        effective_window_open_fn: Callable[..., bool],
        set_mpc_params: Callable[[MpcParams], None],
        logger: logging.Logger,
    ) -> ObservationResult:
        """Window signals, capability, dynamics retune, learn gate."""
        return _pipeline.stage_observe(
            self,
            inputs,
            ing,
            entry_id=entry_id,
            windows=windows,
            actuator_entity=actuator_entity,
            window_auto_cfg=window_auto_cfg,
            adaptive_cool_cfg=adaptive_cool_cfg,
            dynamics_override=dynamics_override,
            effective_window_open_fn=effective_window_open_fn,
            set_mpc_params=set_mpc_params,
            logger=logger,
        )

    def stage_safety_floors(
        self,
        ing: IngestResult,
        *,
        entry_id: str,
        humidity_entity: str | None,
        psychro_dewpoint_fn: Callable[[float, float], float],
    ) -> SafetyFloorsResult:
        """Mould floor + dewpoint cap from humidity."""
        return _pipeline.stage_safety_floors(
            ing,
            entry_id=entry_id,
            humidity_entity=humidity_entity,
            psychro_dewpoint_fn=psychro_dewpoint_fn,
        )

    def stage_schedule_gate(
        self,
        inputs: TickInputs,
        ing: IngestResult,
        obs: ObservationResult,
        *,
        schedule: ComfortSchedule,
        optimal_start: bool,
        optimal_stop: bool,
    ) -> ScheduleGateResult:
        """Schedule state + predictive decision."""
        return _pipeline.stage_schedule_gate(
            self,
            inputs,
            ing,
            obs,
            schedule=schedule,
            optimal_start=optimal_start,
            optimal_stop=optimal_stop,
        )

    def stage_comfort_solve(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        sp: SchedulePresenceResult,
        op: OperativeResult,
        lvl: PresenceLevelResult,
        *,
        category: Category,
        cool_min_outdoor: float,
        cool_lockout_enabled: bool,
        heat_max_outdoor: float,
        heat_lockout_enabled: bool,
        priority: float,
        cool_hard_cap: float,
        comfort_decide_fn: Callable[..., ComfortDecision],
    ) -> ComfortDecision:
        """The central comfort solver."""
        return _pipeline.stage_comfort_solve(
            self,
            ing,
            obs,
            floors,
            sp,
            op,
            lvl,
            category=category,
            cool_min_outdoor=cool_min_outdoor,
            cool_lockout_enabled=cool_lockout_enabled,
            heat_max_outdoor=heat_max_outdoor,
            heat_lockout_enabled=heat_lockout_enabled,
            priority=priority,
            cool_hard_cap=cool_hard_cap,
            comfort_decide_fn=comfort_decide_fn,
        )

    def stage_intents(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
    ) -> IntentsResult:
        """Heat/cool intent + EKF drive latches (ADR-0024)."""
        return _pipeline.stage_intents(self, ing, obs, wt)

    def stage_mode_resolution(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        op: OperativeResult,
        wt: WriteTargetResult,
        band: ClimateBandResult,
        *,
        cool_min_outdoor: float,
        cool_lockout_enabled: bool,
        heat_max_outdoor: float,
        heat_lockout_enabled: bool,
        compressor_guard: str,
        comp_min_off_opt: float | None,
        comp_mode_hold_opt: float | None,
    ) -> ModeResolutionResult:
        """Mode arbitration + compressor-guard policy."""
        return _pipeline.stage_mode_resolution(
            self,
            ing,
            obs,
            op,
            wt,
            band,
            cool_min_outdoor=cool_min_outdoor,
            cool_lockout_enabled=cool_lockout_enabled,
            heat_max_outdoor=heat_max_outdoor,
            heat_lockout_enabled=heat_lockout_enabled,
            compressor_guard=compressor_guard,
            comp_min_off_opt=comp_min_off_opt,
            comp_mode_hold_opt=comp_mode_hold_opt,
        )

    def stage_setpoint_observe(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
        nudge: ModeNudgeResult,
        *,
        actual_sp: float | None,
        step: float,
        adopt_external_setpoint: bool,
        setpoint_adopt_reason_fn: Callable[..., str],
    ) -> SetpointObservation:
        """Setpoint observation, §4 throttle, echo re-baseline, with the
        unified decision+reason observation."""
        return _pipeline.stage_setpoint_observe(
            self,
            ing,
            obs,
            wt,
            res,
            routing,
            nudge,
            actual_sp=actual_sp,
            step=step,
            adopt_external_setpoint=adopt_external_setpoint,
            setpoint_adopt_reason_fn=setpoint_adopt_reason_fn,
        )

    def stage_hold_routing(
        self,
        wt: WriteTargetResult,
        *,
        end_hold_fn: Callable[[str], None],
    ) -> HoldRoutingResult:
        """Own-write echo + off-hold routing + escape (implementation in
        ``control/external_override.py``)."""
        return _external_override.stage_hold_routing(self, wt, end_hold_fn=end_hold_fn)

    def stage_mode_adoption(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
        *,
        adopt_external_mode: bool,
        resolve_desired_mode_fn: Callable[..., str],
        mode_adopt_reason_fn: Callable[..., str],
        set_mode_override_fn: Callable[[str], None],
        end_hold_fn: Callable[[str], None],
    ) -> ModeAdoptionResult:
        """External-mode adoption, mode-hold freeze, hold pinning
        (implementation in ``control/external_override.py``)."""
        return _external_override.stage_mode_adoption(
            self,
            ing,
            obs,
            wt,
            res,
            routing,
            adopt_external_mode=adopt_external_mode,
            resolve_desired_mode_fn=resolve_desired_mode_fn,
            mode_adopt_reason_fn=mode_adopt_reason_fn,
            set_mode_override_fn=set_mode_override_fn,
            end_hold_fn=end_hold_fn,
        )

    def stage_setpoint_adopt(
        self,
        ing: IngestResult,
        spo: SetpointObservation,
        *,
        mode_adopt_reason: str,
        actuator_entity: str,
        logger: logging.Logger,
        set_override_fn: Callable[..., None],
    ) -> str:
        """Diagnosis surfacing, debounced log, prev-update and the adoption
        itself (implementation in ``control/external_override.py``)."""
        return _external_override.stage_setpoint_adopt(
            self,
            ing,
            spo,
            mode_adopt_reason=mode_adopt_reason,
            actuator_entity=actuator_entity,
            logger=logger,
            set_override_fn=set_override_fn,
        )

    def plan_setpoint_write(
        self,
        wt: WriteTargetResult,
        adoption: ModeAdoptionResult,
        nudge: ModeNudgeResult,
        spo: SetpointObservation,
    ) -> ActuatorPlan:
        """Setpoint write gate -> the tick's ``ActuatorPlan``."""
        return _pipeline.plan_setpoint_write(self, wt, adoption, nudge, spo)

    def build_finalize_context(
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
        """Assemble the prepare->finalize contract."""
        return _pipeline.build_finalize_context(
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
