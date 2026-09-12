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
# Two setpoint reads count as the same value below this (0.1 grid + float
# hygiene, the same rounding the write gate uses).
_SAME_VALUE_EPS: Final = 0.05

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
    settle_min_s: float = EPISODE_SETTLE_MIN_S,
    liveness_s: float = REASSERT_LIVENESS_S,
) -> bool:
    """True when re-sending the command in force cannot change anything.

    Every condition is necessary; the order is cheapest-first.

    1. the target IS the command in force (a changed target is a new episode),
    2. an episode is running and the device had time to react,
    3. the device has come to rest (two identical readings),
    4. the reading is positively classified (:data:`RELEASING`),
    5. the liveness escape has not expired.

    Deliberately NOT a statement about the device being healthy — see
    :mod:`custom_components.poise.safety.write_convergence`. A suppressed
    re-assert must be folded into that watchdog as divergence evidence, or the
    detector for "device never applies our commands" goes blind (T2).
    """
    if last_cmd_sp is None or not _same(target_snapped, last_cmd_sp):
        return False
    if cmd_episode_ts is None or (now - cmd_episode_ts) < settle_min_s:
        return False
    if actual_sp is None or not _same(actual_sp, prev_device_sp):
        return False  # still moving, or unreadable -> the premise is void
    if provenance not in RELEASING:
        return False
    if last_sp_write_ts is not None and (now - last_sp_write_ts) >= liveness_s:
        return False  # V3: let one write through, the commit re-stamps the clock
    return True
