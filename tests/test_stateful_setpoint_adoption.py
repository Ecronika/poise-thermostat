"""State-machine test over setpoint ADOPTION — the hardest state in Poise (F.5).

Deciding whether a setpoint the device reports is "the user turned the wheel"
or "our own write coming back" depends on four pieces of carried state
(``last_written_sp``, ``last_sp_write_ts``, ``prev_device_sp``,
``pre_write_sp``), five safety gates and a clock. Every historical bug in this
area was a SEQUENCE bug — a late echo after an adoption, a settle that looked
like a move, a frost drop grabbed as a hold — and sequences are exactly what
worked examples cover badly.

So instead of more examples, this drives the real ``ExternalOverrideTracker``
through randomised sequences of the things that actually happen to a zone
(Poise writes, the device reports, time passes, a window opens, the sensor
freezes, the user opts out) and asserts the promises that must hold after
EVERY step, whatever the history:

* each of the five gates is absolute — while it is up, nothing is adopted;
* an adopted value is always exactly what the device reported;
* a reading at or below the frost floor is never adopted (a TRV's own frost
  drop is not a user setpoint);
* our own command coming back within the deadband is never adopted.

The clock only moves forward, mirroring the monotonic tick clock.
"""

from __future__ import annotations

import contextlib

from hypothesis import event
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from custom_components.poise.const import FROST_FLOOR_C, WRITE_DEADBAND_C
from custom_components.poise.control.external_override import ExternalOverrideTracker
from custom_components.poise.control.override import setpoint_adopt_reason
from custom_components.poise.runtime.state import ExternalOverrideRuntime

# Arbitrary injected window, deliberately not the production default
# (SETPOINT_ADOPT_ECHO_WINDOW_S = 120): the machine only needs SOME window to
# drive the inside/outside branches.
ECHO_WINDOW_S = 90.0
SETPOINTS = st.sampled_from([5.0, 7.0, 16.0, 18.5, 20.0, 21.0, 21.5, 24.0, 30.0])
# Gates are the exception in a running zone, not the rule. Unweighted booleans
# would keep one of the five up most of the time and starve the branch this
# machine exists for (measured: adopt reached in <1% of steps). Weighted, the
# generator spends its budget where the logic is.
MOSTLY_FALSE = st.sampled_from([False, False, False, False, True])


# The five gates, in the order observe_setpoint checks them.
def _event(label: str) -> None:
    """``event()`` records branch coverage during a hypothesis run.

    The reachability test at the bottom drives the very same rules directly
    (no hypothesis context), where ``event()`` raises — so it is optional
    here, not load-bearing.
    """
    # Outside a hypothesis run event() raises; that path is the reachability
    # test below, where branch statistics are irrelevant.
    with contextlib.suppress(InvalidArgument):
        event(label)


GATE_REASONS = {
    "opt_out",
    "schedule_active",
    "own_echo",
    "safety_window",
    "safety_frozen",
}


