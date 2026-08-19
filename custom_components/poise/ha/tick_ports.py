"""The tick program's write-side ports onto the coordinator (plan step O.3).

O.2 removed the 39 READ attributes from ``TickOrchestrator._c``. What was left
were 20 distinct capabilities the tick INVOKES (commands, checkpoints and two
pieces of adapter-owned state) plus three stable collaborators. This module
replaces the remaining backreference with explicit, typed contracts:

* five narrow ``Protocol`` views — one per phase of the O.5 split — whose
  union is exactly those 20 capabilities. Since O.5 each holder is typed
  against exactly ONE of them (``TickOrchestrator`` → ``SequencerPorts``,
  ``PreparePhase`` → ``PreparePorts``, …); the transitional union view that
  O.3 needed while a single class still held all five capability groups no
  longer exists, and the structure gate keeps it that way;
* ``TickSnapshotSource``, the READ role: it hands out the two per-tick
  snapshots from O.2 (``ZoneBindings``/``TickConfigSnapshot``) that the
  orchestrator used to build from ``self._c`` directly. Reading and acting stay
  separate roles on purpose;
* ``CoordinatorTickPorts``/``CoordinatorSnapshotSource``, the only objects in
  the tick-orchestration and phase chain that know a ``PoiseCoordinator``.

NO SERVICE LOCATOR (binding, plan O.3). A ``__getattr__`` forwarding to the
coordinator would be ``self._c`` under a new name; it is forbidden here, also
as a transitional form, and ``tests/test_tick_chain_structure.py`` enforces
that plus the absence of any ``getattr(self._c, <variable>)``. Every port is
written out with its real signature.

WHY FIVE VIEWS AND NOT ONE. A single 20-method protocol handed to every phase
would let ``ShadowPhase`` type-check a ``commit_execution`` call. The views are
measured from the actual call sites per method group, not designed:

    SequencerPorts  8  emit_health, save_if_due, record_trace,
                       forecast_outdoor, write_unavailable_safe_state,
                       fire_override_ended, notify_convergence,
                       unavailable_logged (read AND write)
    PreparePorts    5  end_hold, expire_timed_states, notify_failure,
                       notify_cooling_failure, set_mpc_params
    ActuatePorts    5  end_hold, fire_override_ended, set_mode_override,
                       set_override, commit_execution
    ShadowPorts     1  mpc_params (read only)
    ReportPorts     3  sync_suggestion_issue, sync_clo_suggestion_issue,
                       sync_season_hint_issue

``end_hold`` and ``fire_override_ended`` appear in two views each, so the union
is 22 - 2 = 20 distinct capabilities.

LATE BINDING (binding, plan section 4.4). Six targets must resolve through the
coordinator INSTANCE on every call, because tests replace them there after the
orchestrator was built. Five are coordinator instance methods
(``_write_unavailable_safe_state``, ``_maybe_record_trace``,
``_forecast_outdoor``, ``commit_execution``, ``_maybe_save``); the sixth,
``_health.emit``, is a method of the ``HealthReporter`` and is resolved through
``coordinator._health`` — a different substitution form, because
``HealthReporter`` has ``__slots__`` and its ``emit`` cannot be replaced on the
reporter instance at all. Nothing here may snapshot a bound method in
``__init__``; a frozen dataclass of callables would be wrong at all six.
``tests/integration/test_o3_late_binding.py`` proves per target that a
replacement TAKES EFFECT.

TWO SELF-REFERENTIAL CHAINS. Two of those targets call back INTO the
orchestrator, and the chains must stay exactly as they are — the coordinator
method in the middle is the documented patch point:

    TickOrchestrator._run_unavailable_tick
      -> SequencerPorts.write_unavailable_safe_state()
      -> PoiseCoordinator._write_unavailable_safe_state()   # THE patch point
      -> TickOrchestrator._write_unavailable_safe_state()   # thin facade (O.5)
      -> ActuatePhase.write_unavailable_safe_state()        # the body

    TickOrchestrator.finalize_tick
      -> SequencerPorts.record_trace(...)
      -> PoiseCoordinator._maybe_record_trace(...)          # THE patch point
      -> TickOrchestrator._maybe_record_trace(...)

NO GLOBAL CLAIM. ``ha/health_reporter.py`` deliberately keeps its own ``self._c``
(it also WRITES through it); O.3 does not touch it. The "only place that knows
the coordinator" statement is scoped to the tick-orchestration and phase chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .tick_snapshot import TickConfigSnapshot, ZoneBindings

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from collections.abc import Sequence
    from typing import Any

    from ..control.feedback import CloSuggestion
    from ..control.mpc import MpcParams
    from ..control.suggestion import OverrideSuggestion
    from ..coordinator import PoiseCoordinator
    from ..runtime.tick_result import (
        CommitResult,
        ExecutionReport,
        HealthUpdate,
        PostExecutionAction,
    )


class SequencerPorts(Protocol):
    """What the tick SEQUENCER needs: the two checkpoints, the forecast await,
    the unavailable-path entry, the pre-events fire, the convergence notify and
    the one piece of adapter state it owns.

    ``commit_execution`` is deliberately absent: the sequencer's two former
    commit sites moved into ``_stage_fan_write`` (O.1) and
    ``_write_unavailable_safe_state`` (an actuation body), so after the split
    nothing here commits.
    """

    @property
    def unavailable_logged(self) -> bool:
        """The "sensor loss already logged" latch (read AND written here).

        Modelled as a real read/write property rather than a get/set method
        pair: the orchestrator both tests and assigns it, and disguising an
        assignment as a method call would hide that this is state, not a
        command.
        """

    @unavailable_logged.setter
    def unavailable_logged(self, value: bool) -> None: ...

    def emit_health(self, updates: tuple[HealthUpdate, ...]) -> None:
        """Health checkpoint (late-binding target, via ``coordinator._health``)."""

    def fire_override_ended(self, reason: str) -> None:
        """Fire the ``poise_override_ended`` bus event for one ended hold."""

    def notify_convergence(self, active: bool) -> None:
        """Raise/clear the write-convergence repair issue."""

    async def forecast_outdoor(self, horizon_min: float, fallback: float) -> float:
        """The forecast await at the prepare seam (late-binding target)."""

    async def record_trace(
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
        """Trace checkpoint (late-binding target; self-referential chain)."""

    async def save_if_due(self) -> None:
        """Persistence checkpoint (late-binding target)."""

    async def write_unavailable_safe_state(self, bindings: ZoneBindings) -> None:
        """Unavailable safe state (late-binding target; self-referential chain)."""


class PreparePorts(Protocol):
    """What the await-free PREPARE phase invokes: hold/preset bookkeeping, the
    two failure notifies and the per-tick MPC parameter write.
    """

    def end_hold(self, reason: str) -> None:
        """Tear down the active user hold with a named reason."""

    def expire_timed_states(self, home: bool | None) -> None:
        """Expire the timed Boost/manual hold once the house gate is known."""

    def notify_cooling_failure(self, failed: bool) -> None:
        """Raise/clear the cooling-failure repair issue."""

    def notify_failure(self, failed: bool) -> None:
        """Raise/clear the heating-failure repair issue."""

    def set_mpc_params(self, params: MpcParams) -> None:
        """Store this tick's re-derived MPC tuning."""


