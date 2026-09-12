"""Write economy: the re-assert loop must terminate, and silence must be visible.

The two acceptance tests of the 2026-09-12 plan (``docs/Konzepte/
2026-09-12_Plan_Schreiblast-M2-M4.md``), written red before M2 existed.

Background: ``docs/reviews/2026-09-12-TRV-Schreiblast-Zigbee.md``. A
``customize`` entry claimed ``target_temp_step: 0.1`` for a device whose
effective grid is 0.5 K. Poise then snapped to 0.1, the device settled 0.2 K
away, and the write gate's ``>= 0.2`` fired every tick — 1440 setpoint writes
a day on a battery TRV, with no diagnostic anywhere.

Pure: no Home Assistant, no fixtures. ``_run_reassert_loop`` is a hand-rolled
``plan_setpoint_write`` + commit — it composes the SAME functions the actuation
path composes, in the same order, so a green here means the real gate changed.
"""

from __future__ import annotations

from custom_components.poise.const import (
    SETPOINT_ADOPT_ECHO_WINDOW_S,
    WRITE_DEADBAND_C,
)
from custom_components.poise.control.override import setpoint_adopt_reason
from custom_components.poise.control.tick_resolve import should_write, snap_to_step
from custom_components.poise.control.write_economy import (
    CURRENT_COMMAND_MATCH,
    MIN_MODE_REASSERT_INTERVAL_S,
    MIN_SETPOINT_REASSERT_INTERVAL_S,
    QUANT_MIN_SUPPRESSED,
    REASSERT_LIVENESS_S,
    classify_settle,
    mode_reassert_throttled,
    quantization_settle_delta,
    reassert_idempotent,
    reassert_throttled,
)
from custom_components.poise.safety.sensor_watchdog import (
    SELECT_HANDBACK_RETRY_S,
    sensor_source_handback_target,
)
from custom_components.poise.safety.write_convergence import (
    CONV_FAIL_WRITES,
    WriteConvergenceWatchdog,
    convergence_tolerance,
)

_TICK_S = 60.0
_MINUTES = 30


