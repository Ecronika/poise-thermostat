"""Plan O.6: the outcome-diag folds live inside ONE boundary — the proof that
splitting them into methods did not move it.

``ReportPhase._stage_outcome_diag`` has exactly ONE error boundary,
``DiagnosticsCollector.safe_collect``. Inside the closure handed to that
boundary the state folds plus the assembly run in text order, so a failure in
fold N has a very specific, observable shape:

    (a) the stage returns the DEFAULTS (the seven-key degraded payload),
    (b) the folds BEFORE N have already written their state,
    (c) the folds AFTER N never run at all.

O.6 turned those folds into methods called from INSIDE that same closure, in
unchanged text order. These tests are the proof that the boundary did not
travel with them: they inject a fault into every fold and pin (a)-(c).

Why this is an equivalence proof and not a description of the new code: every
injection point is a collaborator the stage calls in BOTH versions
(``observe_session``, ``ca_tick_scorable``, ``flip_metric_ok``, the
``climate_diag["fan_ce_k"]`` read, ``update_offset``, ``update_settle``), and
every assertion is about runtime state and the returned payload, never about
the fold methods. The file was written against the pre-O.6 code, run there
first, and is green on both sides.

The decidability trick: each fold writes state nothing else in the stage
writes — five of them a monotonic anchor (``*_last_mono``), the sixth the two
``PipelineLatches`` solver inputs (seeded to a sentinel here, since 0.0 is a
legitimate result). "This fold ran" is therefore a value comparison, not an
inspection of the accumulators.

SIX folds, not five: the plan (and the collector's own docstring) said "five",
naming HDH, outcome session/stats, CA regulation quality, reference offset and
tau settle. That list predates the ADR-0055 N1 PPD fold and the ADR-0069
U7/U8 tier-2 folds. Measured against the code the closure holds six separable
state folds, and the tier-2 block only fits the plan's 80-code-line per-fold
cap when its two halves (latch stepping vs. next-tick solver inputs — which
write different state groups) are separate.

``test_swallowed_traceback_frames_...`` is the one thing that legitimately
differs (plan §4.1a): the extraction inserts exactly one stack frame per fold
into the swallowed DEBUG traceback. Exception class, exception text, log
channel, log level and the location of the boundary itself are pinned
unchanged next to it.

An HA-runtime file only because ``ha/phase_report.py`` imports
``homeassistant.util.dt``; nothing here needs a ``hass``.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, fields
from typing import Any, cast

import pytest

from custom_components.poise.clock import ManualClock
from custom_components.poise.comfort.dual_setpoint import ComfortDecision
from custom_components.poise.comfort.schedule import ScheduleState
from custom_components.poise.contracts import Source
from custom_components.poise.diagnostics.collector import DiagnosticsCollector
from custom_components.poise.ha import phase_report
from custom_components.poise.ha.phase_report import ReportPhase
from custom_components.poise.ha.tick_snapshot import TickConfigSnapshot
from custom_components.poise.runtime.config import ZoneTuning
from custom_components.poise.runtime.tick_result import FinalizeContext
from custom_components.poise.runtime.zone_runtime import ZoneRuntime

CHANNEL = "custom_components.poise.coordinator"
NOW = 10_000.0
SWALLOW_TEXT = "Poise outcome/savings diagnostics failed"
# Fold 6 writes plain floats whose natural value is 0.0, which is also their
# default — so the latches are seeded away from every value the fold can
# produce and "still the sentinel" means "the fold never ran".
SENTINEL = -1.0

# The degraded payload ``_stage_outcome_diag`` hands to ``safe_collect`` as its
# defaults — the second observable key-shrink mechanism (phase-0 finding 3).
DEFAULTS: dict[str, Any] = {
    "outcome_last_score": None,
    "outcome_ts_avg": None,
    "outcome_obs_avg": None,
    "outcome_n": 0,
    "savings_kwh_month": 0.0,
    "savings_eur_month": 0.0,
    "savings_pct": 0.0,
}

# The per-fold witnesses, in text order. ``ca``/``ppd`` are the two halves of
# the regulation-quality fold; they share a fold but keep separate anchors.
WITNESSES = ("hdh", "ca", "ppd", "tier2", "solver-inputs", "ref", "tau")


class InjectedFoldFailure(RuntimeError):
    """The injected fault — a plain ``RuntimeError`` subclass, so class, args
    and text are trivially comparable across the refactor."""


def _raise_injected(*_args: object, **_kwargs: object) -> Any:
    """Module-level so its NAME is the innermost traceback frame."""
    raise InjectedFoldFailure("injected fold failure")


class _ClimateDiag(dict[str, Any]):
    """A ``climate_diag`` mapping whose ``.get`` raises for ONE key.

    Fold 4 (the tier-2 solver inputs) has no collaborator of its own that a
    cold zone is guaranteed to reach — ``pmv_setpoint_offset`` only runs once
    the pmv_offset latch is live. Its fault is therefore injected at its very
    first statement instead, the ``climate_diag.get("fan_ce_k")`` read, which
    is the same statement in both versions of the code.
    """

    def __init__(self, data: dict[str, Any], raise_key: str = "") -> None:
        super().__init__(data)
        self.raise_key = raise_key

    def get(self, key: str, default: Any = None) -> Any:  # noqa: D102
        if key and key == self.raise_key:
            raise InjectedFoldFailure("injected fold failure")
        return super().get(key, default)


@dataclass(frozen=True)
class _FoldCase:
    """One fold: where the fault goes in, and the witness picture it leaves.

    ``expected`` is the full "did this fold write its state" picture after the
    failure — ``True`` up to the fault, ``False`` after it. It encodes (b) and
    (c) together, INCLUDING the partial progress inside the failing fold,
    which is itself evidence that the boundary sits around the whole closure
    and not around each fold.

    Exactly one of ``patch``/``raise_on_key`` is set: the first patches a
    module-level collaborator, the second makes the ctx's ``climate_diag``
    raise on one key.
    """

    fold: str
    frame: str
    expected: tuple[bool, ...]
    patch: str = ""
    raise_on_key: str = ""
    innermost: str = "_raise_injected"


T, F = True, False

# Injection points are the earliest collaborator unique to each fold, so the
# fault lands as close to the fold's start as the code allows.
FOLD_CASES: tuple[_FoldCase, ...] = (
    _FoldCase(
        fold="1 hdh+outcome",
        patch="observe_session",
        frame="_fold_hdh_and_outcome",
        # The HDH half already stamped its anchor; nothing after it ran.
        expected=(T, F, F, F, F, F, F),
    ),
    _FoldCase(
        fold="2 regulation-quality",
        patch="ca_tick_scorable",
        frame="_fold_regulation_quality",
        # ``ca_tick_scorable`` sits in the ENTRY GATE, before the CA anchor is
        # stamped: fold 2 leaves no trace at all, fold 1 keeps its own.
        expected=(T, F, F, F, F, F, F),
    ),
    _FoldCase(
        fold="3 tier2-activation",
        patch="flip_metric_ok",
        frame="_fold_tier2_activation",
        expected=(T, T, T, T, F, F, F),
    ),
    _FoldCase(
        fold="4 tier2-solver-inputs",
        raise_on_key="fan_ce_k",
        frame="_fold_tier2_inputs",
        innermost="get",
        expected=(T, T, T, T, F, F, F),
    ),
    _FoldCase(
        fold="5 reference-offset",
        patch="update_offset",
        frame="_fold_reference_offset",
        expected=(T, T, T, T, T, T, F),
    ),
    _FoldCase(
        fold="6 tau-settle",
        patch="update_settle",
        frame="_fold_tau_settle",
        expected=(T, T, T, T, T, T, T),
    ),
)

# Which accumulators each case's SKIPPED folds own. The anchors prove the
# folds did not stamp their clocks; these prove they did not fold either.
SKIPPED_ACCUMULATORS: dict[str, tuple[str, ...]] = {
    "1 hdh+outcome": ("regq", "comfort_activation", "ref_offset", "tau_settle"),
    "2 regulation-quality": ("regq", "comfort_activation", "ref_offset", "tau_settle"),
    "3 tier2-activation": ("ref_offset", "tau_settle"),
    "4 tier2-solver-inputs": ("ref_offset", "tau_settle"),
    "5 reference-offset": ("ref_offset", "tau_settle"),
    "6 tau-settle": ("tau_settle",),
}
_LEARNING_ACCUMULATORS = ("ref_offset", "tau_settle")


def _config() -> TickConfigSnapshot:
    """A value-realistic config view built from the parser's own defaults."""
    tuning = ZoneTuning.from_merged({})
    return TickConfigSnapshot(
        **{f.name: getattr(tuning, f.name) for f in fields(TickConfigSnapshot)}
    )


