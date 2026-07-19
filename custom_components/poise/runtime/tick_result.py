"""Tick control contract: plans, effects, reports and outcomes (plan phase 1).

These types carry one coordinator tick through its target flow (refactoring
plan, architecture diagram): the prepare phase produces a ``TickPlan`` (with a
``ForecastRequest`` handshake via ``PrepareContinuation``), the executor turns
the plan's effects into an ordered ``ExecutionReport``, ``commit_execution``
folds that report plus the plan's ``post_actions`` into a ``CommitResult``,
and ``finalize_tick`` yields the ``TickOutcome`` whose ``data`` is the only
thing the presenter ever sees.

Phase-1 scope: pure type definitions. Nothing in ``coordinator.py`` imports
this module yet; the wiring happens in phases 5A/5B/6 of
docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md. All line references
below point into today's ``coordinator.py`` (3,827-line state).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class PersistencePhase(Enum):
    """Where in the tick flow the persistence checkpoint sits (finding 12).

    The save *decision* (dirty/cadence) stays in the adapter's ``_maybe_save``;
    this directive only models the two checkpoint *positions* that exist today:

    * ``AFTER_EXECUTION`` — normal tick: save after ``commit_execution`` and
      the ``CommitResult.events``, before ``finalize_tick`` (Z. 3327), so the
      snapshot contains the *previous* tick's finalize-owned state.
    * ``BEFORE_EXECUTION`` — unavailable path: the dirty flush runs before the
      safe-state write (Z. 2018–2019).

    Normalising the checkpoint is F-SAVEPOINT (phase 10 only).
    """

    NONE = "none"
    BEFORE_EXECUTION = "before_execution"
    AFTER_EXECUTION = "after_execution"


# ---------------------------------------------------------------------------
# Effects — fully decided write intents. The executor performs I/O only; every
# gate (throttle, guard, deadband, off-hold) is resolved before these exist.
# The per-effect executor vocabulary (e.g. ``SetMode`` for the mode nudge,
# plan section 5.4 Z. 2942–2964) is deliberately NOT defined here: phase 5A
# owns it together with the executor, so the two cannot drift apart.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActuatorPlan:
    """The decided actuator write for this tick (write gate Z. 3144–3163).

    The plan carries the DECISION, the executor only performs it: online gate,
    adoption skip, off-hold (K2), compressor-guard defer (P2-3), §4 regulation
    throttle and the ``should_write`` deadband are all resolved by the
    pipeline. ``snapped_setpoint`` is the step-normalised value the device is
    asked for — the executor never re-decides or re-quantises.
    """

    write_mode: bool
    hvac_mode: str | None
    write_setpoint: bool
    snapped_setpoint: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class ExternalTemperaturePlan:
    """TRV external-temperature select/feed sequence (finding 11, Z. 3191–3240).

    The sequence is *conditional*, and that is behaviour: on the tick the
    sensor-select is switched to "external" successfully, the value feed is
    skipped so the device can settle; if the select fails (or none is needed),
    the feed still runs. ``skip_feed_on_select_success`` freezes that coupling
    in the contract so the executor reproduces it exactly.
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
    (after the writes) — see finding 6.
    """

    reason: str


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of an out-of-tick command method (finding 6).

    Commands such as ``set_override(None)`` fire their bus event immediately
    (Z. 638 → 763), not on the next tick: the adapter fires ``events`` right
    away and marks the store dirty when ``dirty`` is set.
    """

    events: tuple[OverrideEnded, ...] = ()
    dirty: bool = False


# ---------------------------------------------------------------------------
# Post-execution actions — ordered domain mutations applied by the commit
# AFTER the report fold (findings 6+9).
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
    """End the active hold after execution (frost rescue, Z. 3324–3325).

    ``require_success=False`` is deliberate: the frost-rescue hold ends
    regardless of whether the rescue writes succeeded — the gate conditions
    (off-held ∧ rescue ∧ online) are known at plan time (Z. 3279), so the
    hold-end must never be coupled to ``EffectExecution.success`` (findings
    6+9, phase-0 frost-rescue matrix).
    """

    reason: str
    require_success: bool = False


# ---------------------------------------------------------------------------
# Health updates and stage failure transport (finding 13).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HealthUpdate:
    """One repair-issue transition, mirroring the ``_issue()`` primitive.

    Field-for-field mirror of ``_issue(issue_id, active, *, translation_key,
    placeholders)`` (Z. 1274–1281). ``placeholders`` carries the translation
    placeholders shown in the repair issue — real emission sites depend on
    them (external_temp_implausible ``{entity, name}`` Z. 1352–1357,
    heating_failure ``{zone}`` Z. 1646–1651, valve_stuck Z. 3510–3515), so
    dropping them would lose observable diagnosis. Stages return these
    instead of touching the issue registry; the coordinator emits them at
    stage checkpoints whose positions preserve today's emission points
    relative to the awaits (finding 13).
    """

    issue_id: str
    active: bool
    translation_key: str
    placeholders: Mapping[str, str] | None = None