def _run_reassert_loop(
    *,
    target: float,
    device_before: float,
    settles_to: float,
    step: float,
    minutes: int = _MINUTES,
    offline: frozenset[int] = frozenset(),
) -> dict:
    """Drive ``minutes`` ticks of the real gate composition against a device.

    ``device_before`` is what the actuator reports until our first write;
    ``settles_to`` is where it comes to rest afterwards — what it could
    represent of our command, with the rest re-quantised away.

    Mirrors the live tick: observe (classify + BOTH verdicts) → gate
    (``should_write`` behind the M2 and M4 vetoes, in the gate's order) →
    commit (stamp the write time, and the episode anchor ONLY on a real
    command change). No own Context is handed through, which is the hard case:
    the device's later reports look foreign.

    M4 is composed in here on purpose. Leaving it out would make the loop a
    weaker machine than the one that ships, and every count below would be an
    upper bound on a gate that no longer exists.
    """
    last_written_sp: float | None = None
    last_write_ts: float | None = None
    last_cmd_sp: float | None = None
    prev_device_sp: float | None = None
    cmd_episode_ts: float | None = None
    device_sp = device_before
    now = 0.0
    writes = 0
    suppressed = 0
    throttled = 0
    reasons: list[str] = []
    provenances: list[str] = []
    for tick in range(minutes):
        if tick in offline:
            # Observe stage: an offline actuator ENDS the command episode (V3,
            # availability half). Nothing is dispatched to it either.
            cmd_episode_ts = None
            now += _TICK_S
            continue
        snapped = snap_to_step(target, step)
        adopt_reason = setpoint_adopt_reason(
            device_sp=device_sp,
            last_written_sp=last_written_sp,
            last_write_ts=last_write_ts,
            now=now,
            echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S,
            deadband=max(WRITE_DEADBAND_C, step),
            prev_device_sp=prev_device_sp,
            pre_write_sp=device_sp,
            frost_floor=7.0,
        )
        provenance = classify_settle(
            own_change=False,  # no Context handed through
            stale_own_echo=False,
            actual_sp=device_sp,
            last_cmd_sp=last_cmd_sp,
            prev_device_sp=prev_device_sp,
            match_tolerance=convergence_tolerance(step),
            adopt_reason=adopt_reason,
        )
        idempotent = reassert_idempotent(
            target_snapped=snapped,
            last_cmd_sp=last_cmd_sp,
            actual_sp=device_sp,
            prev_device_sp=prev_device_sp,
            provenance=provenance,
            cmd_episode_ts=cmd_episode_ts,
            last_sp_write_ts=last_write_ts,
            now=now,
        )
        rate_limited = reassert_throttled(
            target_snapped=snapped,
            last_cmd_sp=last_cmd_sp,
            cmd_episode_ts=cmd_episode_ts,
            last_sp_write_ts=last_write_ts,
            now=now,
        )
        wrote = (
            not idempotent
            and not rate_limited
            and should_write(
                device_sp, snapped, mode_changed=False, deadband=WRITE_DEADBAND_C
            )
        )
        reasons.append(adopt_reason)
        provenances.append(provenance)
        prev_device_sp = device_sp
        if wrote:
            writes += 1
            last_written_sp = snapped
            last_write_ts = now  # re-arms the 120 s adoption echo window
            # Episode anchor: a REAL command change, or a write that BEGINS
            # an episode (there is none after a dropout). Both halves, exactly
            # as ``ZoneRuntime`` commits them.
            if last_cmd_sp != snapped or cmd_episode_ts is None:
                cmd_episode_ts = now
            last_cmd_sp = snapped
            device_sp = settles_to  # the device takes what it can represent
        else:
            # A tick can be both; counted separately so a test can say WHICH
            # gate held the write back.
            suppressed += 1 if idempotent else 0
            throttled += 1 if rate_limited else 0
        now += _TICK_S
    return {
        "writes": writes,
        "suppressed": suppressed,
        "throttled": throttled,
        "reasons": reasons,
        "provenances": provenances,
    }


def test_honest_step_needs_exactly_one_write() -> None:
    """Non-vacuity control: with the device's REAL grid the gate always worked.

    The ``badezimmer_sonoff_trv`` case, the one actuator the faulty
    ``customize`` block never touched: target 22.3 snaps to 22.5 on the real
    0.5 K grid, one write moves the device there, every later tick sees
    distance zero. Green before M2 and after it — if this one ever goes red,
    the loop below is measuring something else.
    """
    run = _run_reassert_loop(target=22.3, device_before=21.0, settles_to=22.5, step=0.5)
    assert run["writes"] == 1, "an honest step must settle after the first write"


def test_reassert_loop_terminates_on_a_requantising_device() -> None:
    """T1 — the 60/120 circle.

    Tick and re-assert 60 s, adoption echo window 120 s, no own Context.
    Command 15.2, device settles at 15.0: |15.2 - 15.0| = 0.2, and the write
    gate's ``>= 0.2`` is true, forever. Every write re-stamps ``last_write_ts``,
    so ``setpoint_adopt_reason`` never leaves the echo-window branch — which is
    why the termination argument may not depend on it.

    One write is correct (the device has to be told once). Thirty was the
    defect.
    """
    run = _run_reassert_loop(target=15.2, device_before=15.5, settles_to=15.0, step=0.1)
    assert run["writes"] <= 2, (
        f"{run['writes']} writes in {_MINUTES} minutes — the re-assert loop "
        "does not terminate"
    )
    assert run["suppressed"] >= _MINUTES - 3, "the rest must be suppressed"
    # With M4 composed in, the measured value is 1: the tick that used to slip
    # through before the episode had settled is now rate-limited. The bound
    # above stays the assertion, because ONE write is correct behaviour and
    # two would still be — thirty was the defect.
    assert run["throttled"] > 0, "M4 must be doing something in this loop"
    # The verdict rests on the command episode, not on the adoption reason:
    # 15.0 is within one re-quantise step of the command in force.
    assert run["provenances"][-1] == CURRENT_COMMAND_MATCH
    # And the circle opens from the other end too, which is worth pinning:
    # once the loop stops, ``last_write_ts`` stops being re-stamped, the 120 s
    # echo window finally expires, and the adoption detector reaches
    # ``stable_offset`` — the branch it could never see while Poise was
    # re-writing every 60 s. Termination is what makes the classification
    # honest again, not the other way round.
    assert run["reasons"][1] == "echo_window"
    assert run["reasons"][-1] == "stable_offset"