def _ctx(raise_on_key: str = "") -> FinalizeContext:
    """A finalize context that lets EVERY fold do work.

    The CA and PPD gates are open (enabled zone, comfort schedule, no
    window/frost mask, valid PMV with a numeric PPD), so a fold that did not
    run did not run because of the injected fault.
    """
    return FinalizeContext(
        config=_config(),
        now=NOW,
        room=20.0,
        room_decide=20.0,
        reading_source=Source.MEASURED,
        rh=45.0,
        dewpoint=8.0,
        mold_min=None,
        mold_capped=False,
        t_out_eff=4.0,
        t_rm_eff=12.0,
        t_rm_source="sensor",
        q_solar=0.0,
        q_solar_source="none",
        q_solar_internal=0.0,
        t_mrt=20.0,
        mrt_source="air",
        mrt_internal=20.0,
        sched=ScheduleState(is_comfort=True, minutes_to_comfort=0, setback_offset=0.0),
        frozen=False,
        window_open=False,
        decision=ComfortDecision(
            heat_sp=21.0, cool_sp=25.0, mode="heat", write_setpoint=21.0, target=21.0
        ),
        eff_cool=25.0,
        mode="heat",
        target=21.0,
        final_mode="heat",
        norm_binding=None,
        binding_precedence=None,
        override_clamped=False,
        heating=True,
        cooling=False,
        failed=False,
        adaptive_cool=False,
        preheating=False,
        preheat_outdoor=None,
        coasting=False,
        act_state=None,
        guard_pol=None,
        g_min_off=0.0,
        g_mode_hold=0.0,
        guard_block=None,
        mode_nudge_blocked="",
        idle_park_mode=None,
        mode_adopt_reason="",
        sp_adopt_reason="",
        climate_diag=_ClimateDiag(
            {
                "ppd": 12.0,
                "pmv_valid": True,
                "pmv": 0.3,
                "fan_ce_k": 0.2,
                "fan_circ_reason": "",
            },
            raise_on_key,
        ),
        sched_active=False,
        fault_active=False,
        heat_source_suspect=False,
        ext_num=None,
        operative_active=False,
        occupancy=(True,),
    )


