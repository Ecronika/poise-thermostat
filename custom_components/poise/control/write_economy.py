"""Write economy: when an identical re-assert cannot achieve anything.

M2 of the 2026-09-12 plan (``docs/Konzepte/2026-09-12_Plan_Schreiblast-M2-M4.md``),
the answer to ``docs/reviews/2026-09-12-TRV-Schreiblast-Zigbee.md``: a zone
whose target lands between two positions the device can represent re-wrote the
same setpoint every tick — 1440 writes a day on a battery TRV, with no
diagnostic anywhere.

THE ARGUMENT IS A FIXPOINT, NOT A PROVENANCE PROOF.  An identical command that
did not move the actuator last time cannot move it next time either.  That
needs two things only: which command is in force (``last_cmd_sp``, stamped by
the commit and never re-baselined) and whether anything has moved since that
command came into force.

THE COMMAND EPISODE is the missing primitive.  ``last_sp_write_ts`` marks the
last *physical* write and already carries the adoption echo window and the
ADR-0052 §4 throttle; with a 60 s re-assert it re-arms a 120 s echo window
forever, so ``setpoint_adopt_reason`` never leaves ``echo_window`` and never
reaches ``stable_offset``.  ``cmd_episode_ts`` therefore marks something else:
the moment ``last_cmd_sp`` actually CHANGED.  Identical re-asserts do not touch
it, so the settle of one logical command stays observable across them.

PROVENANCE IS STILL REQUIRED — for a different question.  The fixpoint decides
whether another write can achieve anything; it does NOT decide whether Poise
may stop asserting.  A device sitting at 20.4 after an unnoticed hand
adjustment while our command says 20.0 satisfies the fixpoint and must still be
re-asserted, or the zone is silently lost.  The two questions are orthogonal,
and folding them into one comparison is exactly the defect this module exists
for.

LIVENESS (plan V3).  "Did not work last time" only implies "cannot work" while
the channel is lossless and the device state persists.  Neither holds here: a
sleepy Zigbee end device can drop a write, and the kitchen TRV of the field
case reports ``power_outage_count: 852``.  Suppression therefore expires — the
clock is ``last_sp_write_ts``, which the commit re-stamps on every real write,
so one write per ``REASSERT_LIVENESS_S`` gets through with no extra state.

Pure: no Home Assistant, no runtime object.  Tested by ``tests/test_write_economy.py``.
"""

from __future__ import annotations

from typing import Final

# One tick plus margin: the device must have had a chance to react to the
# command before its stillness means anything.
EPISODE_SETTLE_MIN_S: Final = 90.0
# Liveness escape (V3): at most this long without a single write of the command
# in force. Generous on purpose — it is a safety net against a lost write and a
# device reboot, not a regulation interval.
REASSERT_LIVENESS_S: Final = 3600.0
# M4 (2026-09-12 plan): the floor between two IDENTICAL re-asserts of the same
# command episode. Not a regulation interval — ADR-0052 §4's
# ``regulation_period_s`` keeps its documented thermodynamic meaning and is not
# touched. Deliberately NOT a user option: a knob on a write gate needs a
# reason, and 10 min is far below every thermal time constant in play.
MIN_SETPOINT_REASSERT_INTERVAL_S: Final = 600.0
# Phase 2a (M5): the floor between two IDENTICAL re-asserts of the same hvac
# mode. Same number as the setpoint limit above and the same kind of statement
# — a rate bound, not a proof — but a DELIBERATELY different gate: there is no
# mode counterpart to :func:`reassert_idempotent`, and there must not be. A
# setpoint the device re-quantises is a representation artefact; a mode that
# does not take is a fault (a TRV back in ``auto`` running its own schedule, a
# device that rejected ``heat``), and a fault must keep being asserted. So the
# mode channel is throttled and never vetoed.
MIN_MODE_REASSERT_INTERVAL_S: Final = 600.0
# Two setpoint reads count as the same value below this (0.1 grid + float
# hygiene, the same rounding the write gate uses).
_SAME_VALUE_EPS: Final = 0.05