def test_liveness_lets_one_write_through_after_the_escape_interval() -> None:
    """V3 — suppression is bounded, because the channel is not lossless.

    A sleepy Zigbee end device can drop a write and a TRV can reboot (the field
    case reports ``power_outage_count: 852``), so "did not work last time" must
    not mean "never again". Over a window longer than ``REASSERT_LIVENESS_S``
    at least one further write has to go out.
    """
    minutes = int(REASSERT_LIVENESS_S / _TICK_S) + 5
    run = _run_reassert_loop(
        target=15.2,
        device_before=15.5,
        settles_to=15.0,
        step=0.1,
        minutes=minutes,
    )
    assert run["writes"] >= 2, "suppression must expire on the liveness clock"
    assert run["writes"] <= 4, "but it must not become a re-assert loop again"


def test_suppressed_reassert_still_escalates_a_device_that_never_applies() -> None:
    """T2 — no silent machine.

    The counterpart to T1, and the reason this cannot simply be "write less".
    A valve that is jammed, clamped or in the wrong mode never reaches the
    commanded value; ``WriteConvergenceWatchdog`` exists to escalate that into
    a repair issue, and it counts divergence only in its ``elif wrote:``
    branch. Suppression therefore has to be folded in as the evidence the write
    would have produced — exactly what ``phase_actuate`` now does with
    ``wrote=plan.write_setpoint or _suppressed``.

    21.0 commanded against a device stuck at 18.0 is 3.0 K apart, far outside
    any re-quantisation tolerance: unambiguously a failure, not a settle.
    """
    tolerance = convergence_tolerance(0.5)
    watchdog = WriteConvergenceWatchdog()
    now = 0.0
    for tick in range(_MINUTES):
        written = tick == 0  # the first write goes out, then M2 suppresses
        suppressed = not written
        watchdog.observe_setpoint(
            actual_sp=18.0,
            last_written_sp=21.0,  # the COMMAND baseline (last_cmd_sp)
            tolerance=tolerance,
            wrote=written or suppressed,  # the phase_actuate fold
            evidence_fresh=True,
            now=now,
        )
        now += _TICK_S
    assert watchdog.sp_diverged_writes >= CONV_FAIL_WRITES, (
        "a suppressed re-assert must still count as divergence evidence"
    )
    assert watchdog.escalated(now=now), (
        "a device that never applies the command must escalate even while "
        "Poise has stopped re-asserting"
    )


def test_watchdog_stays_quiet_when_the_device_merely_requantises() -> None:
    """The other half of T2: folding suppression in must not cry wolf.

    The field case — commanded 15.2, device at 15.0 — is 0.2 K apart, inside
    the floored re-quantise tolerance. The watchdog's converged branch runs
    first, so counting the suppressed re-assert as evidence changes nothing.
    """
    watchdog = WriteConvergenceWatchdog()
    now = 0.0
    for _ in range(_MINUTES):
        watchdog.observe_setpoint(
            actual_sp=15.0,
            last_written_sp=15.2,
            tolerance=convergence_tolerance(0.1),
            wrote=True,  # as if every tick were a suppressed re-assert
            evidence_fresh=True,
            now=now,
        )
        now += _TICK_S
    assert watchdog.sp_diverged_writes == 0
    assert not watchdog.escalated(now=now)