class TickStageError(Exception):
    """A prepare/finalize stage failed; carries the not-yet-emitted health
    updates (finding 13).

    Repair issues are emitted *during* the tick today — earlier issues stay
    set/cleared even when a later step fails. When a stage aborts, the
    coordinator emits ``pending_health_updates`` and re-raises ``cause`` so
    the F12 failure counting in ``_async_update_data`` stays unchanged.
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
# Forecast handshake and the prepare -> finalize context (findings 5, 12).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    """Ask the coordinator for a forecast with the tick-current horizon.

    ``horizon_min`` is the exact optimal-start lead in minutes (Z. 2222–2247);
    ``fallback`` is the outdoor value to use when the provider degrades. The
    runtime never performs the weather I/O itself — the coordinator resolves
    the request at today's position under the lock (finding 5).
    """

    horizon_min: float
    fallback: float


@dataclass(frozen=True, slots=True)
class PreparedState:
    """Opaque carrier for the prepare-phase state across the forecast seam.

    ``prepare_until_forecast`` stops at the predictive decision; whatever it
    already computed must survive until ``resume_prepare`` without leaking
    into the coordinator. Deliberately field-less in phase 1 — the concrete
    fields are established in phase 6, mirroring ``FinalizeContext``.
    """


@dataclass(frozen=True, slots=True)
class FinalizeContext:
    """Explicit prepare→finalize intermediate-value contract.

    ``finalize_tick(plan.finalize_context)`` receives everything it needs from
    the prepare phase through this object instead of implicit locals (plan
    rev. 7). Deliberately slim in phase 1: the concrete fields are added in
    phase 6 when ``_run_once()`` is actually split — guessing them now would
    just recreate the 173-local problem in frozen form.
    """


@dataclass(frozen=True, slots=True)
class PrepareContinuation:
    """Result of ``prepare_until_forecast(inputs)`` (forecast handshake).

    ``forecast_request`` is only set when the predictive path needs outdoor
    data this tick; the coordinator then calls ``ForecastProvider.resolve``
    at today's position under the lock and passes the result into
    ``resume_prepare(prep, forecast)`` (finding 5). ``prepared_state`` carries
    the interrupted prepare-phase state across that seam.
    """

    forecast_request: ForecastRequest | None
    prepared_state: PreparedState


# ---------------------------------------------------------------------------
# Tick plan — output of the prepare phase, input to executor and commit.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TickPlan:
    """Everything the prepare phase decided for this tick.

    ``pre_events`` fire before the writes (hold expiry, preheat-edge hold
    end); ``post_actions`` are applied by ``commit_execution`` after the
    report fold (finding 6). ``persistence`` places the save checkpoint
    (finding 12). ``control_data`` carries the live control values that
    finalize/diagnostics consume; ``finalize_context`` is the explicit
    prepare→finalize handover. An unavailable tick can still carry a
    safe-state plan and events (finding 4).
    """

    actuator_plan: ActuatorPlan | None
    external_temperature_plan: ExternalTemperaturePlan | None
    pre_events: tuple[OverrideEnded, ...]
    post_actions: tuple[PostExecutionAction, ...]
    persistence: PersistencePhase
    control_data: Mapping[str, object]
    finalize_context: FinalizeContext


# ---------------------------------------------------------------------------
# Execution report and commit result (findings 9, 11).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EffectExecution:
    """Attempt/success record of one executed effect (finding 9).

    ``attempted`` state (``pre_write_value`` stamped, ``context_id``
    registered at creation) exists even when the call fails; success state
    (baselines, ``has_actuated``) is committed only on ``success``.
    ``success`` means the service call *dispatched* without a synchronous
    exception: all effect calls run ``blocking=False`` and HA swallows
    handler errors in the background task, so the per-effect boundaries only
    ever see synchronous dispatch errors (phase-0 finding 1 in the plan's
    phase-0 status box). Never interpret it as device-side confirmation.
    """

    effect_id: str
    attempted: bool
    success: bool
    context_id: str | None
    pre_write_value: float | None
    commanded_value: float | None


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """Ordered record of what the executor actually did.

    ``executions`` is ORDERED in actual call order, and ``commit_execution``
    folds strictly in that order (``for execution in report.executions``) —
    today's code mutates state between the individual calls, so grouping by
    effect type would change behaviour (finding 9).
    """

    executions: tuple[EffectExecution, ...]


@dataclass(frozen=True, slots=True)
class CommitResult:
    """Events produced by ``commit_execution(report, post_actions)``.

    The adapter fires these after the commit — e.g. ``OverrideEnded
    ("frost_rescue")`` after the rescue writes (Z. 3324–3325, finding 6).
    """

    events: tuple[OverrideEnded, ...] = ()


# ---------------------------------------------------------------------------
# Public data contract — the only shapes the presenter ever sees (finding 4).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class AvailableTickData:
    """Public per-tick data of an available zone.

    The presenter sees ONLY this form or ``UnavailableTickData`` — never
    ``TickPlan``/``TickOutcome`` internals. The mandatory fields are the hub
    contract (``hub_coordinator``/``hub_aggregate`` readers): ``tpi_duty``
    and ``heat_demand`` are LIVE boiler-request inputs with defined
    fallbacks, not diagnosis shadows (findings 1+4). Phase-0 baseline:
    today's available payload carries 156 keys — the remaining keys reach the
    presenter later via ``control_data``/``diagnostics``, not as fields here.
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

    Deliberately minimal — today's degraded payload is ``{"available":
    False}`` plus ``unavailable_safe`` once the safe state engaged
    (Z. 2039–2040); the entity availability gate relies on nothing else being
    present (Z. 1842–1844).
    """

    available: Literal[False] = False
    unavailable_safe: bool


@dataclass(frozen=True, slots=True)
class TickOutcome:
    """Result of ``finalize_tick`` — data, diagnostics and the trace record.

    ``data`` is the public contract (one of the two forms above);
    ``diagnostics`` the collected shadow/diagnosis values; ``trace_record``
    the pure-built record whose append stays the last statement under the
    lock until F-TRACEIO (finding 5).
    """

    data: AvailableTickData | UnavailableTickData
    diagnostics: Mapping[str, object]
    trace_record: Mapping[str, object] | None
