"""External-override state machine over ``ExternalOverrideRuntime``.

``ExternalOverrideTracker`` owns the observe/mutate primitives over the echo-
and adoption baselines (all baselines live in ONE ``ExternalOverrideRuntime``),
and the three adoption stages — hold routing, mode adoption and the
setpoint-adoption commit — are pure implementations over ``ZoneRuntime``: the
runtime delegates 1:1 and the coordinator's ``_stage_*`` methods stay as thin
signature-identical facades.

``observe_mode``/``observe_setpoint`` evaluate the adoption reason ONCE — the
Layer-1 glue gates in chain order, then the pure Layer-2 reason function — and
derive decision AND reason from that one call (``OverrideObservation``): the
adopt/no-adopt decision and the diagnosis reason can never disagree.  Pinned
by ``tests/test_phase7_tracker.py`` over an input matrix.

Command side effects stay with the adapter: the stages receive the
coordinator's command facades as injected callables (``set_override_fn``/
``set_mode_override_fn``/``end_hold_fn``).  Those run the pure
``control.override_runtime`` lifecycle (``CommandResult``) and fire the
resulting bus events immediately at the in-stage call position; their
``dt_util`` reads happen inside the facade, AFTER the mode-nudge await, so a
nudge-dispatch duration stays observable in ``override_expires_at``.

Patch surfaces: integration tests patch symbols on the COORDINATOR module, so
the pure reason functions arrive as per-call ``*_fn`` parameters which the
coordinator's delegation resolves from its module globals at call time —
``patch("…coordinator.mode_adopt_reason")`` / ``…setpoint_adopt_reason`` /
``…resolve_desired_mode`` keep hitting every dispatch.  LOG CHANNELS are
behaviour: the suppressed-adoption debounce log arrives via the injected
coordinator logger with identical text/level.

This module is hass-free (mypy --strict, py310-clean): the ``State`` flowing
through ``WriteTargetResult.act_state`` is imported under ``TYPE_CHECKING``
only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from ..const import SETPOINT_ADOPT_ECHO_WINDOW_S
from ..runtime.tick_result import (
    HoldRoutingResult,
    ModeAdoptionResult,
)
from .tick_resolve import snap_to_step

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    from ..runtime.state import ExternalOverrideRuntime
    from ..runtime.tick_result import (
        IngestResult,
        ModeResolutionResult,
        ObservationResult,
        SetpointObservation,
        WriteTargetResult,
    )
    from ..runtime.zone_runtime import ZoneRuntime


class AdoptReason(str, Enum):  # noqa: UP042 — explicit str+Enum, StrEnum-equivalent
    """Canonical adoption-reason vocabulary (both diagnosis channels).

    The union of every string the two channels can carry —
    ``coordinator.data["mode_adopt_reason"]`` and ``…["sp_adopt_reason"]``:
    the ``""`` disabled/off-held default, the Layer-1 glue gates and the pure
    Layer-2 detector codes of ``control.override`` (``mode_adopt_reason`` /
    ``setpoint_adopt_reason``, each in guard order).  Members serialize
    CHARACTER-EXACTLY as plain strings (``__str__``/``__format__`` pinned to
    ``str``; JSON dumps the str content), pinned by
    ``tests/test_phase7_tracker.py``.

    Deliberately a vocabulary REGISTRY, not the runtime value type: the stage
    bodies produce plain ``str``, and threading enum members through
    ``coordinator.data``/the store would ride on ``Enum.__format__`` semantics
    that shifted across Python 3.10→3.12 — the pure suite runs 3.10, the HA
    suite 3.13, so plain strings are the one provably identical representation
    on both.  The whitelist below and the sync tests keep this registry honest.
    """

    __str__ = str.__str__

    def __format__(self, format_spec: str) -> str:
        # Pin format()/f-strings to the raw string: mixed str-Enum
        # ``__format__`` semantics shifted across py3.10→3.12, and the two
        # suites run 3.10 and 3.13 (StrEnum-equivalent pinning).
        return str.__format__(self, format_spec)

    NONE_YET = ""  # disabled / off-held default
    # Layer-1 glue gates (mode chain order: opt_out · safety_window ·
    # safety_frozen · own_echo · hold_resumed; setpoint chain order: opt_out ·
    # schedule_active · own_echo · safety_window · safety_frozen).
    OPT_OUT = "opt_out"
    SCHEDULE_ACTIVE = "schedule_active"
    OWN_ECHO = "own_echo"
    SAFETY_WINDOW = "safety_window"
    SAFETY_FROZEN = "safety_frozen"
    HOLD_RESUMED = "hold_resumed"
    # Layer-2 pure mode codes (override.mode_adopt_reason, guard order).
    NO_SIGNAL = "no_signal"
    DEVICE_ALIGNED = "device_aligned"
    UNSUPPORTED = "unsupported"
    OWN_COMMAND_ECHO = "own_command_echo"
    NO_BASELINE = "no_baseline"
    ECHO_WINDOW = "echo_window"
    STABLE_PREV = "stable_prev"
    # Layer-2 pure setpoint codes (override.setpoint_adopt_reason, guard
    # order; no_baseline/echo_window shared with the mode channel above).
    COMMAND_ECHO = "command_echo"
    IMPLAUSIBLE_FROST = "implausible_frost"
    STABLE_OFFSET = "stable_offset"
    ADOPT = "adopt"


# The debounced-debug-log whitelist — the *suppression* codes worth surfacing
# to a user whose remote change "did nothing".  NOT listed, hence never logged:
# ``adopt`` (nothing suppressed), the ``""`` default, and the nothing-to-adopt
# codes ``no_signal``/``device_aligned``/``own_command_echo``/``command_echo``/
# ``implausible_frost``.  The sync test pins both the exact tuple and its
# complement.
SUPPRESSED_ADOPT_REASONS: tuple[str, ...] = (
    AdoptReason.ECHO_WINDOW,
    AdoptReason.OWN_ECHO,
    AdoptReason.OPT_OUT,
    AdoptReason.SAFETY_WINDOW,
    AdoptReason.SAFETY_FROZEN,
    AdoptReason.HOLD_RESUMED,
    AdoptReason.STABLE_PREV,
    AdoptReason.STABLE_OFFSET,
    AdoptReason.NO_BASELINE,
    AdoptReason.UNSUPPORTED,
    AdoptReason.SCHEDULE_ACTIVE,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class OverrideObservation:
    """One adoption observation: decision AND reason from ONE call.

    ``reason`` is the full diagnosis code (a Layer-1 glue gate or the pure
    Layer-2 detector code); the decision is derived from it — ``adopt_mode``
    (mode channel) or ``adopt_setpoint`` (setpoint channel) carries the raw
    device value exactly when ``reason == "adopt"``, else ``None``.
    """

    reason: str
    adopt_mode: str | None = None
    adopt_setpoint: float | None = None


class ExternalOverrideTracker:
    """Echo-/foreign-change state machine over ``ExternalOverrideRuntime``.

    A stateless VIEW: every baseline lives in the ``ExternalOverrideRuntime``
    group, so the tracker can be constructed per stage call.  It owns the
    observe primitives (own-write echo, the two adoption observations) and the
    baseline mutations the observation path performs (mode-guard freeze, echo
    re-baseline, prev-update, post-adoption stamps); the write-path baseline
    advance stays exclusively with ``ZoneRuntime.commit_execution``.
    """

    __slots__ = ("external",)

    def __init__(self, external: ExternalOverrideRuntime) -> None:
        self.external = external

    def is_own_write(self, context_id: str | None) -> bool:
        """Does this HA ``Context`` id identify Poise's own write echo?"""
        return context_id is not None and context_id in self.external.own_write_ctx_ids

    def observe_mode(
        self,
        *,
        device_mode: str | None,
        desired_mode: str,
        now: float,
        echo_window_s: float,
        supported_modes: tuple[str, ...],
        adopt_enabled: bool,
        window_open: bool,
        frozen: bool,
        own_change: bool,
        hold_resumed: bool,
        mode_adopt_reason_fn: Callable[..., str],
    ) -> OverrideObservation:
        """Classify why the device mode was or was not adopted — the Layer-1
        glue gates first (in chain order), then the pure Layer-2 detector
        reason — and derive the adoption decision from that ONE reason.
        Behind the opt-out and the Context check (our own nudge echo is never
        adopted); off while a safety layer is active (window/frost beat a
        mode-hold — it is comfort, not safety); only modes the device lists
        (``heat_cool`` excluded).
        """
        if not adopt_enabled:
            reason = "opt_out"
        elif window_open:
            reason = "safety_window"
        elif frozen:
            reason = "safety_frozen"
        elif own_change:
            reason = "own_echo"
        elif hold_resumed:
            reason = "hold_resumed"
        else:
            reason = mode_adopt_reason_fn(
                device_mode=device_mode,
                desired_mode=desired_mode,
                last_commanded_mode=self.external.last_commanded_hvac,
                last_cmd_ts=self.external.last_hvac_cmd_ts,
                now=now,
                echo_window_s=echo_window_s,
                supported_modes=supported_modes,
                prev_mode=self.external.prev_device_mode,
            )
        return OverrideObservation(
            reason=reason,
            adopt_mode=device_mode if reason == "adopt" else None,
        )

    def freeze_mode_reference(
        self, device_mode: str | None, *, now: float, echo_window_s: float
    ) -> None:
        """Freeze the mode move-guard reference while the echo window is open,
        so an in-window observation of the user's mode never poisons the guard
        (the mode analogue of the setpoint prev-freeze).  Runs AFTER the
        observation.
        """
        if (
            self.external.last_hvac_cmd_ts is None
            or (now - self.external.last_hvac_cmd_ts) >= echo_window_s
        ):
            self.external.prev_device_mode = device_mode

    def rebaseline_own_echo(self, actual_sp: float) -> None:
        """Accept the device's *actual* settled value (echo / clamp /
        re-quantise under our own Context) as the echo baseline so future
        reports of it are recognised as echoes.  Deliberately does NOT touch
        ``last_sp_write_ts``: the echo window and the ADR-0052 §4 regulation
        throttle both key off the real last-*write* time; refreshing it every
        echo tick would keep the window/throttle open as long as the device
        echoes our context and could defer a legitimate new-target write past
        its period.
        """
        self.external.last_written_sp = actual_sp

    def observe_setpoint(
        self,
        *,
        device_sp: float | None,
        now: float,
        echo_window_s: float,
        deadband: float,
        frost_floor: float,
        adopt_enabled: bool,
        sched_active: bool,
        own_change: bool,
        window_open: bool,
        frozen: bool,
        setpoint_adopt_reason_fn: Callable[..., str],
    ) -> OverrideObservation:
        """Classify why the reported setpoint was or was not adopted — the
        Layer-1 glue gates first (in chain order), then the pure Layer-2
        detector reason — and derive the adoption decision from that ONE
        reason.  Off while the device runs its own schedule (the schedule, not
        the user, moves the setpoint), behind the opt-out and the Context
        check, and gated on safety like the mode path — an open window or a
        frozen sensor must not let a device-side drop be grabbed as a "manual"
        hold (the frost-drop phantom-hold class).
        """
        if not adopt_enabled:
            reason = "opt_out"
        elif sched_active:
            reason = "schedule_active"
        elif own_change:
            reason = "own_echo"
        elif window_open:
            reason = "safety_window"
        elif frozen:
            reason = "safety_frozen"
        else:
            reason = setpoint_adopt_reason_fn(
                device_sp=device_sp,
                last_written_sp=self.external.last_written_sp,
                last_write_ts=self.external.last_sp_write_ts,
                now=now,
                echo_window_s=echo_window_s,
                deadband=deadband,
                # Only a value the device *moved* to is a user change; a
                # stable settle/clamp of our own write is not.
                prev_device_sp=self.external.prev_device_sp,
                # Inside the echo window, a value differing from BOTH our
                # command and the pre-write reading is a provable user change.
                pre_write_sp=self.external.pre_write_sp,
                frost_floor=frost_floor,
            )
        return OverrideObservation(
            reason=reason,
            adopt_setpoint=device_sp if reason == "adopt" else None,
        )

    def note_device_setpoint(self, actual_sp: float | None) -> None:
        """Remember this tick's device reading so next tick can tell a fresh
        move (user) from a value the device is merely holding (echo of our
        write, re-quantised/clamped).  Updated every tick regardless of the
        adoption branch, so a settled offset never re-triggers adoption.
        """
        self.external.prev_device_sp = actual_sp

    def adopt_setpoint_baselines(
        self, *, adopted_sp: float, step: float, now: float
    ) -> None:
        """Echo-baseline choreography after an adoption was applied.

        The device now reports the adopted value, so make it the echo
        baseline.  Without this an in-band adoption (the common case, where no
        write follows because target == device) would be re-detected every
        tick -> ``set_override`` recomputes the expiry from ``now()`` forever
        (the hold never ends, a schedule resume is undone within a tick) and a
        store-save fires per tick.  Out-of-band adoptions self-correct: the
        clamped write that follows re-stamps ``last_written_sp``.

        The only other legit echo value still in flight is our *previous*
        command, so make it the pre-write reference.  Otherwise a late echo of
        that command (fresh context, sluggish device) differs from both the
        adopted value and a stale pre-write -> the three-value rule would
        re-adopt it and replace the user's hold with a phantom hold of our own
        old setpoint.
        """
        self.external.pre_write_sp = self.external.last_written_sp
        self.external.last_written_sp = snap_to_step(adopted_sp, step)
        self.external.last_sp_write_ts = now