# M3 advisory (2026-09-12 plan): how many suppressed re-asserts of ONE command
# episode must have piled up before the resting distance is reported as a
# possible declared-step mismatch. Five ticks of a settled episode — enough that
# a slow settle or a single missed echo is not a diagnosis.
QUANT_MIN_SUPPRESSED: Final = 5

# --- provenance classes ------------------------------------------------------
# The three that may release M2 differ in evidence strength and are kept apart
# so diagnostics cannot later turn a weak statement into a strong one.
PROVEN_OWN_ECHO: Final = "proven_own_echo"  # our Context, current command
CURRENT_COMMAND_MATCH: Final = "current_command_match"  # value == last_cmd_sp
ACCEPTED_SETTLE: Final = "accepted_settle"  # stable, compatible, unproven
# The three that must not.
STALE_OWN_ECHO: Final = "stale_own_echo"  # our Context, SUPERSEDED command
FOREIGN: Final = "foreign"  # external change detected
UNKNOWN: Final = "unknown"  # no statement about provenance

RELEASING: Final = frozenset({PROVEN_OWN_ECHO, CURRENT_COMMAND_MATCH, ACCEPTED_SETTLE})

# Adoption reasons that mean "the detector RAN and found no foreign change".
# Everything else — ``opt_out``/``schedule_active`` (adoption switched off),
# ``safety_window``/``safety_frozen``/``implausible_frost`` (suppressed),
# ``no_baseline`` (nothing to compare) — says nothing about provenance, and a
# non-statement must never release the gate. This is what keeps the 0.5 K match
# tolerance below safe: an unnoticed hand adjustment 0.4 K away only reaches
# the value comparison while the detector is actually looking.
_DETECTOR_RAN: Final = frozenset({"command_echo", "echo_window", "stable_offset"})


