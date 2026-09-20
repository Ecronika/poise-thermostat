"""ADR-0074 state-space soak — the invariants, on a fixed seed.

Hand-written cases prove the transitions we thought of. This module proves the
ones we did not: it walks the whole reachable state space with a deterministic
pseudo-random driver and checks twelve properties that must hold for EVERY
sequence of resolver answers, window signals and tick lengths.

Three real defects came from here and from nowhere else — a prompt budget that
followed the tick's reason instead of the episode, a spent budget that turned a
standing close into ``idle``, and a phase change that swallowed ``discourage``
at the exact moment it became actionable. The seed is fixed so the run is a
test, not an anecdote.

A soak is only as good as its properties: invariant 10 was added after an
external review found a latched protection stop losing its REASON to an
ordinary close. The old property checked the level alone and therefore could
not fire once the reason was already gone.
"""

from __future__ import annotations

import random

from custom_components.poise.comfort.vent_episode import (
    PHASE_COOLDOWN,
    PHASE_IDLE,
    PHASE_REQUESTED,
    PHASE_STOP_REQUESTED,
    PHASE_VENTILATING,
    PROTECTION_CLOSE,
    REASON_AIRING_DONE,
    WINDOW_CLOSED,
    WINDOW_LIKELY_CLOSED,
    WINDOW_LIKELY_OPEN,
    WINDOW_OPEN,
    WINDOW_SOURCE_BYPASS,
    WINDOW_SOURCE_CONTACT,
    WINDOW_SOURCE_NONE,
    WINDOW_SOURCE_SLOPE,
    WINDOW_UNKNOWN,
    EpisodeConfig,
    EpisodeState,
    episode_protected,
    episode_step,
)

_CFG = EpisodeConfig()
_PHASES = frozenset(
    {
        PHASE_IDLE,
        PHASE_REQUESTED,
        PHASE_VENTILATING,
        PHASE_STOP_REQUESTED,
        PHASE_COOLDOWN,
    }
)
_WINDOWS = (
    WINDOW_OPEN,
    WINDOW_CLOSED,
    WINDOW_LIKELY_OPEN,
    WINDOW_LIKELY_CLOSED,
    WINDOW_UNKNOWN,
)
_OPENISH = frozenset({WINDOW_OPEN, WINDOW_LIKELY_OPEN})
_CLOSEDISH = frozenset({WINDOW_CLOSED, WINDOW_LIKELY_CLOSED})
# Every answer ``ventilation_advise`` can produce, as a triple.
_ANSWERS = (
    ("idle", "no_gain", "ok"),
    ("idle", "no_data", "ok"),
    ("open", "moisture_out", "ok"),
    ("open", "moisture_protect", "warn"),
    ("open", "mold_risk", "alert"),
    ("open", "co2", "ok"),
    ("open", "heat_out", "ok"),
    ("close", "mold_guard", "warn"),
    ("close", "thermal_floor", "warn"),
    ("close", "too_dry", "warn"),
    ("close", "target_reached", "ok"),
    ("close", "cooled_off", "ok"),
    ("discourage", "too_dry", "warn"),
)
_SOURCES = (
    WINDOW_SOURCE_CONTACT,
    WINDOW_SOURCE_SLOPE,
    WINDOW_SOURCE_BYPASS,
    WINDOW_SOURCE_NONE,
)
_AGES = (None, 1.0, 45.0)
_TICKS = (0.5, 1.0, 5.0, 30.0)
_RUNS = 30_000
_SEED = 20260917


def _episode_budget(state: EpisodeState) -> int:
    return (
        _CFG.max_prompts_per_episode_protection
        if episode_protected(state)
        else _CFG.max_prompts_per_episode
    )


def _cap(state: EpisodeState) -> int:
    return (
        _CFG.max_prompts_per_phase_protection
        if episode_protected(state)
        else _CFG.max_prompts_per_phase
    )


