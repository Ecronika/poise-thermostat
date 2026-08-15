"""Write-convergence watchdog (review C.8, ADR-0012 family).

Poise dispatches actuator writes fire-and-forget (``blocking=False`` is the
executor's contract) and re-asserts per tick against the device's *real*
state. A device that silently never applies our commands therefore produces
**sub-threshold divergence**: permanent re-assert traffic with no user-visible
signal as long as the room stays outside the heating-failure window. This
watchdog counts that traffic and escalates it into a repair issue.

Deliberately only two observable stages (review R1c): *dispatch accepted*
(today's ``EffectExecution.success``) and *state converged* (this watchdog).
A middle ``service_completed`` stage is unobservable under ``blocking=False``
— HA neither returns the handler task nor propagates handler exceptions — so
it is not modelled.

Evidence rules (per tick, adversarial-review hardened):

* Only a FRESH device state is evidence (``evidence_fresh``: the state
  updated after our last command on that channel). A state the integration
  has not refreshed since the write can neither prove the device ignored the
  command (poll latency) nor that it applied it (frozen own-context echo) —
  stale ticks hold the episode unchanged.
* Setpoint: judged against the **last commanded (snapped)** value,
  pre-commit. Settling within one tolerance INCLUSIVE reads as converged —
  exactly one tolerance is the canonical re-quantise distance (truncating
  0.5-grid, banker's-rounded 1.0-grid) and must never read as divergence.
  The tolerance is ``convergence_tolerance(step)`` (floored at 0.5 K so a
  missing ``target_temp_step`` cannot sharpen it below a plausible grid).
  A tick that writes while the previous command still diverges increments;
  a tick with no write and no convergence (throttle, adoption, off-hold)
  is no evidence.
* Mode: only an identical re-nudge (``desired == last_commanded_hvac`` at
  dispatch time, i.e. ``mode_changed=False``) counts — a nudge to a *new*
  mode is a fresh command and ends the episode. The device reaching the
  desired mode clears it; unknown/unsupported device modes are no evidence.
* Episodes EXPIRE: a gap of ``CONV_EVIDENCE_TTL_S`` without any evidence on
  a channel ends its episode. Otherwise a stale count (seasonal idle, long
  unavailable, replaced device behind a persisted baseline) would merge with
  fresh counts and fire the issue on the first write of a healthy restart —
  inverting the ``CONV_FAIL_MIN_S`` protection.

Escalation needs BOTH a count and a minimum elapsed time since the episode
began, so slow-reporting/poll integrations cannot false-positive. Transient
by design: like the failure detectors, the watchdog re-arms from live
observations after a restart.

Own-context clamp coverage (C.8f): a device that clamps our write to an
unannounced internal limit and reports the settle under OUR service context
is re-baselined by the adoption logic (``rebaseline_own_echo``) — that
baseline must therefore never be the judge. The fold instead uses
``ExternalOverrideRuntime.last_cmd_sp``: stamped by the commit, never
re-baselined, so the clamp reads as the divergence it is, and a throttled
tick in between holds the episode instead of resetting it. A late echo of a
SUPERSEDED command (the context ring is shared with the mode/fan channels)
is flagged ``stale_own_echo`` upstream and carries no evidence. A truly
frozen own-context state (HA state dedup: identical echoes produce no state
change) stays no-evidence by design; real divergence there surfaces through
the foreign-context updates the integration keeps publishing.
"""

from __future__ import annotations

from dataclasses import dataclass

CONV_FAIL_WRITES: int = 5  # consecutive unconverged setpoint re-asserts
CONV_FAIL_NUDGES: int = 5  # consecutive identical mode re-nudges
CONV_FAIL_MIN_S: float = 600.0  # AND at least this long since the episode began
# An evidence-free gap this long ends the episode (real divergence produces
# evidence at least once per regulation period, well below this).
CONV_EVIDENCE_TTL_S: float = 3600.0
# The tolerance floor: never judge convergence sharper than half a Kelvin —
# the step read falls back to 0.1 when the device does not announce one.
CONV_MIN_TOLERANCE_C: float = 0.5


def convergence_tolerance(step: float) -> float:
    """The convergence judgement tolerance for a device step (floored)."""
    return max(CONV_MIN_TOLERANCE_C, step)