def _phase() -> tuple[ReportPhase, ZoneRuntime]:
    runtime = ZoneRuntime(ManualClock(NOW))
    runtime.latches.fan_ce_credit_k = SENTINEL
    runtime.latches.pmv_offset_k = SENTINEL
    phase = ReportPhase(
        runtime=runtime,
        reader=cast(Any, None),  # untouched by _stage_outcome_diag
        diag=DiagnosticsCollector(logging.getLogger(CHANNEL)),
        ports=cast(Any, None),  # untouched by _stage_outcome_diag
        logger=logging.getLogger(CHANNEL),
    )
    return phase, runtime


def _folds_that_ran(runtime: ZoneRuntime) -> tuple[bool, ...]:
    """One boolean per witness, in text order — see ``WITNESSES``."""
    diag, learn, latch = runtime.diagnostics, runtime.learning, runtime.latches
    return (
        diag.hdh_last_mono is not None,
        diag.ca_last_mono is not None,
        diag.ppd_last_mono is not None,
        diag.tier2_last_mono is not None,
        (latch.fan_ce_credit_k, latch.pmv_offset_k) != (SENTINEL, SENTINEL),
        learn.ref_last_mono is not None,
        learn.tau_last_mono is not None,
    )


def _apply(case: _FoldCase, monkeypatch: pytest.MonkeyPatch) -> FinalizeContext:
    """Arm the case's fault and hand back the context to run the stage with."""
    assert bool(case.patch) != bool(case.raise_on_key), "exactly one injection"
    if case.patch:
        monkeypatch.setattr(phase_report, case.patch, _raise_injected)
    return _ctx(case.raise_on_key)


def _swallow_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == SWALLOW_TEXT]


# ---------------------------------------------------------------------------
# anti-vacuum control: the healthy tick really does run every fold
# ---------------------------------------------------------------------------


