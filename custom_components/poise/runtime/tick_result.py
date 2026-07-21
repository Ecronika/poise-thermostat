"""Tick control contract: plans, effects, reports and outcomes.

These types carry one coordinator tick through its flow: the prepare phase
produces a ``TickPlan`` (with a ``ForecastRequest`` handshake via
``PrepareContinuation``), the executor turns the plan's effects into an ordered
``ExecutionReport``, ``commit_execution`` folds that report plus the plan's
``post_actions`` into a ``CommitResult``, and ``finalize_tick`` yields the
``TickOutcome`` whose ``data`` is the only thing the presenter ever sees.

The executor sequences (``ha/actuator_executor.py``) build ``EffectExecution``/
``ExecutionReport`` and the coordinator's ``commit_execution`` folds them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from homeassistant.core import State

    from ..comfort.dual_setpoint import ComfortDecision
    from ..comfort.presence import PresenceLevel
    from ..comfort.schedule import ScheduleState
    from ..comfort.thermal_shock import AdaptiveCool
    from ..contracts import Reading, Source
    from ..multi.lifecycle import LifecyclePolicy
    from .tick_inputs import PresenceSnapshot, TickInputs


class PersistencePhase(Enum):
    """Where in the tick flow the persistence checkpoint sits.

    The save *decision* (dirty/cadence) stays in the adapter's ``_maybe_save``;
    this directive only models the two checkpoint *positions* that exist:

    * ``AFTER_EXECUTION`` — normal tick: save after ``commit_execution`` and
      the ``CommitResult.events``, before ``finalize_tick``, so the snapshot
      contains the *previous* tick's finalize-owned state.
    * ``BEFORE_EXECUTION`` — unavailable path: the dirty flush runs before the
      safe-state write.
    """

    NONE = "none"
    BEFORE_EXECUTION = "before_execution"
    AFTER_EXECUTION = "after_execution"


# ---------------------------------------------------------------------------
# Effects — fully decided write intents. The executor performs I/O only; every
# gate (throttle, guard, deadband, off-hold) is resolved before these exist.
# The per-effect executor vocabulary (e.g. ``SetMode`` for the mode nudge) is
# deliberately NOT defined here: the executor owns it, so the two cannot drift
# apart.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActuatorPlan:
    """The decided actuator write for this tick.

    The plan carries the DECISION, the executor only performs it: online gate,
    adoption skip, off-hold, compressor-guard defer, §4 regulation throttle and
    the ``should_write`` deadband are all resolved by the pipeline — the
    executor never re-decides or re-quantises.

    Honest wire/baseline split: ``raw_setpoint`` is the value that goes ON THE
    WIRE (``ActuatorCommand.value=target`` is raw, NOT snapped);
    ``snapped_setpoint`` is the step-normalised echo baseline the commit stamps
    (``snap_to_step(target, step)`` → ``last_written_sp``). Both are None when
    no setpoint write was decided. The tick's actuation is an ordered
    multi-segment program, so on the enabled path ``write_mode``/``hvac_mode``
    RECORD the mode-nudge segment's decision (executed at its mandatory earlier
    position) while ``write_setpoint``/``*_setpoint`` gate the setpoint segment.
    A ``reason="frost_rescue"`` plan carries the floor in ``raw_setpoint`` only
    (the rescue commit clears the echo baseline, ``last_written_sp=None``, so
    there is no snapped baseline to carry).
    """

    write_mode: bool
    hvac_mode: str | None
    write_setpoint: bool
    snapped_setpoint: float | None
    reason: str
    raw_setpoint: float | None = None


@dataclass(frozen=True, slots=True)
class ExternalTemperaturePlan:
    """TRV external-temperature select/feed sequence.

    The sequence is *conditional*, and that is behaviour: when the sensor-select
    is switched to "external" successfully, the value feed is skipped so the
    device can settle; if the select fails (or none is needed), the feed still
    runs. ``skip_feed_on_select_success`` freezes that coupling in the contract
    so the executor reproduces it exactly.
    """

    select_external: bool
    feed_value: float | None
    skip_feed_on_select_success: bool = True


# ---------------------------------------------------------------------------
# Domain events and out-of-tick command results.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OverrideEnded:
    """A hold/override ended; the HA adapter turns this into the bus event.

    The domain decides and mutates hold state; only the adapter fires events.
    Depending on origin this travels via ``CommandResult`` (immediately),
    ``TickPlan.pre_events`` (before the writes) or ``CommitResult.events``
    (after the writes).
    """

    reason: str


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of an out-of-tick command method.

    Commands such as ``set_override(None)`` fire their bus event immediately,
    not on the next tick: the adapter fires ``events`` right away and marks the
    store dirty when ``dirty`` is set.
    """

    events: tuple[OverrideEnded, ...] = ()
    dirty: bool = False


