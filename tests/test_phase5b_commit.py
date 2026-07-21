"""Phase-5B contract tests for the commit transport types (pure, no HA).

Plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md, Phase 5B.
``commit_execution`` itself is a TRANSITIONAL coordinator method (it moves to
``ZoneRuntime`` in phase 6) and therefore lives in ``coordinator.py``, which
imports Home Assistant — the actual attribute fold (attempt/success rules per
effect, ctx registration, EndHold teardown) is exercised end-to-end in
``tests/integration/test_phase5b_sequences.py``. THIS module pins everything
the pure py310 gate can construct: the report transport the fold relies on —

* the full 8-id effect vocabulary travels ordered and unaggregated,
* ``attempted=False`` transports a skipped/aborted planned effect
  (unavailable-safe abort, ext-feed settle skip),
* the mode-string/M2 transport added for 5B (``commanded_mode``,
  ``mode_changed``) and the per-effect ``commanded_value`` meaning,
* the ``EndHold`` post-action + ``CommitResult.events`` round trip.
"""

from __future__ import annotations

from custom_components.poise.runtime.tick_result import (
    CommitResult,
    EffectExecution,
    EndHold,
    ExecutionReport,
    ExternalTemperaturePlan,
    OverrideEnded,
    PostExecutionAction,
)

# The 5B effect vocabulary — one id per commit rule (plan 5B table; the
# rescue nudge is deliberately NOT the tick mode nudge: its ts stamp is
# unconditional while the tick nudge is M2-gated via ``mode_changed``).
EFFECT_IDS = (
    "mode_nudge",
    "setpoint_write",
    "ext_select",
    "ext_feed",
    "rescue_nudge",
    "rescue_write",
    "safe_mode",
    "safe_setpoint",
)


def _execution(
    effect_id: str,
    *,
    attempted: bool = True,
    success: bool = True,
    context_id: str | None = None,
    pre_write_value: float | None = None,
    commanded_value: float | None = None,
    commanded_mode: str | None = None,
    mode_changed: bool = False,
) -> EffectExecution:
    return EffectExecution(
        effect_id=effect_id,
        attempted=attempted,
        success=success,
        context_id=context_id,
        pre_write_value=pre_write_value,
        commanded_value=commanded_value,
        commanded_mode=commanded_mode,
        mode_changed=mode_changed,
    )


# ---------------------------------------------------------------------------
# Fold order: the report is the ORDER contract the commit folds by.
# ---------------------------------------------------------------------------


def test_report_preserves_full_vocabulary_in_call_order() -> None:
    # Befund 9: strictly ``for execution in report.executions`` — a report
    # carrying every 5B effect id in a deliberately jumbled order must come
    # back exactly as built (no grouping, no reordering, no dedup).
    jumbled = tuple(
        _execution(effect_id)
        for effect_id in (
            "rescue_write",
            "mode_nudge",
            "safe_setpoint",
            "ext_feed",
            "setpoint_write",
            "ext_select",
            "safe_mode",
            "rescue_nudge",
        )
    )
    report = ExecutionReport(executions=jumbled)
    assert report.executions == jumbled
    assert sorted(e.effect_id for e in report.executions) == sorted(EFFECT_IDS)


def test_report_keeps_same_effect_repeated_and_interleaved() -> None:
    # Order (not identity) is the contract: two writes to the same baseline
    # in different order mean different final state, so the transport must
    # keep duplicates positionally intact.
    first = _execution("setpoint_write", commanded_value=21.5)
    second = _execution("rescue_write", commanded_value=7.0)
    third = _execution("setpoint_write", commanded_value=19.0)
    report = ExecutionReport(executions=(first, second, third))
    assert [e.effect_id for e in report.executions] == [
        "setpoint_write",
        "rescue_write",
        "setpoint_write",
    ]
    assert [e.commanded_value for e in report.executions] == [21.5, 7.0, 19.0]


# ---------------------------------------------------------------------------
# Attempt/success transport: failure, abort and skip shapes.
# ---------------------------------------------------------------------------


def test_attempt_state_survives_a_failed_dispatch() -> None:
    # Phase-0 attempt_success Fall A: a synchronously failing setpoint write
    # still carries its attempt state (pre_write_value + context id) — the
    # commit registers EXACTLY this even though success stays False.
    failed = _execution(
        "setpoint_write",
        success=False,
        context_id="ctx-fail",
        pre_write_value=20.0,
        commanded_value=21.5,
        commanded_mode="heat",
    )
    assert failed.attempted is True
    assert failed.success is False
    assert failed.context_id == "ctx-fail"
    assert failed.pre_write_value == 20.0


