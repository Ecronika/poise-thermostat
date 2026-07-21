"""Hold-/Boost-lifecycle commands over ``UserControlState``.

The hass-free implementations of the coordinator's out-of-tick command
methods: set/clear a manual hold, adopt a device mode as a mode-hold,
arm/expire the timed Boost, end a hold, expire timed states on a tick, plus
the §5 override statistic and the set-time switchpoint lookup.  Every function
mutates the passed state group directly and returns a ``CommandResult``: the
HA adapter fires ``CommandResult.events`` immediately at the call position
(the domain decides and mutates hold state; only the adapter fires bus events)
and translates ``dirty`` into its store-dirty flag.

Clock injection: this module never imports Home Assistant.  Wall-clock reads
(``dt_util.utcnow``/``dt_util.now``) arrive as injected callables
(``now_utc_fn``/``local_minute_fn``/``minutes_to_switchpoint_fn``) evaluated
INSIDE these functions at their call positions and under their conditions — a
clear (``value=None``) path never reads the clock, a gated-out statistic never
reads it either, so call counts and error paths stay well-defined.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..comfort.presence import PresenceLevel
from ..const import OVERRIDE_POLICY_SCHEDULE
from ..runtime.tick_result import CommandResult, OverrideEnded
from .override import (
    OverrideMode,
    hold_expired,
    mode_comfort_base,
    resolve_boost_expiry,
    resolve_hold_expiry,
)
from .tick_resolve import sanitize_override

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..comfort.schedule import ComfortSchedule
    from ..runtime.state import PresenceRuntime, UserControlState
    from .override import OverrideConfig


def set_enabled(user: UserControlState, value: bool) -> CommandResult:
    """Enable/disable the zone (store-owned user intent)."""
    user.enabled = value
    return CommandResult(dirty=True)


def set_climate_mode(user: UserControlState, mode: str) -> CommandResult:
    """Record the user's climate-mode choice (store-owned)."""
    user.climate_mode = mode
    return CommandResult(dirty=True)


def set_window_bypass(user: UserControlState, on: bool) -> CommandResult:
    """Toggle the window-reaction bypass (ADR-0041 stage 2)."""
    user.window_bypass = on
    return CommandResult(dirty=True)


def minutes_to_switchpoint(
    schedule: ComfortSchedule, local_minute: int
) -> float | None:
    """Minutes to the next schedule switchpoint for a hold's expiry.

    The nearer of the upcoming setback/comfort edges; None when there is no
    upcoming switchpoint (always-comfort) -> the timer fallback applies.

    This is the plain set-time switchpoint for the *announced* expiry.
    ADR-0059 §3 (end the hold already at the optimal-start preheat-start, so
    the room is warm at comfort time) is resolved in the tick -- where the
    model/forecast preheat decision lives -- by ``hold_ends_at_preheat``.  The
    caller supplies the local minute-of-day.
    """
    sched = schedule.state_at(local_minute)
    cands = [
        float(m)
        for m in (sched.minutes_to_setback, sched.minutes_to_comfort)
        if m is not None and m > 0
    ]
    return min(cands) if cands else None


def _announce_hold_expiry(
    user: UserControlState,
    *,
    set_at: float,
    mins: float | None,
    policy: str,
    timer_h: float,
    max_h: float,
) -> None:
    """Announce a hold's set-time expiry (ADR-0059 §4) — the shared half of
    ``set_override``/``set_mode_override``.

    Sets ``override_expires_at`` via ``resolve_hold_expiry`` and the §1
    reason-accuracy flag: was the announced expiry the switchpoint itself
    (not the timer fallback / max_h cap)? -> ``_expire_timed_states`` reason.
    """
    user.override_expires_at = resolve_hold_expiry(
        policy=policy,
        set_at=set_at,
        timer_h=timer_h,
        max_h=max_h,
        minutes_to_switchpoint=mins,
    )
    user.override_expiry_is_switchpoint = (
        policy == OVERRIDE_POLICY_SCHEDULE
        and mins is not None
        and mins > 0
        and set_at + mins * 60.0 <= set_at + max_h * 3600.0
    )