class ActuatePorts(Protocol):
    """What the ACTUATION phase invokes: the commit primitive plus the four
    override/hold commands its segments drive.
    """

    def commit_execution(
        self,
        report: ExecutionReport,
        post_actions: Sequence[PostExecutionAction] = (),
        *,
        now: float | None = None,
    ) -> CommitResult:
        """Fold one execution report into the domain state (late-binding target)."""

    def end_hold(self, reason: str) -> None:
        """Tear down the active user hold with a named reason."""

    def fire_override_ended(self, reason: str) -> None:
        """Fire the ``poise_override_ended`` bus event for one ended hold."""

    def set_mode_override(self, mode: str | None) -> None:
        """Adopt (or clear) an externally observed HVAC mode as user intent."""

    def set_override(self, value: float | None, *, reason: str | None = None) -> None:
        """Adopt (or clear) an externally observed setpoint as user intent."""


class ShadowPorts(Protocol):
    """What the SHADOW phase needs — one read, nothing else.

    This is the view that makes the split worth its price: ``ShadowPhase``
    cannot even type a ``commit_execution`` call.
    """

    @property
    def mpc_params(self) -> MpcParams:
        """This tick's MPC tuning, as written by ``PreparePorts``."""


class ReportPorts(Protocol):
    """What the REPORT phase invokes: the three suggestion-issue facades."""

    def sync_clo_suggestion_issue(self, suggestion: CloSuggestion | None) -> None:
        """Raise/clear the clothing-offset suggestion issue."""

    def sync_season_hint_issue(self, hint: str | None) -> None:
        """Raise/clear the seasonal mode-hint issue."""

    def sync_suggestion_issue(
        self, suggestion: OverrideSuggestion | None, suppressed: bool
    ) -> None:
        """Raise/clear the override-pattern suggestion issue."""


class TickSnapshotSource(Protocol):
    """The READ role: the per-tick snapshots from O.2.

    Kept separate from the ports on purpose — reading the world and acting on
    it are different responsibilities. The build POSITIONS stay behaviour and
    stay in the orchestrator: ``bindings()`` runs as the first statement of the
    tick (before the availability gate), ``config()`` right after the gate
    passes.
    """

    def bindings(self) -> ZoneBindings:
        """The zone's identity and entity wiring for this tick."""

    def config(self) -> TickConfigSnapshot:
        """The tick-stable policy/config view for this tick."""


