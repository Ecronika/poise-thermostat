"""Write-convergence watchdog (review C.8): pure counter/escalation logic.

The watchdog turns the silent "device never applies our commands" condition
into telemetry + a repair issue: it counts consecutive unconverged setpoint
re-asserts and identical mode re-nudges, resets on observed convergence, and
escalates only after both a count threshold and a minimum elapsed time.
Adversarial-review hardening: evidence expires (stale episodes must not merge
with fresh counts), stale device states are no evidence in either direction,
and settling within one tolerance INCLUSIVE reads as converged (device
re-quantise), with the tolerance floored at half a Kelvin.
"""

from __future__ import annotations

from custom_components.poise.safety.write_convergence import (
    CONV_EVIDENCE_TTL_S,
    CONV_FAIL_MIN_S,
    CONV_FAIL_NUDGES,
    CONV_FAIL_WRITES,
    WriteConvergenceWatchdog,
    convergence_tolerance,
)


def _diverge_sp(wd: WriteConvergenceWatchdog, n: int, *, start: float = 0.0) -> float:
    """n divergent re-asserts, one per 60 s tick; returns the last now."""
    now = start
    for i in range(n):
        now = start + 60.0 * i
        wd.observe_setpoint(
            actual_sp=20.0,
            last_written_sp=22.0,
            tolerance=0.5,
            wrote=True,
            evidence_fresh=True,
            now=now,
        )
    return now


def test_initial_state_is_clean() -> None:
    wd = WriteConvergenceWatchdog()
    assert wd.sp_diverged_writes == 0
    assert wd.mode_diverged_nudges == 0
    assert not wd.escalated(now=1e9)


def test_divergent_reasserts_count() -> None:
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, 3)
    assert wd.sp_diverged_writes == 3


def test_convergence_resets_setpoint_counter() -> None:
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, 3)
    # Device settles within one step of the last command — even on a tick
    # without a write, the observation alone clears the episode.
    wd.observe_setpoint(
        actual_sp=21.8,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=False,
        evidence_fresh=True,
        now=200.0,
    )
    assert wd.sp_diverged_writes == 0
    assert not wd.escalated(now=1e9)


def test_delta_at_tolerance_is_converged() -> None:
    # Review fix: exactly ONE tolerance is the canonical device re-quantise
    # distance (truncating 0.5-grid, banker's-rounded 1.0-grid) — it must
    # read as converged, not as permanent divergence. Just above stays
    # divergent.
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, 2)
    wd.observe_setpoint(
        actual_sp=21.5,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=200.0,
    )
    assert wd.sp_diverged_writes == 0  # == tolerance -> converged, episode ends
    wd.observe_setpoint(
        actual_sp=21.4,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=260.0,
    )
    assert wd.sp_diverged_writes == 1  # 0.6 > 0.5 -> divergent


def test_convergence_tolerance_floors_at_half_kelvin() -> None:
    # A missing target_temp_step falls back to 0.1 at the read boundary; the
    # watchdog tolerance must not follow it below a plausible device grid,
    # or every x.2/x.3 target on a real 0.5-grid device reads divergent.
    assert convergence_tolerance(0.1) == 0.5
    assert convergence_tolerance(0.5) == 0.5
    assert convergence_tolerance(1.0) == 1.0


def test_unobservable_ticks_are_no_evidence() -> None:
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, 2)
    # No reported setpoint / no prior command: neither increment nor reset.
    wd.observe_setpoint(
        actual_sp=None,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=200.0,
    )
    wd.observe_setpoint(
        actual_sp=20.0,
        last_written_sp=None,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=260.0,
    )
    assert wd.sp_diverged_writes == 2


def test_stale_state_is_no_evidence() -> None:
    # Review fix: a device state that has not updated since our last write
    # cannot prove the device ignored the command (poll latency) — and it
    # cannot prove convergence either (frozen own-context echo). Hold.
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, 2)
    wd.observe_setpoint(
        actual_sp=20.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=False,
        now=200.0,
    )
    assert wd.sp_diverged_writes == 2  # no increment on stale
    wd.observe_setpoint(
        actual_sp=22.0,  # would read converged — but the state is stale
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=False,
        evidence_fresh=False,
        now=260.0,
    )
    assert wd.sp_diverged_writes == 2  # no reset on stale either