def set_override(
    user: UserControlState,
    value: float | None,
    *,
    reason: str | None,
    policy: str,
    timer_h: float,
    max_h: float,
    frost_floor: float,
    device_max: float,
    now_utc_fn: Callable[[], float],
    minutes_to_switchpoint_fn: Callable[[], float | None],
    record_stat_fn: Callable[[float], None],
) -> CommandResult:
    """Set or clear the manual setpoint hold (ADR-0059 §1/§4/§5).

    Validates at the trust boundary: rejects non-finite, clamps to the safe
    envelope so a bad manual setpoint can never reach the actuator.  Setting
    announces the hold's expiry at set-time so the Card can show its
    "valid until …" hint the instant the user intervenes, keeps the pre-clamp
    requested value, records the §5 statistic (via ``record_stat_fn`` —
    observe-only, its swallow boundary stays with the adapter) and stamps the
    hold's origin (a UI setpoint change defaults to ``"ui_setpoint"``; device
    adoption passes ``reason="device_adopt_setpoint"``).  Clearing drops the
    whole lifecycle and — only when an explicit ``None`` ends a hold that was
    actually active — returns the immediate ``OverrideEnded(reason or
    "user_resume")`` event, so a mode change or a resume on a hold-less zone
    raises no false event.
    """
    was_active = user.override is not None  # only a real hold ends
    clamped = sanitize_override(value, frost_floor, device_max)
    user.override = clamped
    events: tuple[OverrideEnded, ...] = ()
    if clamped is not None:
        set_at = now_utc_fn()
        user.override_set_wall = set_at
        # Keep the pre-clamp requested value: the Card shows what the user
        # asked for vs the norm-clamped hold that is applied.
        user.override_requested = float(value) if value is not None else None
        mins = minutes_to_switchpoint_fn()
        _announce_hold_expiry(
            user, set_at=set_at, mins=mins, policy=policy, timer_h=timer_h, max_h=max_h
        )
        record_stat_fn(clamped)  # §5 L1 (observe-only)
        # record the hold's origin.
        user.override_reason = reason or "ui_setpoint"
    else:
        # Clearing the hold: drop the whole lifecycle + announce the reason.
        user.override_set_wall = None
        user.override_expires_at = None
        user.override_requested = None
        user.override_expiry_is_switchpoint = False
        user.override_reason = None  # no hold -> no origin
        if value is None and was_active:  # explicit clear of an active hold
            events = (OverrideEnded(reason or "user_resume"),)
    return CommandResult(events=events, dirty=True)


def set_mode_override(
    user: UserControlState,
    mode: str | None,
    *,
    policy: str,
    timer_h: float,
    max_h: float,
    now_utc_fn: Callable[[], float],
    minutes_to_switchpoint_fn: Callable[[], float | None],
) -> CommandResult:
    """Adopt (or clear) a device-side hvac_mode as a manual mode-hold.

    Shares the setpoint hold's lifecycle: if no hold is running yet it starts
    one (set-time expiry via ``resolve_hold_expiry`` + the zone policy). A
    setpoint hold already active this frame keeps its announced expiry -- the
    common case where an IR remote sends mode + temperature in one frame,
    adopted together.  Cleared by ``end_hold`` alongside the setpoint hold;
    never a safety layer.
    """
    user.mode_override = mode
    if mode is not None:
        user.override_reason = "device_adopt_mode"  # origin of this hold
    if mode is not None and user.override_set_wall is None:
        set_at = now_utc_fn()
        user.override_set_wall = set_at
        mins = minutes_to_switchpoint_fn()
        _announce_hold_expiry(
            user, set_at=set_at, mins=mins, policy=policy, timer_h=timer_h, max_h=max_h
        )
    return CommandResult(dirty=True)


def set_preset(
    user: UserControlState,
    mode: OverrideMode,
    *,
    boost_duration_min: float,
    now_utc_fn: Callable[[], float],
) -> CommandResult:
    """Select a comfort preset; Boost is the one timed preset (ADR-0059 §2).

    Freezes the preset active at activation so expiry restores it, and
    announces the expiry up front; re-pressing Boost re-arms from now without
    stacking BOOST onto itself as the frozen preset.  Any stateless preset
    (Eco/Comfort/Away/None) drops the Boost timer.
    """
    if mode is OverrideMode.BOOST:
        if user.preset is not OverrideMode.BOOST:
            user.boost_prev_preset = user.preset
        user.boost_expires_at = resolve_boost_expiry(
            set_at=now_utc_fn(),
            boost_duration_min=boost_duration_min,
        )
    else:
        user.boost_expires_at = None
        user.boost_prev_preset = None
    user.preset = mode
    return CommandResult(dirty=True)