class CoordinatorTickPorts:
    """The ``PoiseCoordinator``-backed implementation of all five views.

    This class and ``CoordinatorSnapshotSource`` are the ONLY places in the
    tick-orchestration and phase chain that hold a coordinator reference. Every
    method below forwards through ``self._c`` at CALL time — never through a
    method object captured in ``__init__`` — which is what makes the six
    late-binding targets replaceable on the instance (see the module docstring).
    Plain forwarding shares that property for free, so the rule needs no
    exception anywhere.
    """

    __slots__ = ("_c",)

    def __init__(self, coordinator: PoiseCoordinator) -> None:
        self._c = coordinator

    # --- SequencerPorts ----------------------------------------------------

    @property
    def unavailable_logged(self) -> bool:
        return self._c._unavailable_logged

    @unavailable_logged.setter
    def unavailable_logged(self, value: bool) -> None:
        self._c._unavailable_logged = value

    def emit_health(self, updates: tuple[HealthUpdate, ...]) -> None:
        # LATE BINDING, different form: ``emit`` belongs to the HealthReporter,
        # so BOTH ``_health`` and ``emit`` are resolved here, in this order. A
        # test replaces ``coordinator._health`` (the reporter itself) - it
        # cannot replace ``emit`` on the reporter, which has ``__slots__``.
        self._c._health.emit(updates)

    def fire_override_ended(self, reason: str) -> None:
        self._c._fire_override_ended(reason)

    def notify_convergence(self, active: bool) -> None:
        self._c._notify_convergence(active)

    async def forecast_outdoor(self, horizon_min: float, fallback: float) -> float:
        # LATE BINDING (test_forecast_backoff / test_glue_coverage4 /
        # test_phase5a_wiring drive the coordinator method directly).
        return await self._c._forecast_outdoor(horizon_min, fallback)

    async def record_trace(
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
        # LATE BINDING + self-referential: the coordinator method dispatches
        # back into ``TickOrchestrator._maybe_record_trace`` (test_phase8_
        # presenter wraps the coordinator method with an async spy).
        await self._c._maybe_record_trace(
            data, room=room, t_out=t_out, rh=rh, t_rm=t_rm, now=now, config=config
        )

    async def save_if_due(self) -> None:
        # LATE BINDING (the F-SAVEPOINT checkpoint, test_phase0_persistence_
        # checkpoint).
        await self._c._maybe_save()

    async def write_unavailable_safe_state(self, bindings: ZoneBindings) -> None:
        # LATE BINDING + self-referential: the coordinator method dispatches
        # back into ``TickOrchestrator._write_unavailable_safe_state``.
        await self._c._write_unavailable_safe_state(bindings)

    # --- PreparePorts ------------------------------------------------------

    def end_hold(self, reason: str) -> None:
        self._c._end_hold(reason)

    def expire_timed_states(self, home: bool | None) -> None:
        self._c._expire_timed_states(home)

    def notify_cooling_failure(self, failed: bool) -> None:
        self._c._notify_cooling_failure(failed)

    def notify_failure(self, failed: bool) -> None:
        self._c._notify_failure(failed)

    def set_mpc_params(self, params: MpcParams) -> None:
        self._c._set_mpc_params(params)

    # --- ActuatePorts ------------------------------------------------------

    def commit_execution(
        self,
        report: ExecutionReport,
        post_actions: Sequence[PostExecutionAction] = (),
        *,
        now: float | None = None,
    ) -> CommitResult:
        # LATE BINDING (test_phase5b_sequences drives the coordinator method
        # directly).
        return self._c.commit_execution(report, post_actions, now=now)

    def set_mode_override(self, mode: str | None) -> None:
        self._c._set_mode_override(mode)

    def set_override(self, value: float | None, *, reason: str | None = None) -> None:
        self._c.set_override(value, reason=reason)

    # --- ShadowPorts -------------------------------------------------------

    @property
    def mpc_params(self) -> MpcParams:
        return self._c._mpc_params

    # --- ReportPorts -------------------------------------------------------

    def sync_clo_suggestion_issue(self, suggestion: CloSuggestion | None) -> None:
        self._c._sync_clo_suggestion_issue(suggestion)

    def sync_season_hint_issue(self, hint: str | None) -> None:
        self._c._sync_season_hint_issue(hint)

    def sync_suggestion_issue(
        self, suggestion: OverrideSuggestion | None, suppressed: bool
    ) -> None:
        self._c._sync_suggestion_issue(suggestion, suppressed)


class CoordinatorSnapshotSource:
    """The ``PoiseCoordinator``-backed ``TickSnapshotSource``.

    Both builders read the LIVE coordinator on every call, exactly as the
    inline ``ZoneBindings.from_coordinator(self._c)`` /
    ``TickConfigSnapshot.from_coordinator(self._c)`` calls did: a snapshot
    taken in a constructor would go stale (``async_bootstrap``
    resets ``_trv_ext_temp`` on the reporter's verdict).
    """

    __slots__ = ("_c",)

    def __init__(self, coordinator: PoiseCoordinator) -> None:
        self._c = coordinator

    def bindings(self) -> ZoneBindings:
        return ZoneBindings.from_coordinator(self._c)

    def config(self) -> TickConfigSnapshot:
        return TickConfigSnapshot.from_coordinator(self._c)
