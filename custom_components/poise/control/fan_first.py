"""ADR-0068 fan-first cooling stage — pure, echo-gated, multi-tick FSM.

The first cooling stage is the compressor-free ``hvac_mode="fan_only"``,
never just a fan-speed write: sequence ``normal → fan_only → fan_only +
stage → cool``.  The FSM is echo-gated (Rev. 3/4): the dwell starts only
after ``fan_only`` was OBSERVED at the device, and no stage is commanded
before that — a ``blocking=False`` dispatch proves acceptance, never the
mode.  Entry is fail closed: a running compressor is never demoted (first
stage means FIRST), unknown run state blocks, and without a clamp-conform
KNOWN stage there is no active fan-first at all (a device default stage can
be ``turbo``; a conservative CE computation bounds only the credit, never
the real air speed).

This module emits per-tick ACTIONS for the mode seam (wired via
``stage_mode_resolution``/the orchestrator FSM block, ADR-0069 U5/U6):
``fan_only`` (mode candidate), ``stage`` (fan-stage write), ``cool`` (yield
to the compressor), ``release`` (disengage, normal logic resumes), ``none``
(hold the current phase).  The seam stays the single mode authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..comfort.fan_cooling import known_stage_velocity

FAN_ECHO_TIMEOUT_S = 180.0  # unanswered echo -> yield, never escalate
FAN_DWELL_MIN_S = 600.0  # the stage gets at least this chance
FAN_FIRST_TIMEOUT_S = 1800.0  # total sequence budget before the compressor
FAST_RISE_K = 0.5  # room rising this much past entry -> direct cool
HEAT_LIMIT_C = 35.0  # Poise policy (conservative vs WHO 40 C): no fan-first
REENTRY_BLOCK_S = 900.0  # anti-flap after a yield/release

# Velocity clamp (conservative Poise clamp, ADR-0068 § Entscheidung 5 —
# NOT a full ASHRAE-55 equal-SET reimplementation): below 23 C operative
# 0.2 m/s (no elevated stage qualifies), 0.8 m/s only from 25.5 C.
_CLAMP_LOW_C = 23.0
_CLAMP_HIGH_C = 25.5
_CLAMP_LOW_MS = 0.2
_CLAMP_HIGH_MS = 0.8


def max_stage_velocity(operative_c: float) -> float:
    """The air-speed clamp for the current operative temperature."""
    if operative_c < _CLAMP_LOW_C:
        return _CLAMP_LOW_MS
    if operative_c >= _CLAMP_HIGH_C:
        return _CLAMP_HIGH_MS
    span = (_CLAMP_HIGH_MS - _CLAMP_LOW_MS) / (_CLAMP_HIGH_C - _CLAMP_LOW_C)
    return _CLAMP_LOW_MS + (operative_c - _CLAMP_LOW_C) * span


def select_fan_stage(
    advertised_modes: tuple[str, ...] | list[str], max_velocity: float
) -> str | None:
    """Highest KNOWN advertised stage whose velocity class meets the clamp.

    Fail closed (ADR-0068 § Entscheidung 4): unknown labels are never
    guessed, and without a qualifying known stage the answer is ``None`` —
    no active fan-first, never a device default.
    """
    best: tuple[float, str] | None = None
    for stage in advertised_modes:
        # "auto" is not a stage: it hands the speed to the device firmware,
        # which may spin up to turbo — a hard clamp can never be guaranteed.
        # The diagnostic table maps it (fair for estimating an OBSERVED
        # state); commanding it is excluded here.
        if stage.lower() == "auto":
            continue
        velocity = known_stage_velocity(stage)
        if velocity is None or not (_CLAMP_LOW_MS < velocity <= max_velocity):
            continue
        if best is None or velocity > best[0]:
            best = (velocity, stage)
    return best[1] if best is not None else None


@dataclass(frozen=True, slots=True)
class FanFirstState:
    """Persisted-per-tick FSM state (transient runtime, restart -> idle)."""

    phase: str = "idle"  # idle | await_fan_only | await_stage | dwell | yielded
    engaged_at: float | None = None  # sequence start (total budget, fast rise)
    phase_at: float | None = None  # current phase entry (echo timeouts, dwell)
    stage: str | None = None
    room_at_entry: float | None = None
    # The fan stage observed at ENGAGE — restored on exit (field decision:
    # previous value first, "auto" only as fallback; user intent is sacred).
    entry_fan_mode: str | None = None
    blocked_until: float | None = None  # re-entry anti-flap


@dataclass(frozen=True, slots=True)
class FanFirstDecision:
    """One tick's verdict: the successor state + the action for the seam."""

    state: FanFirstState
    command: str  # none | fan_only | stage | cool | release
    reason: str
    # Exit restore (field decision): the stage to write back on yield/release
    # — the pre-sequence value, "auto" only as fallback; None = no write.
    restore_stage: str | None = None


def _restore_target(
    state: FanFirstState,
    *,
    observed_fan_mode: str | None,
    advertised_modes: tuple[str, ...] | list[str],
) -> str | None:
    """The stage to write back on exit — never a guess, never a duel.

    Restores only when WE commanded a stage and the device still shows it
    (a foreign change is user intent and is excluded by the caller; an
    unconfirmed stage would make the restore a blind write).  Target: the
    ENGAGE-time value; unknown -> ``auto`` when advertised (post-yield the
    firmware should modulate the fan under the compressor — the clamp
    doctrine only governed the fan-first stage itself); else leave as-is.
    """
    if state.stage is None or observed_fan_mode != state.stage:
        return None
    target = state.entry_fan_mode
    if target is None:
        target = "auto" if any(m.lower() == "auto" for m in advertised_modes) else None
    if target is None or target == observed_fan_mode:
        return None
    return target