def test_state_space_soak_holds_every_invariant() -> None:
    rnd = random.Random(_SEED)
    broken: list[tuple[object, ...]] = []
    for _ in range(_RUNS):
        st = EpisodeState()
        prev: tuple[str, bool, bool] | None = None
        for _ in range(rnd.randint(1, 40)):
            action, reason, level = rnd.choice(_ANSWERS)
            window = rnd.choice(_WINDOWS)
            res = episode_step(
                st,
                action=action,
                reason=reason,
                level=level,
                window=window,
                window_source=rnd.choice(_SOURCES),
                window_age_min=rnd.choice(_AGES),
                dt_min=rnd.choice(_TICKS),
            )
            s = res.state
            # 1 structure
            if s.phase not in _PHASES:
                broken.append(("phase", s.phase))
            if res.window_seen not in (*_WINDOWS,):
                broken.append(("window_seen", res.window_seen))
            if res.action not in ("idle", "open", "close", "discourage"):
                broken.append(("action", res.action))
            # 2 the prompt budget belongs to the episode
            if s.prompts > _cap(s):
                broken.append(("budget", s.prompts, s.reason, s.owner))
            # 3 discourage is never swallowed
            if action == "discourage" and res.action == "idle":
                broken.append(("discourage", prev, window))
            # 4 a CURRENT protection close is never published as "open"
            if (
                action == "close"
                and reason in PROTECTION_CLOSE
                and res.action == "open"
            ):
                broken.append(("protection-as-open", prev, window))
            if prev is not None:
                # 5 a known-open window never lets a standing close expire.
                # The test reads ``window_seen``, not the raw signal: a stale
                # or unproven reading is not knowledge, and the machine is
                # judged on what it was entitled to believe.
                if (
                    prev[0] == PHASE_STOP_REQUESTED
                    and res.window_seen in _OPENISH
                    and res.action not in ("close", "open")
                ):
                    broken.append(("close-expired-while-open", res.action, window))
                # 6 an emergency is never overruled by a new opening reason
                if (
                    prev[0] == PHASE_STOP_REQUESTED
                    and action == "open"
                    and prev[1]
                    and s.phase == PHASE_VENTILATING
                ):
                    broken.append(("emergency-overruled",))
                # 7 silencing the doorbell never changes the truth
                if (
                    prev[0] == PHASE_STOP_REQUESTED
                    and prev[2]
                    and action == "close"
                    and res.window_seen not in _CLOSEDISH
                    and res.action != "close"
                ):
                    broken.append(("mute-changed-truth", res.action, window))
            # 8 an airing is never claimed without an observed opening
            if s.phase == PHASE_VENTILATING and not s.opened_seen:
                broken.append(("ventilating-without-evidence", res.window_seen))
            # 9 the episode ceiling holds across phase re-entry
            if s.episode_prompts > _episode_budget(s):
                broken.append(("episode-budget", s.episode_prompts, s.reason))
            # 10 a latched protection stop never loses its reason. The
            # earlier version only checked the LEVEL, which cannot fire once
            # the reason itself has been overwritten.
            if (
                s.phase == PHASE_STOP_REQUESTED
                and s.emergency
                and res.reason not in PROTECTION_CLOSE
            ):
                broken.append(("latched-protection-lost", res.reason))
            # 11 a protection close is never published as harmless
            if (
                res.action == "close"
                and res.reason in PROTECTION_CLOSE
                and res.level == "ok"
            ):
                broken.append(("protection-close-at-ok", res.reason))
            # 12 the leftover note is never stale and never leaks out of the
            # quiet time. Both halves matter: a note in a live phase would be
            # a second, competing source of truth about what is wanted, and a
            # note the resolver no longer backs would advise airing for air
            # that is already fine.
            if s.pending_reason and (
                s.phase != PHASE_COOLDOWN
                or action != "open"
                or reason != s.pending_reason
            ):
                broken.append(("pending-note", s.phase, s.pending_reason, action))
            prev = (s.phase, s.emergency, s.prompts >= _cap(s))
            st = s
    assert not broken, broken[:5]


def test_every_reachable_state_leaves_when_the_world_goes_quiet() -> None:
    """No phase without a finite exit — checked from reachable states.

    The quiet world uses an UNKNOWN contact on purpose: a window that is KNOWN
    to be open must keep its close standing, so that case has an event-driven
    exit rather than a finite one.
    """
    rnd = random.Random(_SEED + 1)
    for _ in range(1500):
        st = EpisodeState()
        for _ in range(rnd.randint(1, 12)):
            action, reason, level = rnd.choice(_ANSWERS)
            st = episode_step(
                st,
                action=action,
                reason=reason,
                level=level,
                window=rnd.choice(_WINDOWS),
                dt_min=rnd.choice((1.0, 5.0)),
            ).state
        seed_phase = st.phase
        for _ in range(400):
            st = episode_step(
                st,
                action="idle",
                reason="no_gain",
                level="ok",
                window=WINDOW_UNKNOWN,
                dt_min=1.0,
            ).state
            if st.phase == PHASE_IDLE:
                break
        assert st.phase == PHASE_IDLE, f"kein Ausgang aus {seed_phase}"


def test_the_soak_actually_reaches_every_phase_and_the_episode_token() -> None:
    """A green soak over an unreached state space would prove nothing."""
    rnd = random.Random(_SEED + 2)
    phases: set[str] = set()
    reasons: set[str] = set()
    st = EpisodeState()
    for _ in range(40_000):
        action, reason, level = rnd.choice(_ANSWERS)
        res = episode_step(
            st,
            action=action,
            reason=reason,
            level=level,
            window=rnd.choice(_WINDOWS),
            dt_min=rnd.choice(_TICKS),
        )
        phases.add(res.state.phase)
        reasons.add(res.reason)
        st = res.state
    assert phases == _PHASES
    assert REASON_AIRING_DONE in reasons