def test_skipped_write_holds_state() -> None:
    # Diverged but nothing written this tick (throttle / adoption / off-hold):
    # the episode neither grows nor clears.
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, 2)
    wd.observe_setpoint(
        actual_sp=20.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=False,
        evidence_fresh=True,
        now=200.0,
    )
    assert wd.sp_diverged_writes == 2


def test_episode_expires_without_fresh_evidence() -> None:
    # Review fix: an evidence-free gap (seasonal idle, long unavailable) must
    # END the episode — a stale count merging with fresh counts would fire
    # the repair issue on the FIRST write of a healthy re-start, inverting
    # the CONV_FAIL_MIN_S protection.
    wd = WriteConvergenceWatchdog()
    last = _diverge_sp(wd, CONV_FAIL_WRITES - 1)
    late = last + CONV_EVIDENCE_TTL_S + 1.0
    wd.observe_setpoint(
        actual_sp=20.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=late,
    )
    # The stale episode expired first; this tick started a NEW one.
    assert wd.sp_diverged_writes == 1
    assert not wd.escalated(now=late + CONV_FAIL_MIN_S - 60.0)


def test_gap_below_ttl_keeps_the_episode() -> None:
    wd = WriteConvergenceWatchdog()
    last = _diverge_sp(wd, 2)
    wd.observe_setpoint(
        actual_sp=20.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=last + CONV_EVIDENCE_TTL_S - 1.0,
    )
    assert wd.sp_diverged_writes == 3


def test_setpoint_escalation_needs_count_and_elapsed() -> None:
    wd = WriteConvergenceWatchdog()
    last = _diverge_sp(wd, CONV_FAIL_WRITES)
    # Count reached but the episode is younger than CONV_FAIL_MIN_S.
    assert last < CONV_FAIL_MIN_S
    assert not wd.escalated(now=last)
    assert wd.escalated(now=CONV_FAIL_MIN_S)


def test_setpoint_escalation_needs_full_count() -> None:
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, CONV_FAIL_WRITES - 1)
    assert not wd.escalated(now=1e9)


def _nudge(wd: WriteConvergenceWatchdog, n: int, *, start: float = 0.0) -> float:
    now = start
    for i in range(n):
        now = start + 60.0 * i
        wd.observe_mode(
            nudged=True,
            re_nudge=True,
            current_matches_desired=False,
            evidence_fresh=True,
            now=now,
        )
    return now


def test_mode_re_nudges_count_and_escalate() -> None:
    wd = WriteConvergenceWatchdog()
    last = _nudge(wd, CONV_FAIL_NUDGES)
    assert wd.mode_diverged_nudges == CONV_FAIL_NUDGES
    assert not wd.escalated(now=last)
    assert wd.escalated(now=CONV_FAIL_MIN_S)


def test_fresh_mode_command_starts_new_episode() -> None:
    wd = WriteConvergenceWatchdog()
    _nudge(wd, 3)
    # A nudge to a NEW desired mode is a fresh command, not divergence
    # evidence: the old episode ends.
    wd.observe_mode(
        nudged=True,
        re_nudge=False,
        current_matches_desired=False,
        evidence_fresh=True,
        now=300.0,
    )
    assert wd.mode_diverged_nudges == 0


def test_mode_match_resets() -> None:
    wd = WriteConvergenceWatchdog()
    _nudge(wd, 3)
    wd.observe_mode(
        nudged=False,
        re_nudge=False,
        current_matches_desired=True,
        evidence_fresh=True,
        now=300.0,
    )
    assert wd.mode_diverged_nudges == 0
    assert not wd.escalated(now=1e9)