def _released(
    state: FanFirstState,
    now: float,
    reason: str,
    restore: str | None = None,
) -> FanFirstDecision:
    return FanFirstDecision(
        state=FanFirstState(blocked_until=now + REENTRY_BLOCK_S),
        command="release",
        reason=reason,
        restore_stage=restore,
    )


def _yielded(
    state: FanFirstState,
    now: float,
    reason: str,
    restore: str | None = None,
) -> FanFirstDecision:
    return FanFirstDecision(
        state=replace(state, phase="yielded", phase_at=now),
        command="cool",
        reason=reason,
        restore_stage=restore,
    )


def fan_first_decision(
    state: FanFirstState,
    *,
    now: float,
    cool_requested: bool,
    fan_first_allowed: bool,
    fan_only_capable: bool,
    observed_hvac_mode: str | None,
    observed_hvac_action: str | None,
    observed_fan_mode: str | None,
    advertised_modes: tuple[str, ...] | list[str],
    operative_c: float,
    room_c: float,
    presence_ok: bool,
    window_open: bool,
    in_comfort_window: bool,
    foreign_fan_change: bool,
) -> FanFirstDecision:
    """Advance the fan-first FSM by one tick (pure).

    ``fan_first_allowed`` is the seam's intent provenance (a MANUAL cool wish
    skips fan-first); ``presence_ok`` is ``presence_control_ready AND
    room_present`` (ADR-0069); ``foreign_fan_change`` is the tracker's
    verdict (a real user fan change exits, never a write duel).
    """
    engaged = state.phase in ("await_fan_only", "await_stage", "dwell")
    _restore: str | None = None
    if engaged:
        assert state.engaged_at is not None and state.phase_at is not None
        assert state.room_at_entry is not None
        if foreign_fan_change:
            # User intent stands: exit WITHOUT any restore write.
            return _released(state, now, "foreign_fan_change")
        _restore = _restore_target(
            state,
            observed_fan_mode=observed_fan_mode,
            advertised_modes=advertised_modes,
        )
        if not cool_requested:
            return _released(state, now, "demand_ended", _restore)
        if window_open:
            return _released(state, now, "window_open", _restore)
        if (
            not fan_first_allowed
            or not presence_ok
            or not in_comfort_window
            or room_c >= HEAT_LIMIT_C
        ):
            return _yielded(state, now, "guard_lost", _restore)
        if now - state.engaged_at > FAN_FIRST_TIMEOUT_S:
            return _yielded(state, now, "timeout", _restore)
        if room_c - state.room_at_entry > FAST_RISE_K:
            return _yielded(state, now, "fast_rise", _restore)

    if state.phase == "idle":
        entry_ok = (
            cool_requested
            and fan_first_allowed
            and fan_only_capable
            and presence_ok
            and not window_open
            and in_comfort_window
            and room_c < HEAT_LIMIT_C
            # First stage means FIRST: never demote a running compressor
            # (restart case), and an UNKNOWN run state blocks (fail closed).
            and observed_hvac_action is not None
            and observed_hvac_action != "cooling"
            and select_fan_stage(advertised_modes, max_stage_velocity(operative_c))
            is not None
            and (state.blocked_until is None or now >= state.blocked_until)
        )
        if not entry_ok:
            return FanFirstDecision(state=state, command="none", reason="idle")
        return FanFirstDecision(
            state=FanFirstState(
                phase="await_fan_only",
                engaged_at=now,
                phase_at=now,
                room_at_entry=room_c,
                entry_fan_mode=observed_fan_mode,
            ),
            command="fan_only",
            reason="engage",
        )

    if state.phase == "await_fan_only":
        if observed_hvac_mode == "fan_only":
            stage = select_fan_stage(advertised_modes, max_stage_velocity(operative_c))
            if stage is None:
                return _yielded(state, now, "stage_lost", _restore)
            if observed_fan_mode == stage:
                return FanFirstDecision(
                    state=replace(state, phase="dwell", stage=stage, phase_at=now),
                    command="none",
                    reason="dwell",
                )
            return FanFirstDecision(
                state=replace(state, phase="await_stage", stage=stage, phase_at=now),
                command="stage",
                reason="stage_request",
            )
        assert state.phase_at is not None
        if now - state.phase_at > FAN_ECHO_TIMEOUT_S:
            return _yielded(state, now, "echo_timeout", _restore)
        return FanFirstDecision(state=state, command="none", reason="await_echo")

    if state.phase == "await_stage":
        if observed_fan_mode == state.stage:
            return FanFirstDecision(
                state=replace(state, phase="dwell", phase_at=now),
                command="none",
                reason="dwell",
            )
        assert state.phase_at is not None
        if now - state.phase_at > FAN_ECHO_TIMEOUT_S:
            return _yielded(state, now, "stage_echo_timeout", _restore)
        return FanFirstDecision(state=state, command="none", reason="await_echo")

    if state.phase == "dwell":
        assert state.phase_at is not None and state.room_at_entry is not None
        if now - state.phase_at >= FAN_DWELL_MIN_S and room_c >= state.room_at_entry:
            return _yielded(state, now, "no_progress", _restore)
        return FanFirstDecision(state=state, command="none", reason="dwelling")

    # yielded: the compressor runs; disengage when the demand ends.
    if not cool_requested:
        return FanFirstDecision(
            state=FanFirstState(blocked_until=now + REENTRY_BLOCK_S),
            command="none",
            reason="reset",
        )
    return FanFirstDecision(state=state, command="none", reason="yielded")