# --------------------------------------------------------------- M3 advisory
def _advice(**over: object) -> float | None:
    """The field case, with one knob turned per test.

    Küche: declared 0.1 K, commanded 15.2, the device rests at 15.0 — 0.2 K
    away, which 0.1 K cannot explain, repeated for a whole command episode.
    """
    args: dict = {
        "declared_step": 0.1,
        "last_cmd_sp": 15.2,
        "actual_sp": 15.0,
        "suppressed": QUANT_MIN_SUPPRESSED,
    }
    args.update(over)
    return quantization_settle_delta(**args)  # type: ignore[arg-type]


def test_the_field_case_is_reported_with_its_measured_distance() -> None:
    """What the advisory exists for — and it reports the MEASURED number.

    0.2 K, not "a mismatch": the issue text names the distance so the user can
    compare it against the grid their device really uses. This is the line that
    would have shown the case on day one.
    """
    assert _advice() == 0.2


def test_one_settle_is_not_a_diagnosis() -> None:
    """Below the evidence floor there is nothing to say.

    A device can be slow, an echo can be missed. The episode anchor resets
    ``suppressed`` on every real command change, so reaching the floor means
    the SAME command has rested wrong that many times — not that Poise has
    been running a while.
    """
    assert _advice(suppressed=QUANT_MIN_SUPPRESSED - 1) is None


def test_an_honest_grid_says_nothing_even_when_suppressed() -> None:
    """Non-vacuity from the other side: suppression alone is not the signal.

    The bathroom TRV, the one the faulty ``customize`` block never touched:
    declared 0.5 K and resting 0.2 K away is ordinary rounding on its own
    grid. M2 still suppresses the re-assert there — correctly — and the
    advisory must stay quiet, or it would fire on every well-behaved device.
    """
    assert _advice(declared_step=0.5) is None


def test_a_device_that_declares_nothing_gets_no_advice() -> None:
    """No declaration, no claim about one.

    With the attribute missing the write gate falls back to a Poise default;
    telling the user their device "declares" that default would be a statement
    about our own code.
    """
    assert _advice(declared_step=None) is None


def test_an_unreadable_setpoint_is_not_evidence() -> None:
    """The premise is a MEASURED resting distance; without a reading there is
    none, and a missing command baseline leaves nothing to measure against."""
    assert _advice(actual_sp=None) is None
    assert _advice(last_cmd_sp=None) is None


def test_the_gross_failure_case_belongs_to_the_watchdog_not_here() -> None:
    """Boundary with ``write_convergence`` — the reason this cannot fire on a
    broken valve.

    A device clamped 3 K below the command never satisfies
    ``reassert_idempotent`` (the distance exceeds ``convergence_tolerance``),
    so ``suppressed`` never climbs and this function is never reached with
    that evidence. Pinned as a unit statement anyway: with the evidence floor
    unmet, no advice — the fault path stays the watchdog's (T2).
    """
    assert _advice(actual_sp=18.0, last_cmd_sp=21.0, suppressed=0) is None


# ------------------------------------------------- M4 + the premise it rests on
def _throttle(**over: object) -> bool:
    """A settled episode, 60 s after its write — the ordinary re-assert tick."""
    args: dict = {
        "target_snapped": 15.2,
        "last_cmd_sp": 15.2,
        "cmd_episode_ts": 0.0,
        "last_sp_write_ts": 0.0,
        "now": 60.0,
    }
    args.update(over)
    return reassert_throttled(**args)  # type: ignore[arg-type]


def test_an_identical_reassert_waits_out_the_interval() -> None:
    """M4 — the rate limit, on the same anchor as M2.

    This is the case M2 declines and must decline: no settle evidence, no
    provenance, so nothing is PROVEN about the write. M4 claims nothing
    either; it only says that sixty repetitions an hour of one command is not
    a regulation strategy.
    """
    assert _throttle() is True
    assert _throttle(now=MIN_SETPOINT_REASSERT_INTERVAL_S + 1.0) is False


def test_a_new_command_is_never_throttled() -> None:
    """The property the whole feature stands or falls on.

    Schedule, override, window event, frost rescue — every one of them
    produces a DIFFERENT target, and a different target is a new episode, not
    a re-assert. If this ever goes red, M4 is delaying control actions and
    must be reverted, not tuned.
    """
    assert _throttle(target_snapped=21.0) is False