# ---------------------------------------------------------------------------
# The three adoption stages
# ---------------------------------------------------------------------------


def stage_hold_routing(
    rt: ZoneRuntime,
    wt: WriteTargetResult,
    *,
    end_hold_fn: Callable[[str], None],
) -> HoldRoutingResult:
    """Own-write echo + off-hold routing + user-resume escape.

    INVARIANT (pinned): the off-hold frost route keeps its one-tick delay --
    ``off_held`` reads the persisted hold at tick start; the adopting tick
    still runs the enabled block.

    ``end_hold_fn`` is the coordinator's ``_end_hold`` facade (pure
    ``override_runtime.end_hold`` teardown + immediate bus fire), so the
    off-hold escape's ``poise_override_ended`` fires at its in-stage position.
    """
    act_state = wt.act_state
    # INVARIANT (K2b, ADR-0046 §9): observe() folds LATE, after the guard —
    # folding early lets compressor_running's intent-fallback and the
    # first-tick mode_changed_wall stamp brake the guard against its own
    # intent / self-armed hold.  Pinned by
    # test_dry_actuation.py::test_dry_nudge_when_humid_and_idle.
    # Is the actuator's current state Poise's own write echo (our Context)?
    # Computed once, reused by the mode-adoption gate here and the setpoint
    # gate below (a change under our own context is never adopted, mode or
    # setpoint).
    tracker = ExternalOverrideTracker(rt.external)
    _own_change = tracker.is_own_write(
        act_state.context.id
        if act_state is not None and act_state.context is not None
        else None
    )
    # An ``off`` mode-hold routes the zone through the disabled/frost-rescue
    # branch below (frost + mould protection stay active), exactly like a
    # user-disabled zone.  Read from the persisted hold at tick start; the tick
    # that first adopts ``off`` still runs the enabled block (pins desired=off,
    # skips the setpoint write) and only the next tick takes the frost route.
    _off_held = rt.user.mode_override == "off"
    # An off-hold is escapable at the device -- if the user switches the AC
    # back on (a foreign-context mode change away from off), end the hold so the
    # zone resumes control instead of holding a stale off while the device runs.
    # ``_hold_resumed`` then suppresses this tick's adoption so we do not re-grab
    # the mode the user just switched to as a fresh hold (resume != re-adopt).
    _hold_resumed = False
    if (
        _off_held
        and not _own_change
        and (act_state.state if act_state else None)
        not in ("off", None, "unknown", "unavailable")
    ):
        end_hold_fn("user_resume")
        _off_held = False
        _hold_resumed = True
    # Why this tick did/did not adopt a device change, surfaced as diagnostics
    # (stays "" on the disabled / off-held path that skips below).
    _mode_adopt_reason = ""
    _sp_adopt_reason = ""
    return HoldRoutingResult(
        own_change=_own_change,
        off_held=_off_held,
        hold_resumed=_hold_resumed,
        mode_adopt_reason=_mode_adopt_reason,
        sp_adopt_reason=_sp_adopt_reason,
    )