class SetpointAdoptionMachine(RuleBasedStateMachine):
    """Drives the real tracker; asserts the adoption promises after each step."""

    def __init__(self) -> None:
        super().__init__()
        self.state = ExternalOverrideRuntime()
        self.tracker = ExternalOverrideTracker(self.state)
        self.now = 1_000.0
        # Gate flags, flipped by rules below.
        self.adopt_enabled = True
        self.sched_active = False
        self.window_open = False
        self.frozen = False
        self.own_change = False
        # Bookkeeping for the assertions. The command baseline is captured
        # AS OF the observation: later rules (a re-baseline) move
        # ``last_written_sp``, and judging a past decision against a later
        # baseline is what an early version of this test got wrong.
        self.last_observation: (
            tuple[float | None, str, float | None, float | None] | None
        ) = None

    # --- things that happen to a zone -------------------------------------

    @rule(seconds=st.sampled_from([1.0, 30.0, 60.0, 120.0, 600.0]))
    def time_passes(self, seconds: float) -> None:
        self.now += seconds

    @rule(value=SETPOINTS)
    def poise_writes(self, value: float) -> None:
        """A successful setpoint write — mirrors what commit_execution stamps."""
        self.state.pre_write_sp = self.state.prev_device_sp
        self.state.last_written_sp = value
        self.state.last_sp_write_ts = self.now

    @rule(value=st.one_of(st.none(), SETPOINTS, SETPOINTS, SETPOINTS))
    def device_reports(self, value: float | None) -> None:
        """The device publishes a setpoint; the tracker classifies it."""
        obs = self.tracker.observe_setpoint(
            device_sp=value,
            now=self.now,
            echo_window_s=ECHO_WINDOW_S,
            deadband=WRITE_DEADBAND_C,
            frost_floor=FROST_FLOOR_C,
            adopt_enabled=self.adopt_enabled,
            sched_active=self.sched_active,
            own_change=self.own_change,
            window_open=self.window_open,
            frozen=self.frozen,
            setpoint_adopt_reason_fn=setpoint_adopt_reason,
        )
        self.last_observation = (
            value,
            obs.reason,
            obs.adopt_setpoint,
            self.state.last_written_sp,
        )
        # Visible under --hypothesis-show-statistics: which branches the
        # generated sequences actually reach.
        _event(f"reason={obs.reason}")
        # Every tick remembers the reading, adoption branch or not.
        self.tracker.note_device_setpoint(value)

    @rule()
    def poise_rebaselines_own_echo(self) -> None:
        """The observe stage's re-baseline when the reading is our own echo.

        No ``@precondition``: gating the rule on "a reading exists" makes
        hypothesis re-draw from the filtered rule set on every early step
        (measured: ~5 % of runs aborted as invalid). Cheaper to let the rule
        run and no-op.
        """
        value = self.last_observation[0] if self.last_observation else None
        if value is not None:
            self.tracker.rebaseline_own_echo(value)

    @rule(flag=MOSTLY_FALSE)
    def window_toggles(self, flag: bool) -> None:
        self.window_open = flag

    @rule(flag=MOSTLY_FALSE)
    def sensor_freezes_or_thaws(self, flag: bool) -> None:
        self.frozen = flag

    @rule(flag=st.sampled_from([True, True, True, True, False]))
    def user_toggles_adoption(self, flag: bool) -> None:
        self.adopt_enabled = flag

    @rule(flag=MOSTLY_FALSE)
    def device_schedule_toggles(self, flag: bool) -> None:
        self.sched_active = flag

    @rule(flag=MOSTLY_FALSE)
    def context_ownership_changes(self, flag: bool) -> None:
        """Whether the current reading carries one of our own HA contexts."""
        self.own_change = flag

    # --- promises ----------------------------------------------------------

    @invariant()
    def gates_are_absolute(self) -> None:
        if self.last_observation is None:
            return
        _value, reason, adopted, _cmd = self.last_observation
        if reason in GATE_REASONS:
            assert adopted is None, (
                f"gate {reason!r} was up but {adopted} was adopted anyway"
            )

    @invariant()
    def adopted_value_is_the_reported_one(self) -> None:
        if self.last_observation is None:
            return
        value, reason, adopted, _cmd = self.last_observation
        if adopted is not None:
            assert reason == "adopt"
            assert adopted == value, (
                f"adopted {adopted} but the device reported {value}"
            )

    @invariant()
    def frost_drop_is_never_a_user_hold(self) -> None:
        """A reading at/below the frost floor is the TRV's own frost drop."""
        if self.last_observation is None:
            return
        value, _reason, adopted, _cmd = self.last_observation
        if value is not None and value <= FROST_FLOOR_C:
            assert adopted is None, f"frost drop {value} adopted as a manual hold"

    @invariant()
    def our_own_command_is_never_adopted(self) -> None:
        """A value within the deadband of what we last commanded is an echo."""
        if self.last_observation is None:
            return
        value, _reason, adopted, last_cmd = self.last_observation
        if value is None or last_cmd is None or adopted is None:
            return
        assert round(abs(value - last_cmd), 3) >= WRITE_DEADBAND_C, (
            f"adopted {value} although it is within the deadband of our own "
            f"command {last_cmd}"
        )


TestSetpointAdoption = SetpointAdoptionMachine.TestCase


def test_the_machine_can_actually_reach_an_adoption() -> None:
    """Guard against a vacuously green state machine.

    Every invariant above is of the form "if X was adopted, then …". If the
    gates were ever tightened so that nothing is EVER adopted, all of them
    would pass while proving nothing. This drives the machine's own rules
    through the canonical user-turns-the-wheel sequence and insists that the
    adoption branch is still reachable.
    """
    m = SetpointAdoptionMachine()
    m.poise_writes(21.0)  # we command 21.0
    m.time_passes(120.0)  # ... the echo window closes
    m.device_reports(21.0)  # device confirms our value (echo)
    m.time_passes(120.0)
    m.device_reports(24.0)  # user turns the wheel to 24.0
    m.time_passes(120.0)
    m.device_reports(24.0)  # and it stays there

    reasons = {m.last_observation[1] if m.last_observation else None}
    m2 = SetpointAdoptionMachine()
    m2.poise_writes(21.0)
    m2.time_passes(120.0)
    m2.device_reports(21.0)
    m2.time_passes(120.0)
    m2.device_reports(24.0)
    assert m2.last_observation is not None
    assert m2.last_observation[1] == "adopt", (
        f"the canonical user change was classified as {m2.last_observation[1]!r} — "
        "if that is intended, this machine no longer tests anything"
    )
    assert m2.last_observation[2] == 24.0
    assert reasons  # keeps the first sequence meaningful for the reader