def test_nothing_commanded_yet_is_not_a_repetition() -> None:
    """The first write of an episode has nothing to repeat."""
    assert _throttle(cmd_episode_ts=None) is False
    assert _throttle(last_sp_write_ts=None) is False
    assert _throttle(last_cmd_sp=None) is False


def test_a_mode_change_defeats_both_gates() -> None:
    """The defect M4 surfaced in M2, pinned for both.

    ``should_write`` writes unconditionally on a mode change, because a device
    coming back from ``off`` or switching heat/cool may have parked or
    reinterpreted its setpoint while still REPORTING the same number. M2's
    fixpoint assumes the device is in the state in which the command last
    failed to move it — a mode change is precisely a change of that state, so
    the premise is void, exactly as it is for the reboot V3 covers.

    Shipped wrong once: the M2 veto sat ahead of ``should_write`` in the gate's
    ``and`` chain and would have swallowed the post-mode-change write.
    """
    idem = dict(
        target_snapped=15.2,
        last_cmd_sp=15.2,
        actual_sp=15.0,
        prev_device_sp=15.0,
        provenance=CURRENT_COMMAND_MATCH,
        cmd_episode_ts=0.0,
        last_sp_write_ts=0.0,
        now=600.0,
    )
    assert reassert_idempotent(**idem) is True  # type: ignore[arg-type]
    assert reassert_idempotent(**idem, mode_changed=True) is False  # type: ignore[arg-type]
    assert _throttle(mode_changed=True) is False


def test_the_two_gates_compose_with_the_liveness_escape() -> None:
    """M2 and M4 must not deadlock each other.

    M2 releases one write per ``REASSERT_LIVENESS_S`` (3600 s) so a lost write
    or a rebooted TRV is eventually re-told; M4 must be open by then, or that
    escape would be silently cancelled by the rate limit. It is, and by a wide
    margin — but the relation is an invariant, not an accident, so it is
    pinned rather than assumed.
    """
    assert MIN_SETPOINT_REASSERT_INTERVAL_S < REASSERT_LIVENESS_S
    assert _throttle(now=REASSERT_LIVENESS_S) is False


def test_a_dropout_resumes_writing_and_does_not_restart_the_loop() -> None:
    """V3's availability half, and the commit clause that makes it safe.

    Two rules have to hold together, and each one alone is a defect:

    * an offline actuator ends the command episode, so the first tick after it
      returns writes immediately — a TRV that rebooted while away (the field
      case reports ``power_outage_count: 852``) must be told again, and the
      "it did not work last time" premise says nothing about it. Without this,
      M4 swallows the recovery write for its whole interval — which is exactly
      how ``test_p3_18a_actuator_dropout_then_recovery_resumes_writes`` went
      red;
    * a write that BEGINS an episode stamps the anchor even when the command
      value is unchanged — which it usually is after a dropout. Without this,
      no episode ever starts again, neither gate can ever hold, and the
      re-assert loop is back unbounded. Nothing in the glue suite would catch
      that: writes DO resume there, forever.

    So: one write, silence while away, one write on recovery, then quiet.
    """
    run = _run_reassert_loop(
        target=15.2,
        device_before=15.5,
        settles_to=15.0,
        step=0.1,
        offline=frozenset({1, 2}),
    )
    assert run["writes"] == 2, (
        f"{run['writes']} writes — expected one before the dropout and one "
        "after the recovery"
    )
    assert run["suppressed"] + run["throttled"] > 0, "and quiet afterwards"


# --- Phase 2a: the other three channels -------------------------------------