def end_hold(user: UserControlState, reason: str) -> CommandResult:
    """Tear down an active manual hold and report why (ADR-0059 §1/§3).

    The ONE hold-teardown implementation: clears the hold value, the mode-hold,
    the whole announced-expiry lifecycle and the hold origin.  The resulting
    ``OverrideEnded(reason)`` travels in ``CommandResult.events`` — the adapter
    fires it immediately (in-stage for the expiry/preheat/re-align sites, via
    ``CommitResult.events`` for the frost-rescue ``EndHold`` post-action).
    """
    user.override = None
    # mode-hold shares the setpoint hold's end.
    user.mode_override = None
    user.override_set_wall = None
    user.override_expires_at = None
    user.override_requested = None
    user.override_reason = None  # origin cleared with the hold
    user.override_expiry_is_switchpoint = False
    return CommandResult(events=(OverrideEnded(reason),), dirty=True)


def expire_timed_states(
    user: UserControlState,
    presence: PresenceRuntime,
    home: bool | None,
    *,
    end_on_presence: bool,
    boost_duration_min: float,
    now_utc_fn: Callable[[], float],
) -> CommandResult:
    """Expire the timed Boost + manual hold on a tick (ADR-0059 §1/§2).

    A house-gate presence flip (either direction) since the last tick, or the
    hold's announced wall-clock expiry, ends a manual hold; a timed Boost
    restores the preset frozen at activation.  Wall-clock throughout, so a
    state restored after a restart expires on real elapsed time.  Runs under
    any active layer (window/frozen): the layer keeps regulating.

    The reason derivation mirrors the announcement flag: ``presence_change``
    when the presence trigger fired; ``schedule_point`` only when the
    announced expiry was the switchpoint itself (§1 accuracy); else
    ``expired_timer`` (timer policy, or schedule with no switchpoint /
    max_h-capped).
    """
    now = now_utc_fn()
    presence_changed = (
        presence.prev_home is not None
        and home is not None
        and home != presence.prev_home
    )
    presence.prev_home = home
    dirty = False
    events: tuple[OverrideEnded, ...] = ()
    # timed Boost (§2): restore the frozen preset; then Boost is stateless.
    if user.boost_expires_at is not None and now >= user.boost_expires_at:
        restored = set_preset(
            user,
            user.boost_prev_preset or OverrideMode.NONE,
            boost_duration_min=boost_duration_min,
            now_utc_fn=now_utc_fn,
        )
        dirty = dirty or restored.dirty
    # manual hold (§1): value-independent expiry announced at set-time; a
    # mode-hold (possibly without a setpoint hold) expires on the same
    # triggers.
    if (user.override is not None or user.mode_override is not None) and hold_expired(
        expires_at=user.override_expires_at,
        now=now,
        presence_changed=presence_changed,
        end_on_presence=end_on_presence,
    ):
        if presence_changed and end_on_presence:
            reason = "presence_change"
        elif user.override_expiry_is_switchpoint:
            # schedule policy AND the announced expiry was the switchpoint
            # (not the timer fallback / max_h cap) -> a true schedule end.
            reason = "schedule_point"
        else:
            # timer policy, or schedule with no switchpoint / max_h-capped.
            reason = "expired_timer"
        ended = end_hold(user, reason)
        dirty = dirty or ended.dirty
        events = ended.events
    return CommandResult(events=events, dirty=dirty)


def record_override_stat(
    user: UserControlState,
    clamped: float,
    *,
    presence_level: str,
    window_open: bool,
    comfort_base: float,
    override_cfg: OverrideConfig,
    schedule: ComfortSchedule,
    local_minute_fn: Callable[[], int],
    now_utc_fn: Callable[[], float],
) -> None:
    """Append one L1 override observation (ADR-0059 §5; diagnostic only).

    A capped rolling log of user setpoint nudges: direction/delta vs the
    effective preset base, the schedule phase and the presence level at set
    time.  AWAY / window-open nudges are skipped (not representative).  No
    behaviour and no suggestions -- L2 (suggestions) is a v2 feature.

    Deliberately raises through: the broad swallow boundary (with its exact
    debug-log channel/text) stays in the coordinator adapter — the log channel
    is observable diagnosis.  The clock callables are only evaluated past the
    gate.
    """
    if (
        user.preset is OverrideMode.AWAY
        or presence_level == PresenceLevel.AWAY.value
        or window_open
    ):
        return
    base = mode_comfort_base(user.preset, comfort_base, override_cfg)
    delta = clamped - base
    phase = "comfort" if schedule.state_at(local_minute_fn()).is_comfort else "setback"
    user.override_stats.append(
        {
            "ts": now_utc_fn(),
            "direction": 1 if delta >= 0 else -1,
            "delta": round(delta, 2),
            "phase": phase,
            "presence_level": presence_level,
        }
    )
    del user.override_stats[:-50]  # keep the last 50