def stage_mode_adoption(
    rt: ZoneRuntime,
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
    """External-mode adoption, guard-reference freeze, hold pinning.

    INVARIANT (pinned): an active mode-hold pins the desired mode unless
    window/frost took over this tick (safety beats hold).

    ``set_mode_override_fn``/``end_hold_fn`` are the coordinator's command
    facades: the pure ``override_runtime`` lifecycle runs inside them at this
    in-stage call position — their ``dt_util.utcnow``/switchpoint reads
    therefore stay INSIDE the stage (after the nudge await) and the mode
    re-align's ``poise_override_ended`` fires at its in-stage position.
    """
    now = ing.now
    frozen = ing.frozen
    window_open = obs.window_open
    can_heat = obs.can_heat
    can_cool = obs.can_cool
    act_state = wt.act_state
    _idle_park_mode = wt.idle_park_mode
    final_mode = res.final_mode
    act_modes = res.act_modes
    _own_change = routing.own_change
    _hold_resumed = routing.hold_resumed
    desired_hvac = resolve_desired_mode_fn(
        final_mode=final_mode,
        current_device_mode=act_state.state if act_state else None,
        can_cool=can_cool,
        can_heat=can_heat,
        idle_park_mode=_idle_park_mode,
    )
    # Adopt a device-side hvac_mode change (the IR remote) as a manual
    # mode-hold instead of nudging it straight back.  Behind the opt-out and
    # the Context check (our own nudge echo is never adopted); off while a
    # safety layer is active (window/frost beat a mode-hold -- it is comfort,
    # not safety); only modes the device lists (``heat_cool`` excluded).
    # Classify why the mode change was or was not adopted -- Layer-1 glue
    # gates first, then the pure Layer-2 detector reason -- so a suppressed
    # user mode change is explainable in diagnostics.  ONE call yields both
    # decision and reason, so they can never disagree.
    _cur_mode = act_state.state if act_state else None
    tracker = ExternalOverrideTracker(rt.external)
    observation = tracker.observe_mode(
        device_mode=_cur_mode,
        desired_mode=desired_hvac,
        now=now,
        echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S,
        supported_modes=tuple(act_modes),
        adopt_enabled=adopt_external_mode,
        window_open=window_open,
        frozen=frozen,
        own_change=_own_change,
        hold_resumed=_hold_resumed,
        mode_adopt_reason_fn=mode_adopt_reason_fn,
    )
    _mode_adopt = observation.adopt_mode
    _mode_adopt_reason = observation.reason
    # Freeze the mode move-guard reference while the echo window is open, so
    # an in-window observation of the user's mode never poisons the guard
    # (the mode analogue of the setpoint prev-freeze).
    tracker.freeze_mode_reference(
        _cur_mode, now=now, echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S
    )
    if _mode_adopt is not None:
        set_mode_override_fn(_mode_adopt)
    # A mode-hold is escapable AT THE DEVICE -- if the user selects the
    # plan mode again (a foreign-context change back to what Poise wants),
    # end the hold instead of pinning them off it (the mode observation
    # returns None for device==desired, so it is resolved here).
    elif (
        rt.user.mode_override is not None
        and not _own_change
        and _cur_mode == desired_hvac
        and _cur_mode != rt.user.mode_override
        and not window_open
        and not frozen
    ):
        end_hold_fn("user_resume")
    # An active mode-hold pins the desired mode (no nudge; the setpoint keeps
    # regulating within it) unless a safety layer has taken over this tick --
    # window-open / frost still beat the hold, and the hold resumes once the
    # layer clears.
    if rt.user.mode_override is not None and not window_open and not frozen:
        desired_hvac = rt.user.mode_override
    return ModeAdoptionResult(
        desired_hvac=desired_hvac, mode_adopt_reason=_mode_adopt_reason
    )


def stage_setpoint_adopt(
    rt: ZoneRuntime,
    ing: IngestResult,
    spo: SetpointObservation,
    *,
    mode_adopt_reason: str,
    actuator_entity: str,
    logger: logging.Logger,
    set_override_fn: Callable[..., None],
) -> str:
    """Adoption-diagnosis surfacing, debounced log, prev-update and the
    adoption itself.

    Returns the tick's ``sp_adopt_reason``.  The reason travels IN ``spo`` —
    computed together with the decision by the ONE ``observe_setpoint`` call
    in the observe stage; nothing between the stages mutates any input.

    ``set_override_fn`` is the coordinator's ``set_override`` facade (full
    pure hold lifecycle incl. the set-time expiry announcement, the §5
    statistic and the hold origin) invoked at this in-stage position, so its
    ``dt_util.utcnow``/switchpoint reads keep their timing (after the nudge
    await).
    """
    now = ing.now
    actual_sp = spo.actual_sp
    step = spo.step
    _adopted_sp = spo.adopted_sp
    _mode_adopt_reason = mode_adopt_reason
    _sp_adopt_reason = spo.sp_adopt_reason
    tracker = ExternalOverrideTracker(rt.external)
    # Log a suppressed device change once (debounced on the reason) so a
    # user whose remote change "did nothing" can see why in the debug log.
    _sup = next(
        (
            r
            for r in (_mode_adopt_reason, _sp_adopt_reason)
            if r in SUPPRESSED_ADOPT_REASONS
        ),
        "",
    )
    if _sup and _sup != rt.user.last_adopt_log:
        logger.debug(
            "Poise %s: device change not adopted (mode=%s setpoint=%s)",
            actuator_entity,
            _mode_adopt_reason or "-",
            _sp_adopt_reason or "-",
        )
    rt.user.last_adopt_log = _sup
    # Remember this tick's device reading so next tick can tell a fresh move
    # (user) from a value the device is merely holding (echo of our write,
    # re-quantised/clamped).  Updated every tick regardless of the branch
    # below, so a settled offset never re-triggers adoption.
    tracker.note_device_setpoint(actual_sp)
    if _adopted_sp is not None:
        set_override_fn(_adopted_sp, reason="device_adopt_setpoint")
        # Post-adoption echo-baseline choreography (see
        # ``adopt_setpoint_baselines`` for the full rationale).
        tracker.adopt_setpoint_baselines(adopted_sp=_adopted_sp, step=step, now=now)
        rt.dirty = True  # persist the adopted hold across restarts
    return _sp_adopt_reason