def _run_mode_nudge_loop(
    *,
    desired: str,
    device_mode: str,
    adopts_at_tick: int | None = None,
    minutes: int = _MINUTES,
) -> dict[str, int]:
    """The mode channel's re-nudge loop, composed like the setpoint one above.

    ``needs_mode_nudge`` + the M5 rate limit + the commit's two stamps, in the
    order ``_stage_mode_nudge`` runs them. ``adopts_at_tick`` is the tick on
    which the device finally reports ``desired`` — ``None`` means it never
    does, which is the case the rate limit exists for and also the case the
    convergence watchdog must keep seeing.
    """
    last_commanded: str | None = None
    last_nudge_ts: float | None = None
    writes = 0
    throttled = 0
    evidence = 0  # ticks the watchdog was fed a re-nudge as divergence
    for tick in range(1, minutes + 1):
        now = tick * _TICK_S
        if adopts_at_tick is not None and tick >= adopts_at_tick:
            device_mode = desired
        nudge = device_mode != desired  # needs_mode_nudge, supported=True
        if nudge and desired == last_commanded:
            evidence += 1  # T2: counted BEFORE the throttle can cancel it
        if nudge and mode_reassert_throttled(
            desired_mode=desired,
            last_commanded_hvac=last_commanded,
            last_mode_nudge_ts=last_nudge_ts,
            now=now,
        ):
            nudge = False
            throttled += 1
        if nudge:
            writes += 1
            last_nudge_ts = now
            last_commanded = desired
    return {"writes": writes, "throttled": throttled, "evidence": evidence}


def test_a_mode_that_never_takes_is_asserted_ten_times_an_hour_not_sixty() -> None:
    """The M5 acceptance test — the mode channel's version of the field case.

    A TRV that keeps falling back to its own weekly schedule (``system_mode``
    back to ``auto``) is nudged by ``needs_mode_nudge`` on every single tick,
    because "current != desired" is true on every single tick. That is the
    same 1440/day shape the setpoint channel had, on the same battery, and it
    had no gate at all.

    The limit must NOT make it stop: a mode that does not take is a fault, and
    Poise keeps telling the device. It only slows down — first assert
    immediate, then one per interval.
    """
    run = _run_mode_nudge_loop(desired="heat", device_mode="auto", minutes=30)
    # 30 unthrottled nudges before, three now: the first tick, then one per
    # ``MIN_MODE_REASSERT_INTERVAL_S``. Ten times an hour is the ceiling, not
    # the rate — the first assert of a run is free, so 30 minutes buy three.
    assert MIN_MODE_REASSERT_INTERVAL_S == 600.0
    assert run["writes"] == 3, f"{run['writes']} nudges in 30 minutes"
    assert run["throttled"] == 27
    # ...and it never falls silent: the interval is finite, so the next
    # assertion is always scheduled.
    assert (
        _run_mode_nudge_loop(desired="heat", device_mode="auto", minutes=180)["writes"]
        > run["writes"]
    )


def test_a_throttled_re_nudge_still_reaches_the_convergence_watchdog() -> None:
    """T2 for the mode channel, stated as a test rather than as a comment.

    The watchdog for "this device never applies our commands" counts evidence
    per nudge. If the rate limit removed the nudge before the fold, a device
    that refuses ``heat`` forever would produce one piece of evidence per ten
    minutes instead of one per tick — the detector would need hours to reach
    its threshold, and the whole point of the limit was to change the WRITE
    rate, not the DIAGNOSIS rate.
    """
    run = _run_mode_nudge_loop(desired="heat", device_mode="auto", minutes=30)
    assert run["evidence"] == run["throttled"] + run["writes"] - 1, (
        "every re-nudge must be evidence — sent or throttled; only the very "
        "first nudge is not a RE-nudge"
    )


def test_a_real_mode_change_is_never_throttled() -> None:
    """The exemption that keeps the limit honest.

    Every safety and comfort path that changes the mode — window open, frost,
    a user override, the fan-first FSM, the idle park of a reversible AC —
    produces a DIFFERENT desired mode, and none of them may wait behind a
    ten-minute timer. The comparison is the same one the executor evaluates at
    dispatch time and the commit folds as ``mode_changed``, so the two cannot
    drift apart.
    """
    assert (
        mode_reassert_throttled(
            desired_mode="cool",
            last_commanded_hvac="heat",
            last_mode_nudge_ts=0.0,
            now=1.0,  # one second after the last dispatch
        )
        is False
    )
    # and the first nudge of a run, which has no previous dispatch at all
    assert (
        mode_reassert_throttled(
            desired_mode="heat",
            last_commanded_hvac=None,
            last_mode_nudge_ts=None,
            now=1.0,
        )
        is False
    )