def _same(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= _SAME_VALUE_EPS


def _stale_anchor(now: float, anchor: float) -> bool:
    """True when ``anchor`` cannot belong to the same clock as ``now``.

    The monotonic clock is injected (ADR-0006/0014), so "monotonic" holds
    within one clock and not across a swapped one — a replay harness, a test
    that installs its own clock mid-run, a restore path that stamped from a
    previous process. An anchor from ANOTHER era is not merely inaccurate, it
    is unusable: ``now - anchor`` comes out large and negative, every interval
    comparison reads as "just written", and the gate below would stay shut
    until the clock caught up.

    Both gates that use this therefore fail OPEN — they let the write through.
    That is the same direction ``safety/heating_failure`` chose for the same
    problem (its F22 clock guard re-anchors instead of stalling its window),
    and it is the direction this module's whole stance demands: silence must
    be justified, and an unusable anchor justifies nothing.
    """
    return now < anchor


def classify_settle(
    *,
    own_change: bool,
    stale_own_echo: bool,
    actual_sp: float | None,
    last_cmd_sp: float | None,
    prev_device_sp: float | None,
    match_tolerance: float,
    adopt_reason: str,
) -> str:
    """Where the device's current reading came from, as far as Poise can tell.

    Ordered by evidence strength. ``match_tolerance`` is the re-quantise
    distance (``convergence_tolerance(step)``, floored at 0.5 K) — the same
    number the convergence watchdog judges by, so the two cannot disagree about
    what "the device is where we put it" means. That was the original defect.
    """
    if own_change and stale_own_echo:
        return STALE_OWN_ECHO  # our Context, but of a superseded command
    if own_change:
        return PROVEN_OWN_ECHO
    if adopt_reason == "adopt":
        return FOREIGN
    if adopt_reason not in _DETECTOR_RAN:
        return UNKNOWN  # detector off or suppressed -> no statement
    if (
        actual_sp is not None
        and last_cmd_sp is not None
        and round(abs(actual_sp - last_cmd_sp), 3) <= match_tolerance
    ):
        return CURRENT_COMMAND_MATCH
    if _same(actual_sp, prev_device_sp):
        return ACCEPTED_SETTLE
    return UNKNOWN


def reassert_idempotent(
    *,
    target_snapped: float,
    last_cmd_sp: float | None,
    actual_sp: float | None,
    prev_device_sp: float | None,
    provenance: str,
    cmd_episode_ts: float | None,
    last_sp_write_ts: float | None,
    now: float,
    mode_changed: bool = False,
    settle_min_s: float = EPISODE_SETTLE_MIN_S,
    liveness_s: float = REASSERT_LIVENESS_S,
) -> bool:
    """True when re-sending the command in force cannot change anything.

    Every condition is necessary; the order is cheapest-first.

    0. the device's MODE has not just changed,
    1. the target IS the command in force (a changed target is a new episode),
    2. an episode is running and the device had time to react,
    3. the device has come to rest (two identical readings),
    4. the reading is positively classified (:data:`RELEASING`),
    5. the liveness escape has not expired.

    Condition 0 is the same class of exception as the liveness escape, and it
    was missed on the first pass: the fixpoint argument assumes the device is
    in the state it was in when the command last failed to move it. A mode
    change IS a change of that state — a device coming back from ``off``, or
    switching heat/cool, may have parked or reinterpreted its setpoint while
    reporting the same number — so the premise is void and
    :func:`should_write`'s own ``mode_changed`` shortcut must not be vetoed
    here. Same reasoning as V3 for a reboot, same conclusion.

    Deliberately NOT a statement about the device being healthy — see
    :mod:`custom_components.poise.safety.write_convergence`. A suppressed
    re-assert must be folded into that watchdog as divergence evidence, or the
    detector for "device never applies our commands" goes blind (T2).
    """
    if mode_changed:
        return False  # the device state the premise rests on just changed
    if last_cmd_sp is None or not _same(target_snapped, last_cmd_sp):
        return False
    if cmd_episode_ts is None or (now - cmd_episode_ts) < settle_min_s:
        return False
    if actual_sp is None or not _same(actual_sp, prev_device_sp):
        return False  # still moving, or unreadable -> the premise is void
    if provenance not in RELEASING:
        return False
    if last_sp_write_ts is None:
        return True
    if now < last_sp_write_ts:
        return False  # see _stale_anchor
    # V3: once the escape interval has elapsed, one write goes out again — the
    # commit re-stamps the clock, so the next interval starts by itself.
    return (now - last_sp_write_ts) < liveness_s


def quantization_settle_delta(
    *,
    declared_step: float | None,
    last_cmd_sp: float | None,
    actual_sp: float | None,
    suppressed: int,
    min_suppressed: int = QUANT_MIN_SUPPRESSED,
) -> float | None:
    """The resting distance worth reporting, or ``None`` when there is nothing.

    The M3 advisory of the plan, in its cheap half: NOT a grid inference (that
    is the deferred part), but the observation this module already pays for.
    Within ONE command episode — ``suppressed`` is reset by the episode anchor,
    so the count cannot survive a changed command — the device has repeatedly
    come to rest further from the command than its declared step can explain.

    The band is narrow on both sides, and that is what makes it a statement:

    * below ``declared_step / 2`` the distance is ordinary rounding on the
      declared grid and means nothing;
    * above ``convergence_tolerance(step)`` :func:`reassert_idempotent` never
      releases, so ``suppressed`` never climbs — a clamped, jammed or
      wrong-mode valve cannot reach here at all. That case belongs to
      :mod:`custom_components.poise.safety.write_convergence`, which escalates
      it as a fault instead of as advice.

    ``declared_step`` is the actuator's own ``target_temp_step`` attribute, not
    the resolved step the write gate falls back to: the claim is about what the
    device DECLARES, so a missing declaration yields no claim rather than one
    about a Poise default.

    What is left between the two is a device whose real grid is coarser than
    the one it declares. ``possible`` stays in the issue's name: a fixed
    calibration offset inside the device produces the same reading, and this
    function cannot tell the two apart. The reported text therefore says what
    was measured and which setting to check — it does not assert a cause.
    """
    if suppressed < min_suppressed:
        return None
    if declared_step is None or declared_step <= 0.0:
        return None  # the device declares no step -> no claim about one
    if last_cmd_sp is None or actual_sp is None:
        return None
    delta = round(abs(actual_sp - last_cmd_sp), 3)
    return delta if delta > declared_step / 2.0 else None


def reassert_throttled(
    *,
    target_snapped: float,
    last_cmd_sp: float | None,
    cmd_episode_ts: float | None,
    last_sp_write_ts: float | None,
    now: float,
    mode_changed: bool = False,
    min_interval_s: float = MIN_SETPOINT_REASSERT_INTERVAL_S,
) -> bool:
    """True while an identical re-assert should simply wait its turn (M4).

    The second consumer of the command episode, and deliberately the WEAKER
    of the two. :func:`reassert_idempotent` proves a write cannot achieve
    anything and needs settle plus provenance to do so; this one proves
    nothing and only bounds the RATE at which the same command is repeated.
    It therefore covers exactly the cases M2 correctly declines: the device is
    still moving, or its reading cannot be classified, so Poise keeps
    asserting — but ten times an hour, not sixty.

    What is never throttled, because none of it is a re-assert:

    * a different target — schedule, override, window event, frost or any
      other safety path all produce a NEW command and go out on the tick they
      are decided;
    * a mode change, for the reason given in :func:`reassert_idempotent`;
    * the first write of an episode (``cmd_episode_ts`` is what an episode
      HAS, and ``last_sp_write_ts`` what it needs to be measured against).

    A throttled re-assert is silence like a suppressed one, so the convergence
    watchdog must be fed it the same way (T2) — otherwise a device that never
    applies a command would be judged on one write per ten minutes.
    """
    if mode_changed:
        return False
    if last_cmd_sp is None or not _same(target_snapped, last_cmd_sp):
        return False  # a new command is never throttled
    if cmd_episode_ts is None or last_sp_write_ts is None:
        return False  # nothing has been commanded yet -> nothing to repeat
    if _stale_anchor(now, last_sp_write_ts):
        return False
    return (now - last_sp_write_ts) < min_interval_s


def mode_reassert_throttled(
    *,
    desired_mode: str,
    last_commanded_hvac: str | None,
    last_mode_nudge_ts: float | None,
    now: float,
    min_interval_s: float = MIN_MODE_REASSERT_INTERVAL_S,
) -> bool:
    """True while an identical re-nudge of the same mode should wait (M5).

    The mode channel's half of the write economy, and the ONLY half it gets.
    ``needs_mode_nudge`` is "current != desired", evaluated every tick, so a
    device that never adopts the commanded mode is nudged sixty times an hour
    for as long as it refuses — the same 1440/day shape the setpoint channel
    had, on the same battery.

    WHY THERE IS NO MODE COUNTERPART TO :func:`reassert_idempotent`. The
    setpoint veto rests on a fixpoint: the device came to rest at a value its
    grid can represent, so the identical command provably cannot move it, and
    provenance says the reading is ours. None of that transfers. A device
    sitting in the wrong MODE has not "settled on a representable
    approximation" — it has declined, or lost, the command. The honest reading
    of a mode that does not take is a fault, and the answer to a fault is to
    keep asserting, more slowly. So this function bounds the rate and stops
    there; the *diagnosis* belongs to
    :mod:`custom_components.poise.safety.write_convergence`, which is why the
    caller must fold a throttled re-nudge into that watchdog exactly as if it
    had been sent (T2). Silence that the watchdog cannot see is how a device
    that never applies our commands would be judged on one nudge per ten
    minutes.

    Never throttled:

    * a mode CHANGE (``desired != last_commanded_hvac`` — the same comparison
      the executor evaluates at dispatch time and the commit folds as
      ``mode_changed``): the first assert of a new mode goes out on the tick it
      is decided, always;
    * the first nudge of a run (``last_mode_nudge_ts is None``).

    The clock is ``last_mode_nudge_ts`` — the last mode DISPATCH — and not
    ``last_hvac_cmd_ts``, which moves only on a real change because it arms the
    mode echo window. Measuring the rate against the change anchor would let
    the limit expire once and then never again. The split mirrors
    ``last_sp_write_ts`` (physical write) against ``cmd_episode_ts`` (command
    change) on the setpoint side.
    """
    if last_commanded_hvac is None or desired_mode != last_commanded_hvac:
        return False  # a mode change is never throttled
    if last_mode_nudge_ts is None:
        return False  # nothing dispatched yet -> nothing to repeat
    if _stale_anchor(now, last_mode_nudge_ts):
        return False
    return (now - last_mode_nudge_ts) < min_interval_s