# ---------------------------------------------------------------------------
# Post-execution actions — ordered domain mutations applied by the commit
# AFTER the report fold.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PostExecutionAction:
    """Base for ordered domain actions the commit applies after the report fold.

    These are not mere events: the domain mutates state (e.g. hold teardown)
    and the resulting events surface via ``CommitResult.events``. Kept as a
    small closed hierarchy — two event phases, no action engine.
    """


@dataclass(frozen=True, slots=True)
class EndHold(PostExecutionAction):
    """End the active hold after execution (frost rescue).

    ``require_success=False`` is deliberate: the frost-rescue hold ends
    regardless of whether the rescue writes succeeded — the gate conditions
    (off-held ∧ rescue ∧ online) are known at plan time, so the hold-end must
    never be coupled to ``EffectExecution.success``.
    """

    reason: str
    require_success: bool = False


# ---------------------------------------------------------------------------
# Health updates and stage failure transport.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HealthUpdate:
    """One repair-issue transition, mirroring the ``_issue()`` primitive.

    Field-for-field mirror of ``_issue(issue_id, active, *, translation_key,
    placeholders)``. ``placeholders`` carries the translation placeholders
    shown in the repair issue — real emission sites depend on them
    (external_temp_implausible ``{entity, name}``, heating_failure ``{zone}``,
    valve_stuck), so dropping them would lose observable diagnosis. Stages
    return these instead of touching the issue registry; the coordinator emits
    them at stage checkpoints whose positions preserve the emission points
    relative to the awaits.
    """

    issue_id: str
    active: bool
    translation_key: str
    placeholders: Mapping[str, str] | None = None


class TickStageError(Exception):
    """A prepare/finalize stage failed; carries the not-yet-emitted health
    updates.

    Repair issues are emitted *during* the tick — earlier issues stay
    set/cleared even when a later step fails. When a stage aborts, the
    coordinator emits ``pending_health_updates`` and re-raises ``cause`` so the
    failure counting in ``_async_update_data`` stays unchanged.
    """

    def __init__(
        self,
        cause: BaseException,
        pending_health_updates: tuple[HealthUpdate, ...] = (),
    ) -> None:
        super().__init__(f"tick stage failed: {cause!r}")
        self.cause = cause
        self.pending_health_updates = pending_health_updates