def test_healthy_tick_runs_every_fold_and_replaces_the_defaults(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without an injected fault every witness fires and the payload is the
    FULL collected key set, not the defaults.

    Without this control the degradation tests below could all pass on a stage
    that never reaches a single fold. It also pins that the five monotonic
    anchors are stamped with THIS tick's clock, not with some other value.
    """
    phase, runtime = _phase()
    assert _folds_that_ran(runtime) == (False,) * len(WITNESSES)

    with caplog.at_level(logging.DEBUG, logger=CHANNEL):
        result = phase._stage_outcome_diag(_ctx())

    assert _folds_that_ran(runtime) == (True,) * len(WITNESSES)
    assert runtime.diagnostics.hdh_last_mono == NOW
    assert runtime.diagnostics.ca_last_mono == NOW
    assert runtime.diagnostics.ppd_last_mono == NOW
    assert runtime.diagnostics.tier2_last_mono == NOW
    assert runtime.learning.ref_last_mono == NOW
    assert runtime.learning.tau_last_mono == NOW
    assert not _swallow_records(caplog)
    assert set(DEFAULTS) < set(result), "the healthy payload must be a superset"
    assert "ca_minutes" in result and "tau_confidence" in result


# ---------------------------------------------------------------------------
# the proof: a fault in fold N degrades exactly the way it did before O.6
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", FOLD_CASES, ids=[c.fold for c in FOLD_CASES])
def test_fault_in_fold_n_keeps_the_defaults_and_the_partial_state(
    case: _FoldCase, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """(a) defaults returned, (b) folds before N applied, (c) folds after N
    skipped — for every fold.

    This is THE O.6 assertion. Had the boundary been duplicated per fold, (a)
    would break: the later folds would still run and the assembly would return
    a full payload. Had it moved outward, (b) would break: nothing would be
    swallowed here and the exception would leave the stage.
    """
    phase, runtime = _phase()
    ctx = _apply(case, monkeypatch)

    with caplog.at_level(logging.DEBUG, logger=CHANNEL):
        result = phase._stage_outcome_diag(ctx)

    # (a) the degraded payload, key for key.
    assert result == DEFAULTS
    # (b) + (c) written before the fault, untouched after it.
    assert _folds_that_ran(runtime) == case.expected
    # The one swallow record — every field §4.1a calls behaviour, unchanged.
    records = _swallow_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].name == CHANNEL
    assert records[0].exc_info is not None
    exc = records[0].exc_info[1]
    assert type(exc) is InjectedFoldFailure
    assert str(exc) == "injected fold failure"


@pytest.mark.parametrize("case", FOLD_CASES, ids=[c.fold for c in FOLD_CASES])
def test_state_after_the_failing_fold_is_untouched_by_object_identity(
    case: _FoldCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(c), sharpened: the accumulators the skipped folds own are the SAME
    OBJECTS afterwards.

    Every accumulator in this stage is REPLACED (``x = x.observe(...)``),
    never mutated in place, so identity is exactly the right question.
    """
    phase, runtime = _phase()
    before = {
        "regq": runtime.diagnostics.regq,
        "comfort_activation": runtime.diagnostics.comfort_activation,
        "ref_offset": runtime.learning.ref_offset,
        "tau_settle": runtime.learning.tau_settle,
    }
    ctx = _apply(case, monkeypatch)

    phase._stage_outcome_diag(ctx)

    for name in SKIPPED_ACCUMULATORS[case.fold]:
        group = (
            runtime.learning if name in _LEARNING_ACCUMULATORS else runtime.diagnostics
        )
        assert getattr(group, name) is before[name], (
            f"{name} advanced although fold {case.fold} failed"
        )


# ---------------------------------------------------------------------------
# plan §4.1a: the ONE accepted, non-functional difference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", FOLD_CASES, ids=[c.fold for c in FOLD_CASES])
def test_swallowed_traceback_frames_are_the_only_difference(
    case: _FoldCase, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The swallowed DEBUG traceback gains exactly ONE frame per fold.

    ``exc_info=True`` renders the EXCEPTION traceback, which begins at the
    frame holding the ``try`` — ``DiagnosticsCollector.safe_collect``. Before
    O.6 the list was::

        safe_collect -> _collect_outcome_diag -> <raiser>            (3)

    and after the split it is::

        safe_collect -> _collect_outcome_diag -> _fold_x -> <raiser>  (4)

    Frame 0 is the assertion that matters: the boundary is still located in
    ``safe_collect`` — it neither moved nor multiplied. Everything else §4.1a
    names as behaviour (class, text, channel, level) is pinned in the
    degradation test above.

    This is the one test in this file that does NOT pass against the pre-O.6
    code: it measures the change instead of asserting the equivalence.
    """
    phase, _runtime = _phase()
    ctx = _apply(case, monkeypatch)

    with caplog.at_level(logging.DEBUG, logger=CHANNEL):
        phase._stage_outcome_diag(ctx)

    (record,) = _swallow_records(caplog)
    assert record.exc_info is not None
    frames = [f.name for f in traceback.extract_tb(record.exc_info[2])]
    assert frames == [
        "safe_collect",
        "_collect_outcome_diag",
        case.frame,
        case.innermost,
    ]
