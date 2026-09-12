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
    REASSERT_LIVENESS_S,
    classify_settle,
    reassert_idempotent,
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
) -> dict:
    """Drive ``minutes`` ticks of the real gate composition against a device.

    ``device_before`` is what the actuator reports until our first write;
    ``settles_to`` is where it comes to rest afterwards — what it could
    represent of our command, with the rest re-quantised away.

    Mirrors the live tick: observe (classify + idempotence verdict) → gate
    (``should_write`` behind the M2 veto) → commit (stamp the write time, and
    the episode anchor ONLY on a real command change). No own Context is handed
    through, which is the hard case: the device's later reports look foreign.
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
    reasons: list[str] = []
    provenances: list[str] = []
    for _ in range(minutes):
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
        wrote = not idempotent and should_write(
            device_sp, snapped, mode_changed=False, deadband=WRITE_DEADBAND_C
        )
        reasons.append(adopt_reason)
        provenances.append(provenance)
        prev_device_sp = device_sp
        if wrote:
            writes += 1
            last_written_sp = snapped
            last_write_ts = now  # re-arms the 120 s adoption echo window
            if last_cmd_sp != snapped:  # episode anchor: only a REAL change
                cmd_episode_ts = now
            last_cmd_sp = snapped
            device_sp = settles_to  # the device takes what it can represent
        elif idempotent:
            suppressed += 1
        now += _TICK_S
    return {
        "writes": writes,
        "suppressed": suppressed,
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