@dataclass(slots=True)
class WriteConvergenceWatchdog:
    """Counts unconverged re-asserts/re-nudges; pure, monotonic-clock based."""

    sp_diverged_writes: int = 0
    sp_diverged_since: float | None = None
    sp_last_evidence: float | None = None
    mode_diverged_nudges: int = 0
    mode_diverged_since: float | None = None
    mode_last_evidence: float | None = None

    def _expire_sp(self, now: float) -> None:
        # F22: tolerate a non-monotonic clock — re-anchor instead of letting a
        # stale anchor fire the elapsed guard prematurely on a forward jump.
        if self.sp_diverged_since is not None and now < self.sp_diverged_since:
            self.sp_diverged_since = now
        if self.sp_last_evidence is not None and now < self.sp_last_evidence:
            self.sp_last_evidence = now
        if (
            self.sp_last_evidence is not None
            and (now - self.sp_last_evidence) > CONV_EVIDENCE_TTL_S
        ):
            self.sp_diverged_writes = 0
            self.sp_diverged_since = None
            self.sp_last_evidence = None

    def _expire_mode(self, now: float) -> None:
        if self.mode_diverged_since is not None and now < self.mode_diverged_since:
            self.mode_diverged_since = now
        if self.mode_last_evidence is not None and now < self.mode_last_evidence:
            self.mode_last_evidence = now
        if (
            self.mode_last_evidence is not None
            and (now - self.mode_last_evidence) > CONV_EVIDENCE_TTL_S
        ):
            self.mode_diverged_nudges = 0
            self.mode_diverged_since = None
            self.mode_last_evidence = None

    def observe_setpoint(
        self,
        *,
        actual_sp: float | None,
        last_written_sp: float | None,
        tolerance: float,
        wrote: bool,
        evidence_fresh: bool,
        now: float,
    ) -> None:
        """Fold one tick's setpoint evidence.

        ``last_written_sp`` is the PRE-commit COMMAND baseline
        (``ExternalOverrideRuntime.last_cmd_sp``) — the value we asked the
        device for, never the adoption baseline, which follows the device's
        own settle and would report a clamping device as converged.
        """
        self._expire_sp(now)
        if actual_sp is None or last_written_sp is None or not evidence_fresh:
            return  # unobservable/stale — no evidence either way
        # Same float hygiene as should_write: setpoints are 0.1-resolution.
        if round(abs(actual_sp - last_written_sp), 3) <= tolerance:
            self.sp_diverged_writes = 0
            self.sp_diverged_since = None
            self.sp_last_evidence = None
        elif wrote:
            self.sp_diverged_writes += 1
            self.sp_last_evidence = now
            if self.sp_diverged_since is None:
                self.sp_diverged_since = now
        # else: diverged but nothing written (throttle/adoption/off-hold) —
        # no new evidence, hold the episode (the TTL above bounds the hold).

    def observe_mode(
        self,
        *,
        nudged: bool,
        re_nudge: bool,
        current_matches_desired: bool,
        evidence_fresh: bool,
        now: float,
    ) -> None:
        """Fold one tick's mode evidence (see the module evidence rules)."""
        self._expire_mode(now)
        if not evidence_fresh:
            return  # stale device state — no evidence either way
        if current_matches_desired:
            self.mode_diverged_nudges = 0
            self.mode_diverged_since = None
            self.mode_last_evidence = None
        elif nudged and re_nudge:
            self.mode_diverged_nudges += 1
            self.mode_last_evidence = now
            if self.mode_diverged_since is None:
                self.mode_diverged_since = now
        elif nudged:
            # Fresh command (new desired mode): the old episode's evidence no
            # longer applies; divergence of the NEW command starts at zero.
            self.mode_diverged_nudges = 0
            self.mode_diverged_since = None
            self.mode_last_evidence = None
        # else: no nudge and no match (unknown/unsupported) — no evidence.

    def reset(self) -> None:
        """End both episodes (disabled/off-hold/rescue path: without
        regulation there is no convergence claim; re-arms from fresh
        evidence after re-enable)."""
        self.sp_diverged_writes = 0
        self.sp_diverged_since = None
        self.sp_last_evidence = None
        self.mode_diverged_nudges = 0
        self.mode_diverged_since = None
        self.mode_last_evidence = None

    def escalated(self, *, now: float) -> bool:
        """True when either channel exceeds count AND minimum elapsed time."""
        sp = (
            self.sp_diverged_writes >= CONV_FAIL_WRITES
            and self.sp_diverged_since is not None
            and (now - self.sp_diverged_since) >= CONV_FAIL_MIN_S
        )
        mode = (
            self.mode_diverged_nudges >= CONV_FAIL_NUDGES
            and self.mode_diverged_since is not None
            and (now - self.mode_diverged_since) >= CONV_FAIL_MIN_S
        )
        return sp or mode