def test_unknown_mode_is_no_evidence() -> None:
    # Device mode unknown/unavailable: needs_mode_nudge never fires, and the
    # watchdog neither counts nor clears.
    wd = WriteConvergenceWatchdog()
    _nudge(wd, 2)
    wd.observe_mode(
        nudged=False,
        re_nudge=False,
        current_matches_desired=False,
        evidence_fresh=True,
        now=200.0,
    )
    assert wd.mode_diverged_nudges == 2


def test_stale_mode_state_is_no_evidence() -> None:
    wd = WriteConvergenceWatchdog()
    _nudge(wd, 2)
    wd.observe_mode(
        nudged=True,
        re_nudge=True,
        current_matches_desired=False,
        evidence_fresh=False,
        now=200.0,
    )
    assert wd.mode_diverged_nudges == 2  # stale -> hold
    wd.observe_mode(
        nudged=False,
        re_nudge=False,
        current_matches_desired=True,
        evidence_fresh=False,
        now=260.0,
    )
    assert wd.mode_diverged_nudges == 2  # stale match does not reset


def test_mode_episode_expires_without_fresh_evidence() -> None:
    # The replacement-device class: a weeks-old episode must not fire on the
    # first nudge to a fresh device (persisted last_commanded_hvac makes that
    # nudge a re-nudge).
    wd = WriteConvergenceWatchdog()
    last = _nudge(wd, CONV_FAIL_NUDGES - 1)
    late = last + CONV_EVIDENCE_TTL_S + 1.0
    wd.observe_mode(
        nudged=True,
        re_nudge=True,
        current_matches_desired=False,
        evidence_fresh=True,
        now=late,
    )
    assert wd.mode_diverged_nudges == 1
    assert not wd.escalated(now=late + CONV_FAIL_MIN_S - 60.0)


def test_clamped_device_episode_survives_throttled_ticks() -> None:
    """Own-context clamp coverage (C.8f): judged against the COMMAND baseline
    (``last_cmd_sp``, never re-baselined onto the device settle), a clamping
    device stays divergent — and a throttled tick without a write in between
    HOLDS the episode instead of resetting it. Judging against the adoption
    baseline made the counter oscillate 1->0->1 on self-regulating actuators
    (ADR-0052 §4 throttle), so the episode never reached the threshold."""
    wd = WriteConvergenceWatchdog()
    # Write tick: we commanded 22.0, the device clamps to its internal 18.0.
    wd.observe_setpoint(
        actual_sp=18.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=60.0,
    )
    assert wd.sp_diverged_writes == 1
    # Throttled tick (self-regulating device): no write, same clamp reported.
    wd.observe_setpoint(
        actual_sp=18.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=False,
        evidence_fresh=True,
        now=120.0,
    )
    assert wd.sp_diverged_writes == 1  # held, NOT reset
    # Next regulation period writes again -> the episode grows.
    wd.observe_setpoint(
        actual_sp=18.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=360.0,
    )
    assert wd.sp_diverged_writes == 2


def test_reset_clears_both_channels() -> None:
    # Disabled/off-hold/rescue path: without regulation there is no
    # convergence claim — the orchestrator ends both episodes.
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, CONV_FAIL_WRITES)
    _nudge(wd, CONV_FAIL_NUDGES)
    wd.reset()
    assert wd.sp_diverged_writes == 0
    assert wd.mode_diverged_nudges == 0
    assert not wd.escalated(now=1e9)


def test_non_monotonic_clock_reanchors() -> None:
    # F22 pattern: a clock step-back must re-anchor the episode start instead
    # of arming a premature escalation on the next forward jump.
    wd = WriteConvergenceWatchdog()
    _diverge_sp(wd, CONV_FAIL_WRITES, start=1000.0)
    wd.observe_setpoint(
        actual_sp=20.0,
        last_written_sp=22.0,
        tolerance=0.5,
        wrote=True,
        evidence_fresh=True,
        now=50.0,
    )
    # Anchor moved to 50.0: exactly CONV_FAIL_MIN_S later it may escalate,
    # not one tick earlier.
    assert not wd.escalated(now=50.0 + CONV_FAIL_MIN_S - 60.0)
    assert wd.escalated(now=50.0 + CONV_FAIL_MIN_S)