# ---------------------------------------------------------------------------
# Forecast handshake and the prepare -> finalize context.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    """Ask the coordinator for a forecast with the tick-current horizon.

    ``horizon_min`` is the exact optimal-start lead in minutes; ``fallback`` is
    the outdoor value to use when the provider degrades. The runtime never
    performs the weather I/O itself — the coordinator resolves the request at
    its position under the lock.
    """

    horizon_min: float
    fallback: float


# ---------------------------------------------------------------------------
# Prepare/resume stage results. Each stage of the split ``_run_once`` returns
# one of these typed values instead of leaking loose tick locals. Field names
# deliberately mirror the tick-local names they replace.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class IngestResult:
    """Ingest & environment stage: health flags, the temperature ingest and
    the T_rm/q_solar/MRT selections.

    ``health_updates``: the device-health evaluations (actuator_unavailable,
    sensor_frozen, device_schedule, adaptive_mode_active, device_alarm,
    low_battery, sensor_at_heat_source) collected in emission order instead of
    being written to the issue registry mid-stage; the coordinator emits them
    at the stage-end checkpoint.
    """

    now: float
    frozen: bool
    sched_active: bool
    fault_active: bool
    heat_source_suspect: bool
    reading: Reading
    room: float
    rh: float | None
    t_out_eff: float
    t_rm_eff: float
    t_rm_source: str | None
    q_solar: float
    q_solar_source: str
    q_solar_internal: float
    t_mrt: float
    mrt_source: str
    mrt_internal: float
    health_updates: tuple[HealthUpdate, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationResult:
    """Window/capability/learning observations.

    ``health_updates``: window_sensor_unavailable, both directions, collected
    at its evaluation point."""

    window_open: bool
    can_heat: bool
    can_cool: bool
    adaptive_cool: bool
    device_max: float
    health_updates: tuple[HealthUpdate, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SafetyFloorsResult:
    """Mould floor + dewpoint cap.

    ``health_updates``: mould_protection_inactive, both directions, collected
    at its evaluation point."""

    mold_min: float | None
    mold_capped: bool
    dewpoint: float | None
    health_updates: tuple[HealthUpdate, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduleGateResult:
    """Schedule state + predictive decision.

    The forecast seam: ``forecast_request`` is set iff the ``predictive`` gate
    held, with the tick-current lead horizon.
    """

    sched: ScheduleState
    forecast_request: ForecastRequest | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SchedulePresenceResult:
    """House gate, hold expiry, preheat/coast plan."""

    home: bool | None
    presence: PresenceSnapshot
    base: float
    preheating: bool
    preheat_outdoor: float | None
    coasting: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class OperativeResult:
    """Operative TRV-input mode (ADR-0029).

    ``health_updates``: operative_unsupported, both directions, collected at
    its evaluation point."""

    ext_num: str | None
    ext_ok: bool
    operative_active: bool
    room_decide: float
    t_mrt_decide: float | None
    health_updates: tuple[HealthUpdate, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PresenceLevelResult:
    """Presence level, room absence, eco widen."""

    level: PresenceLevel
    absent_min: float
    occupied: bool
    eco_widen: float
    cool_ceiling: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class WriteTargetResult:
    """Actuator snapshot + write-target resolution.

    ``act_state`` is the tick's ONE central positioned actuator read (after the
    forecast await); every later attribute access this tick reads this object,
    never a fresh read.
    """

    act_state: State | None
    actuator_online: bool
    cool_ac: AdaptiveCool | None
    idle_park_mode: str | None
    eff_cool: float
    target: float
    mode: str
    norm_binding: str | None
    binding_precedence: str | None
    override_clamped: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ClimateBandResult:
    """LEGACY climate-band domain output.

    ``climate_diag`` is the already-degraded assembly of the ONE shared
    boundary; ``hum_action`` drives the LIVE dry mode-nudge and degrades to
    ``"idle"`` with it.
    """

    climate_diag: Mapping[str, object]
    hum_action: str


@dataclass(frozen=True, slots=True, kw_only=True)
class IntentsResult:
    """Heat/cool intent + EKF drive latches."""

    heating: bool
    cooling: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ModeResolutionResult:
    """Mode arbitration + compressor-guard policy.

    ``guard_block``/``mode_nudge_blocked`` carry the defaults (resolved
    unconditionally, also while disabled); the enabled path's mode-nudge stage
    returns the updated values.
    """

    final_mode: str
    act_modes: list[str]
    guard_pol: LifecyclePolicy | None
    g_min_off: float
    g_mode_hold: float
    guard_block: str | None
    mode_nudge_blocked: str


@dataclass(frozen=True, slots=True, kw_only=True)
class HoldRoutingResult:
    """Own-write echo + off-hold routing.

    ``mode_adopt_reason``/``sp_adopt_reason`` carry the ``""`` defaults that
    stay in place on the disabled / off-held path.
    """

    own_change: bool
    off_held: bool
    hold_resumed: bool
    mode_adopt_reason: str
    sp_adopt_reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ModeAdoptionResult:
    """External-mode adoption + hold pinning."""

    desired_hvac: str
    mode_adopt_reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ModeNudgeResult:
    """Mode-nudge decision + dispatch."""

    mode_nudge: bool
    guard_block: str | None
    mode_nudge_blocked: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SetpointObservation:
    """Device setpoint observation + external-setpoint detection.

    ``sp_adopt_reason``: the full diagnosis code, computed together with
    ``adopted_sp`` by the ONE ``observe_setpoint`` call in the observe stage
    and carried here to the adoption stage (which otherwise re-derived it from
    character-equal arguments). Defaults to ``""`` (the disabled/off-held
    default) so direct constructions stay valid.
    """

    actual_sp: float | None
    step: float
    mode_changed: bool
    reg_throttled: bool
    adopted_sp: float | None
    sp_adopt_reason: str = ""


# ---------------------------------------------------------------------------
# Finalize stage results. ``finalize_tick`` is split into stage methods; these
# carry the cross-stage values. The two mapping-valued stages (collector
# boundary, ``_tick_data`` assembly) deliberately return their dict directly:
# the collector contract IS the replace-on-success dict, and the assembly's
# dict OBJECT is the pinned presenter/trace aliasing contract — a wrapper would
# only obscure both.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ShadowStageResult:
    """LEGACY shadow-domain stage output.

    Built once as the NEUTRAL seed by ``finalize_tick`` BEFORE the domain's ONE
    ``try`` (the degraded payload: its ``shadow_objs`` deliberately lacks the
    two ``compressor_gate_*`` keys, so the degraded available key set shrinks by
    exactly those two) and once more by ``_stage_shadow_domain`` from its
    finishing locals, which keep any partial progress a mid-domain failure left
    behind (e.g. a computed ``cover_peak`` next to the neutral ``shadow_objs``).
    """

    operative: float
    binding: str
    cover_peak: float
    cover_pos: float
    cover_reason: str
    shadow_objs: Mapping[str, object]


@dataclass(frozen=True, slots=True, kw_only=True)
class ValveHealthResult:
    """Valve-stuck stage output.

    ``closing_steps``/``idle_steps`` come from the POSITIONED fresh read after
    the savepoint await. ``health_updates`` carries the finalize segment's only
    issue emission (valve_stuck, with its ``{entity}`` placeholder); the
    coordinator emits it immediately after the stage call — between the
    savepoint await and the trace await, the exact position.
    """

    closing_steps: float | None
    idle_steps: float | None
    valve_health: str
    health_updates: tuple[HealthUpdate, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PreparedState:
    """Carrier for the prepare-phase state across the forecast seam.

    ``prepare_until_forecast`` stops at the predictive decision; everything it
    already computed survives until ``resume_prepare`` as the typed stage
    results above.
    """

    inputs: TickInputs
    ingest: IngestResult
    observation: ObservationResult
    floors: SafetyFloorsResult
    sched: ScheduleState


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizeContext:
    """Explicit prepare→finalize intermediate-value contract.

    ``finalize_tick(ctx)`` receives EXACTLY the tick locals the post-savepoint
    segment consumes — 50 free names, one of which (``reading``) is narrowed to
    its only consumed attribute (``reading_source``, the ``"source"``
    diagnostic key). No more, no less — an honest contract instead of 50
    implicit locals.

    Deliberately NOT frozen here (live ``self._*`` reads that stay positioned
    AFTER the savepoint await, where concurrency is observable — a
    ``set_override`` service call arriving during the save must be visible in
    the published payload): ``_enabled``, ``_override``, ``_mode_override``,
    ``_preset``, ``_override_reason``/``_expires``/``_requested``/``_stats``,
    ``_boost_expires_at``, ``_window_bypass`` and every learning/diagnostics
    runtime the finalize segment itself advances.

    ``act_state`` is the tick's ONE central positioned actuator read and
    ``climate_diag`` is the legacy climate-band domain's already-degraded
    assembly.
    """

    # -- clock / ingest / environment ---------------------------------------
    now: float
    room: float
    room_decide: float
    reading_source: Source
    rh: float | None
    dewpoint: float | None
    mold_min: float | None
    mold_capped: bool
    t_out_eff: float
    t_rm_eff: float
    t_rm_source: str | None
    q_solar: float
    q_solar_source: str
    q_solar_internal: float
    t_mrt: float
    mrt_source: str
    mrt_internal: float
    # -- schedule / window / comfort -----------------------------------------
    sched: ScheduleState
    frozen: bool
    window_open: bool
    decision: ComfortDecision
    eff_cool: float
    mode: str
    target: float
    final_mode: str
    norm_binding: str | None
    binding_precedence: str | None
    override_clamped: bool
    heating: bool
    cooling: bool
    failed: bool
    adaptive_cool: bool
    preheating: bool
    preheat_outdoor: float | None
    coasting: bool
    # -- actuator / compressor guard (diagnosis frozen BEFORE observe) -------
    act_state: State | None
    guard_pol: LifecyclePolicy | None
    g_min_off: float
    g_mode_hold: float
    guard_block: str | None
    mode_nudge_blocked: str
    idle_park_mode: str | None
    # -- adoption / diagnostics ----------------------------------------------
    mode_adopt_reason: str
    sp_adopt_reason: str
    climate_diag: Mapping[str, object]
    sched_active: bool
    fault_active: bool
    heat_source_suspect: bool
    ext_num: str | None
    operative_active: bool


@dataclass(frozen=True, slots=True)
class PrepareContinuation:
    """Result of ``prepare_until_forecast()`` (forecast handshake).

    ``forecast_request`` is only set when the predictive path needs outdoor
    data this tick; the coordinator then calls ``ForecastProvider.resolve`` at
    its position under the lock and passes the result into
    ``resume_prepare(prep, forecast)``. ``prepared_state`` carries the
    interrupted prepare-phase state across that seam. ``prepare_until_forecast``
    owns the availability gate and returns the unavailable short-circuit
    ``TickPlan`` INSTEAD of this continuation on a sensor-loss tick (union
    return).
    """

    forecast_request: ForecastRequest | None
    prepared_state: PreparedState


# ---------------------------------------------------------------------------
# Tick plan — output of the prepare phase, input to executor and commit.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TickPlan:
    """Everything the prepare phase decided for this tick.

    ``pre_events`` fire before the writes (hold expiry, preheat-edge hold end);
    ``post_actions`` are applied by ``commit_execution`` after the report fold.
    ``persistence`` places the save checkpoint. ``control_data`` carries the
    live control values that finalize/diagnostics consume; ``finalize_context``
    is the explicit prepare→finalize handover. An unavailable tick can still
    carry a safe-state plan and events.

    Transitional semantics, each documented at the producing site:
    ``pre_events``/``post_actions`` are EMPTY structural seams — the
    expiry/preheat events fire at their in-stage positions (a deferral to the
    coordinator seam has no unobservability proof; synchronous bus listeners
    may write state that later prepare stages read) and the rescue ``EndHold``
    is applied by the rescue segment's own commit at its position.
    ``finalize_context`` is None exactly on the unavailable short-circuit (no
    finalize segment); there ``actuator_plan`` is also None because the
    ``SafeStatePlan`` decision is positioned AFTER the BEFORE_EXECUTION save
    (no reorder proof exists for moving the outage clock read / actuator read
    into the prepare phase).
    """

    actuator_plan: ActuatorPlan | None
    external_temperature_plan: ExternalTemperaturePlan | None
    pre_events: tuple[OverrideEnded, ...]
    post_actions: tuple[PostExecutionAction, ...]
    persistence: PersistencePhase
    control_data: Mapping[str, object]
    finalize_context: FinalizeContext | None


# ---------------------------------------------------------------------------
# Execution report and commit result.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EffectExecution:
    """Attempt/success record of one executed effect.

    ``attempted`` state (``pre_write_value`` stamped, ``context_id``
    registered at creation) exists even when the call fails; success state
    (baselines, ``has_actuated``) is committed only on ``success``.
    ``success`` means the service call *dispatched* without a synchronous
    exception: all effect calls run ``blocking=False`` and HA swallows handler
    errors in the background task, so the per-effect boundaries only ever see
    synchronous dispatch errors. Never interpret it as device-side
    confirmation. ``attempted=False`` records a planned effect the sequence
    skipped: the unavailable-safe setpoint after a mode dispatch error (one
    shared boundary) and the ext-temp feed after a successful select switch
    (ADR-0029 settle tick).

    ``effect_id`` vocabulary (one id per commit rule): ``mode_nudge``,
    ``setpoint_write``, ``ext_select``, ``ext_feed``, ``rescue_nudge``,
    ``rescue_write``, ``safe_mode``, ``safe_setpoint``. The rescue nudge is
    deliberately NOT the tick ``mode_nudge``: it stamps ``last_hvac_cmd_ts``
    unconditionally, while the tick nudge is gated via ``mode_changed``.

    ``commanded_value`` semantics per effect (the commit stamps THESE, so the
    executor must never store the raw wire value where a baseline is meant):
    ``setpoint_write`` -> the SNAPPED target (``snap_to_step(target, step)``,
    the echo baseline — the wire itself carries the raw value);
    ``safe_setpoint`` -> the resolved safe floor (-> ``last_target``);
    ``ext_feed`` -> the fed value (-> ``last_fed``); ``rescue_write`` -> the
    rescue floor (diagnosis only — the commit sets ``last_written_sp=None``).

    ``commanded_mode`` carries the mode STRING an effect stamps (a float field
    cannot): ``mode_nudge`` -> desired hvac (-> ``last_commanded_hvac``);
    ``setpoint_write`` -> ``final_mode`` (-> ``last_written_mode`` — yes, a
    mode string on a setpoint effect); ``safe_mode`` -> the safe plan's hvac
    mode (-> BOTH ``last_written_mode`` and ``last_commanded_hvac``);
    ``rescue_nudge`` -> ``"heat"``.

    ``mode_changed`` is the flag for the tick mode nudge ONLY: evaluated at
    dispatch time (``desired_hvac != last_commanded_hvac``, before the stamp)
    because the commit runs after the sequence and could not recompute it once
    the baseline moved.

    Deliberately NO exception field: the executor logs INSIDE its boundary via
    the injected coordinator logger (channel, text, level, traceback and timing
    unchanged), so the commit never needs the original exception. Reproducing
    the record at commit time instead would reorder the log stream at the
    multi-call sites (frost rescue, unavailable safe).
    """

    effect_id: str
    attempted: bool
    success: bool
    context_id: str | None
    pre_write_value: float | None
    commanded_value: float | None
    commanded_mode: str | None = None
    mode_changed: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """Ordered record of what the executor actually did.

    ``executions`` is ORDERED in actual call order, and ``commit_execution``
    folds strictly in that order (``for execution in report.executions``) — the
    code mutates state between the individual calls, so grouping by effect type
    would change behaviour.
    """

    executions: tuple[EffectExecution, ...]


@dataclass(frozen=True, slots=True)
class CommitResult:
    """Events produced by ``commit_execution(report, post_actions)``.

    The adapter fires these after the commit — e.g.
    ``OverrideEnded("frost_rescue")`` after the rescue writes.
    """

    events: tuple[OverrideEnded, ...] = ()


# ---------------------------------------------------------------------------
# Public data contract — the only shapes the presenter ever sees.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class AvailableTickData:
    """Public per-tick data of an available zone.

    The presenter sees ONLY this form or ``UnavailableTickData`` — never
    ``TickPlan``/``TickOutcome`` internals. The mandatory fields are the hub
    contract (``hub_coordinator``/``hub_aggregate`` readers): ``tpi_duty`` and
    ``heat_demand`` are LIVE boiler-request inputs with defined fallbacks, not
    diagnosis shadows. The remaining keys reach the presenter via
    ``control_data``/``diagnostics``, not as fields here.
    """

    available: Literal[True] = True
    mono_ts: float
    heating: bool
    sensor_frozen: bool
    current_temperature: float | None
    heat_sp: float | None
    tpi_duty: float | None
    heat_demand: float


@dataclass(frozen=True, slots=True, kw_only=True)
class UnavailableTickData:
    """Public per-tick data of an unavailable zone (pristine contract).

    Deliberately minimal — the degraded payload is ``{"available": False}``
    plus ``unavailable_safe`` once the safe state engaged; the entity
    availability gate relies on nothing else being present.
    """

    available: Literal[False] = False
    unavailable_safe: bool


@dataclass(frozen=True, slots=True)
class TickOutcome:
    """Result of ``finalize_tick`` — data, diagnostics and the trace record.

    ``data`` is the public contract (one of the two forms above);
    ``diagnostics`` the collected shadow/diagnosis values; ``trace_record`` the
    pure-built record whose append stays the last statement under the lock.
    """

    data: AvailableTickData | UnavailableTickData
    diagnostics: Mapping[str, object]
    trace_record: Mapping[str, object] | None