def test_the_sensor_source_handback_retries_with_a_backoff_not_every_tick() -> None:
    """The third channel: the ADR-0029 release during a room-sensor outage.

    The release is due for as long as the select still reads ``external``, and
    the write is the only thing that can change that — so a device that keeps
    reverting the select (SONOFF TRVZB, Koenkk/zigbee2mqtt#29650) is written
    once a minute for the whole outage. An outage lasting a workday spends a
    four-figure write count on a battery valve.

    The first attempt stays immediate — a sensor outage is a safety event and
    the release must not wait behind a timer — and only the repetitions are
    bounded.
    """
    kw = {
        "select_entity_id": "select.kuche_trv_sensor",
        "select_state": "external",
        "configured_feed": "number.kuche_trv_ext_temp",
        "last_fed": 21.0,
    }
    # first tick of the outage: released immediately, no attempt on record
    assert sensor_source_handback_target(**kw, last_attempt_ts=None, now=0.0)
    # the device did not take it — the next ticks are silent
    assert sensor_source_handback_target(**kw, last_attempt_ts=0.0, now=60.0) is None
    assert (
        sensor_source_handback_target(
            **kw, last_attempt_ts=0.0, now=SELECT_HANDBACK_RETRY_S - 1.0
        )
        is None
    )
    # ...and then it is asserted again. Bounded, never vetoed.
    assert sensor_source_handback_target(
        **kw, last_attempt_ts=0.0, now=SELECT_HANDBACK_RETRY_S
    )
    # a select that already reads ``internal`` is not written at all, backoff
    # or no backoff — the idempotence that was always there stays first.
    assert (
        sensor_source_handback_target(
            **{**kw, "select_state": "internal"},
            last_attempt_ts=None,
            now=0.0,
        )
        is None
    )


def test_an_anchor_from_another_clock_never_silences_a_write() -> None:
    """A swapped monotonic clock must fail OPEN on both throttles.

    The clock is injected (ADR-0006/0014), so "monotonic" holds within one
    clock and not across two. A replay harness, or a test that installs its own
    clock after setup, leaves an anchor stamped from the previous era; ``now -
    anchor`` is then large and NEGATIVE, which reads as "just written" and
    would keep the gate shut until the clock caught up — potentially forever.

    Found the honest way: the mode limit swallowed the re-nudge in
    ``test_nudge_recorder_is_armed_after_setup``, the control test whose entire
    job is to prove the neighbouring "no re-nudge" assertions are not
    vacuous. A gate that can silence THAT is a gate that can silence a zone.
    """
    # M5: dispatched at 5000 on the old clock, asked at 1000 on the new one.
    assert (
        mode_reassert_throttled(
            desired_mode="heat",
            last_commanded_hvac="heat",
            last_mode_nudge_ts=5000.0,
            now=1000.0,
        )
        is False
    )
    # ...while the same pair on ONE clock throttles as designed.
    assert (
        mode_reassert_throttled(
            desired_mode="heat",
            last_commanded_hvac="heat",
            last_mode_nudge_ts=1000.0,
            now=1060.0,
        )
        is True
    )
    # M4, same exposure, same direction.
    assert (
        reassert_throttled(
            target_snapped=20.0,
            last_cmd_sp=20.0,
            cmd_episode_ts=5000.0,
            last_sp_write_ts=5000.0,
            now=1000.0,
        )
        is False
    )
    # M2's liveness escape too: a stale anchor must not read as "written
    # recently enough", or the V3 escape would never fire again.
    assert (
        reassert_idempotent(
            target_snapped=20.0,
            last_cmd_sp=20.0,
            actual_sp=20.0,
            prev_device_sp=20.0,
            provenance=CURRENT_COMMAND_MATCH,
            cmd_episode_ts=0.0,
            last_sp_write_ts=5000.0,
            now=1000.0,
        )
        is False
    )