def test_unavailable_safe_abort_shape() -> None:
    # ONE shared boundary: mode throw aborts the sequence — the planned
    # setpoint is reported attempted=False AFTER the failed mode, in order.
    report = ExecutionReport(
        executions=(
            _execution("safe_mode", success=False, commanded_mode="heat"),
            _execution(
                "safe_setpoint", attempted=False, success=False, commanded_value=7.0
            ),
        )
    )
    mode, setpoint = report.executions
    assert (mode.attempted, mode.success) == (True, False)
    assert (setpoint.attempted, setpoint.success) == (False, False)


def test_ext_feed_settle_skip_shape() -> None:
    # ADR-0029: select success skips the feed THIS tick — the plan's default
    # coupling flag encodes it, the report transports the skipped feed.
    plan = ExternalTemperaturePlan(select_external=True, feed_value=20.9)
    assert plan.skip_feed_on_select_success is True
    report = ExecutionReport(
        executions=(
            _execution("ext_select", success=True),
            _execution(
                "ext_feed",
                attempted=False,
                success=False,
                commanded_value=plan.feed_value,
            ),
        )
    )
    select, feed = report.executions
    assert select.success is True
    assert feed.attempted is False
    assert feed.commanded_value == 20.9


# ---------------------------------------------------------------------------
# 5B field transport: mode strings, M2 flag, commanded_value meanings.
# ---------------------------------------------------------------------------


def test_mode_transport_per_effect() -> None:
    # The four mode-stamping effects carry their mode STRING; only the tick
    # mode nudge carries a meaningful M2 flag.
    nudge = _execution("mode_nudge", commanded_mode="cool", mode_changed=True)
    setpoint = _execution("setpoint_write", commanded_value=21.5, commanded_mode="heat")
    safe = _execution("safe_mode", commanded_mode="off")
    rescue = _execution("rescue_nudge", commanded_mode="heat")
    assert nudge.commanded_mode == "cool"
    assert nudge.mode_changed is True
    assert (setpoint.commanded_mode, setpoint.commanded_value) == ("heat", 21.5)
    assert safe.commanded_mode == "off"
    # The rescue nudge never uses the M2 flag (unconditional ts commit rule).
    assert (rescue.commanded_mode, rescue.mode_changed) == ("heat", False)


def test_commanded_value_defaults_off_for_value_free_effects() -> None:
    # mode_nudge / ext_select / rescue_nudge / safe_mode carry no float value
    # and no pre-write value — the defaults must not force one.
    for effect_id in ("mode_nudge", "ext_select", "rescue_nudge", "safe_mode"):
        execution = _execution(effect_id)
        assert execution.commanded_value is None
        assert execution.pre_write_value is None


# ---------------------------------------------------------------------------
# Post-action round trip: EndHold in, OverrideEnded out.
# ---------------------------------------------------------------------------


def test_end_hold_post_action_round_trip() -> None:
    # Findings 6+9: the frost-rescue hold end is decoupled from write success
    # (require_success defaults False) and surfaces as CommitResult.events —
    # the adapter fires the bus event, never the commit.
    action = EndHold("frost_rescue")
    assert isinstance(action, PostExecutionAction)
    assert action.require_success is False
    result = CommitResult(events=(OverrideEnded(action.reason),))
    assert [event.reason for event in result.events] == ["frost_rescue"]


def test_commit_result_defaults_no_events() -> None:
    # Sites without post actions (all but frost rescue) commit to an empty
    # event tuple — nothing for the adapter to fire.
    assert CommitResult().events == ()


def test_post_actions_tuple_is_ordered() -> None:
    # post_actions apply AFTER the report fold, in order — the tuple is the
    # order contract (kept future-proof for more than one action).
    actions: tuple[PostExecutionAction, ...] = (
        EndHold("frost_rescue"),
        EndHold("user_resume", require_success=True),
    )
    assert [a.reason for a in actions if isinstance(a, EndHold)] == [
        "frost_rescue",
        "user_resume",
    ]


def test_effect_ids_are_distinct() -> None:
    # Eight distinct commit rules — an id collision would silently merge two
    # rules in the fold's dispatch.
    assert len(set(EFFECT_IDS)) == 8
