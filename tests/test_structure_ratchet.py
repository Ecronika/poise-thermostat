"""Size ratchet: the growth band, the DoD cap and the extraction budget.

One of six structure gates (plan S.2); the shared measurement lives in
``structure_support``. Rationale and full spec:
``docs/Konzepte/2026-08-16_Refactoring-Plan_tick-orchestrator.md``, section
"O.0 - Structure Ratchet". Two independent rules per row:

    (1) Architektur-Deckel  - one-sided, only ever drops:  ist <= ceiling
    (2) Ratchet-Baseline    - tracks reality:               ist >= baseline - H

One sanctioned exception exists, the EXTRACTION BUDGET: a step that pulls code
out of a method into a new method *inside the same file* necessarily adds
signature, result-construction and import lines. Instead of raising the
ceiling - which would destroy its one-way property - a row may declare a
bounded budget with a reason and an expiry step, and
``test_extraction_budget_is_declared_and_expires`` fails the suite once that
step is reached and the budget is still there.

Since S.2 the table also measures THIS gate and its five siblings: a checker
exempt from its own check is how a 2270-line test file grows unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests.structure_support import (
    _ACTIVE_STEPS,
    _CURRENT_STEP,
    _STEP_ORDER,
    _measure,
)

# --- the ratchet table (plan O.0 table, section 6) --------------------------


@dataclass(frozen=True)
class _Entry:
    """One row of the structure-ratchet table.

    ``identifier`` is a repo-relative path, optionally with ``::method_name``
    for a single-method measurement.

    The allowed band around ``baseline_*`` is DELIBERATELY ASYMMETRIC, because
    growing and shrinking are not the same event:

    * upward, ``grow_slack`` (small): room for a comment or a reflowed
      signature, not for a feature. Exceeding it is the alarm this table
      exists for.
    * downward, ``headroom`` (larger): a shrink is good news, but the table
      must be pulled down to match, or it drifts into fiction.

    ``note`` is prose for the reader. It carries no number the gate does not
    enforce - an earlier revision had a ``target_ceiling`` string that ended
    up contradicting the enforced value, which is worse than no string.

    ``budget_*`` is the EXTRACTION BUDGET (see the module docstring): a named,
    bounded, self-destructing allowance added to the upward bound while
    in-file extraction steps run. ``budget_expires_at`` is machine-checked -
    once ``_CURRENT_STEP`` reaches it, a non-zero budget fails the suite.
    """

    identifier: str
    baseline_total: int
    baseline_code: int
    headroom: int
    note: str
    grow_slack: int = 10
    budget_total: int = 0
    budget_code: int = 0
    budget_reason: str = ""
    budget_expires_at: str = ""

    @property
    def is_file_row(self) -> bool:
        return "::" not in self.identifier

    @property
    def max_total(self) -> int:
        return self.baseline_total + self.grow_slack + self.budget_total

    @property
    def max_code(self) -> int:
        return self.baseline_code + self.grow_slack + self.budget_code


_RATCHET: tuple[_Entry, ...] = (
    _Entry(
        identifier="custom_components/poise/ha/tick_orchestrator.py",
        # O.5 landed: the 41 stage bodies left this file for the four phase
        # modules below. 3567 -> 931 total, 2294 -> 436 code. The ceiling drops
        # to the plan's target (1200/900) and the extraction budget is gone -
        # this was the step it was declared to expire at, and it expired by
        # doing its job: lines finally left the file.
        baseline_total=931,
        baseline_code=436,
        headroom=50,
        note="1200/900 total/code, reached at step O.5",
        # Plan defect found while landing O.1 (see plan section 18): O.0 froze
        # this file at ist == ceiling with zero headroom, but O.1-O.4 are
        # IN-FILE extractions - every one of them adds signature, result-
        # construction and import lines and removes none, because only O.5
        # carries lines out of the file. The two rules were therefore
        # unsatisfiable together. Rather than raising the ceiling (which would
        # destroy its one-way property) the allowance is declared here: named,
        # bounded, and self-destructing at the step that makes it unnecessary.
        # Budget history (plan section 18.1): sized at +120/+90 on the estimate
        # "O.2/O.3 small positive". MEASURED, that estimate was wrong: O.1 cost
        # +41/+29 and O.2 +94/+71 (cumulative +138/+100), because threading two
        # explicit per-tick objects through ~30 method signatures is ~70 code
        # lines of pure plumbing - nearly all of it signature explosions forced
        # by the 88-column limit. The design was reviewed and kept (bundling
        # config+bindings into one wrapper would shrink the signatures but make
        # every one of ~200 use sites read `env.config.x`, which is worse where
        # it matters). So the budget is re-declared ONCE at the measured need
        # plus the O.3 estimate, and the reason records why - a budget that is
        # silently topped up on every overrun is not a budget.
        #   ist after O.2   +138/+100
        #   O.3 MEASURED     +11/+10   (estimate was +15/+10 - four injected
        #                               attributes and their slots/params, net
        #                               of a docstring section that moved into
        #                               ha/tick_ports.py)
        #   O.4 MEASURED     -66/-46   (estimate was -68/-45: _CoordinatorGlobals,
        #                               its TYPE_CHECKING mirror and the 15
        #                               noqa: F401 re-exports, minus the module
        #                               imports and the rewritten docstrings)
        # Peak was after O.3, at +149/+110 of the then-declared +160/+120. O.4 is
        # the LAST consumer of this budget - O.5 carries lines OUT of the file -
        # so the window is closed and its cost is no longer an estimate but a
        # measurement: +83/+64. The declaration was pulled down to exactly that,
        # and O.5 then made it moot: the file is 931/436 against a 1200/900
        # ceiling. The budget is gone because it EXPIRED AS DESIGNED, not
        # because it was folded into the cap.
    ),
    # ---- the four phase modules (new with O.5) -----------------------------
    # Same guard shape as the file row above, with the plan's per-module cap
    # (DoD section 9: no module of the tick chain over 1200 total / 900 code).
    # Their baselines are the measured post-move sizes; the bodies inside are
    # byte-identical to the ones the orchestrator held, so a baseline here is a
    # relocation record, not a new allowance.
    _Entry(
        identifier="custom_components/poise/ha/phase_prepare.py",
        baseline_total=1131,
        baseline_code=796,
        headroom=50,
        note=(
            "1200/900 total/code - plan DoD cap, effective from O.5. "
            "Raised 1112/780 -> 1131/796 by ADR-0066 N2: the emission edge "
            "grew a REASON half (mold_guard travels under the shared 'close' "
            "token) and the notification text a lead-in for the one advice "
            "that asks for the opposite action. Feature growth, measured "
            "after the fact - not refactoring drift, and 69/104 lines short "
            "of the DoD cap."
        ),
    ),
    _Entry(
        identifier="custom_components/poise/ha/phase_actuate.py",
        baseline_total=765,
        baseline_code=424,
        headroom=50,
        note="1200/900 total/code - plan DoD cap, effective from O.5",
    ),
    _Entry(
        identifier="custom_components/poise/ha/phase_shadow.py",
        baseline_total=400,
        baseline_code=244,
        headroom=50,
        note="1200/900 total/code - plan DoD cap, effective from O.5",
    ),
    _Entry(
        identifier="custom_components/poise/ha/phase_report.py",
        # O.6 grew this file by +64/+21: the outcome folds became six methods,
        # which costs six signatures, six docstrings and the per-fold ctx
        # unpacking, and removes nothing (the code stays in this file - the
        # lesson of plan section 18.6 restated). 738/549 -> 802/570 against an
        # unchanged 1200/900 cap. The baseline follows the measurement so the
        # row keeps tracking reality; the ceiling does not move.
        baseline_total=802,
        baseline_code=570,
        headroom=50,
        note="1200/900 total/code - plan DoD cap, effective from O.5",
    ),
    _Entry(
        identifier=("custom_components/poise/ha/tick_orchestrator.py::resume_prepare"),
        # O.1 landed: the 102 lines of inline fan-first glue moved into
        # _stage_fan_first / _stage_fan_write, giving 163/86 - under the plan's
        # 170/110 target, and the value the ceiling was lowered to.
        # O.2 added 13/11 back (`config = state.config` plus the extra argument
        # at eleven stage call sites, four of them exploded across lines by the
        # 88-column limit), declared as a budget expiring at O.5.
        # O.5 MEASURED +4/+4 on top: the stage calls in this method now name
        # their phase object (`self._prepare._stage_x` / `self._actuate._stage_x`),
        # and two of them - `_stage_comfort_solve` (92 cols) and
        # `_stage_mode_adoption` (93 cols) - cross the 88-column limit and get
        # exploded into three lines each. 176/97 -> 180/101.
        #
        # PLAN FINDING (O.5): this row is where the budget mechanism of plan
        # section 18.1 runs out of road. The budget expires here, but the code
        # it paid for does not come back - threading `config` and now the phase
        # receiver through these call sites is PERMANENT. Keeping the budget
        # would make "temporary allowance" mean "forever"; deleting docstring
        # to fit 163/86 would delete the four proof-of-dependency paragraphs
        # that plan section 18.5 defends. So the row is re-frozen at the
        # measured value: ceiling == baseline == 180/101, one-way again from
        # here, and this is the LAST step that touches these call sites (O.6
        # works inside _stage_outcome_diag, O.7 only finalises the table).
        # The code metric is the complexity signal (plan 18.5): 101 is well
        # under the plan's 110 target - the 180 total is a 79-line docstring.
        baseline_total=180,
        baseline_code=101,
        headroom=10,
        note=(
            "180/101 - re-frozen at O.5 (code 101 undercuts the plan's 110 "
            "target; the total is proof docstring, plan section 18.5)"
        ),
    ),
    _Entry(
        identifier="custom_components/poise/ha/phase_report.py::_stage_outcome_diag",
        # O.5 moved this method to phase_report.py BYTE-IDENTICALLY (AST
        # census) and re-froze it at 298/228. O.6 is the lowering step: the
        # state folds became the six ``_fold_*`` methods, called from inside
        # the UNCHANGED ``safe_collect`` closure in unchanged text order. What
        # is left here is the dispatcher - defaults, closure, assembly - at
        # 59/32, so the ceiling drops (once, permanently) to the plan's O.6
        # target 60/40 and the baseline to the measured value. Unlike
        # resume_prepare at O.5 this row hits its target: the code the folds
        # took away really left the METHOD, even though it stayed in the file
        # (see the file row above, which absorbed the +64/+21).
        baseline_total=59,
        baseline_code=32,
        headroom=10,
        note="60/40 total/code - plan O.6 target, reached at O.6",
    ),
    _Entry(
        identifier=(
            "custom_components/poise/ha/phase_report.py::_stage_assemble_tick_data"
        ),
        # Moved byte-identically to phase_report.py. Same re-freeze as above:
        # 331+1 / 258+1 was the declared effective cap, and it is now the
        # ceiling. This is the plan's ONE named permanent size exception.
        baseline_total=332,
        baseline_code=259,
        headroom=10,
        note="332/259 - approved permanent exception, no lowering step",
    ),
    _Entry(
        identifier="custom_components/poise/ha/phase_prepare.py::_stage_write_target",
        # Moved byte-identically to phase_prepare.py. Same re-freeze: 153+1 /
        # 102+1 was the declared effective cap.
        baseline_total=154,
        baseline_code=103,
        headroom=10,
        note="154/103 - no lowering step planned in this refactor",
    ),
    _Entry(
        # P.1 moved this function to control/pipeline_prepare.py VERBATIM (AST
        # census over all 15 functions, plus a full diff read for the comments
        # ast.dump cannot see). Path follows the code; the numbers do not move,
        # because nothing inside the function did.
        identifier=(
            "custom_components/poise/control/pipeline_prepare.py"
            "::_stage_observe_guarded"
        ),
        # Total grew +17 with the P.2b decision docstring; CODE is unchanged at
        # 105. Section 18.5: the code count is the complexity signal, the total
        # is drift - and a total that forbids writing down why a split was
        # rejected would be a gate against the record itself.
        baseline_total=174,
        baseline_code=105,
        headroom=10,
        note=(
            "174/105 - growth guard, no lowering target. P.2 ANALYSED 2026-08-17, "
            "outcome P.2b: no seam worth taking. One real candidate exists - the "
            "actuator-capability/dynamics block, which owns the whole swallowing "
            "boundary and shares no state with the window->learning chain "
            "(measured: learn_step, observe_seasonless and observe_window_auto "
            "touch neither rt.compressor nor rt.learning.pi). It was extracted and "
            "measured: the function drops to 135/90, but the MODULE grows "
            "891/597 -> 951/626, i.e. +29 code lines to save 15, and the four "
            "config parameters become pure pass-throughs because the call cannot "
            "move earlier without changing what has run when the window block "
            "aborts. Reverted. The rest is one narrative chained by data: window "
            "health -> effective window signal -> learning gate -> window-auto "
            "update."
        ),
    ),
    _Entry(
        # Added with O.3: the port adapter is the one place that still knows
        # the coordinator instance, so it is exactly the place where coupling
        # would silently accumulate again. The plan's table only foresaw
        # ha/phase_*.py, which would have left this file unguarded until O.5.
        # O.5: MonolithTickPorts is gone, so both values ratchet DOWN by the
        # measured amount (405/148 -> 397/145).
        identifier="custom_components/poise/ha/tick_ports.py",
        baseline_total=397,
        baseline_code=145,
        headroom=50,
        note="397/145 - growth guard; it should shrink, never grow",
    ),
    _Entry(
        # Added with O.5 (see plan section 18.7). coordinator.py is the
        # composition root, not a tick-chain module in the sense of the split,
        # but O.5 grew it by +43/+30 for the phase wiring and the DoD's
        # "no module above 1200/900" would otherwise never see it: 1358 total
        # is past the total limit while 750 code is comfortably inside it. Per
        # section 18.5 the code metric is the complexity signal and the total
        # is drift - 608 of those lines are docstring and comment. So: growth
        # guard at the measured value, no lowering target, and the total is
        # explicitly NOT treated as a violation.
        # +14/+6 for the translated exceptions (quality-scale
        # exception-translations): HA's API takes translation_domain +
        # translation_key + a placeholders dict where an f-string took one
        # line. Irreducible at 88 columns, and the trade is a message the user
        # can read in their language instead of an English internal string.
        # +17/+8 for S.3: the IssueLedger replaces a bare set (three comment
        # lines say why the identity matters), the reporter's collaborators
        # are handed over by keyword instead of via a backreference, and the
        # ext-temp invalidation moved here from the reporter. Bought with a
        # backreference removed from the package, not with plumbing.
        # -78/-67 for review 2026-08-19 P3: the three suggestion-issue bodies
        # (_sync_clo_suggestion_issue / _sync_suggestion_issue /
        # _sync_season_hint_issue) moved to the HealthReporter — the owner of
        # the repair-issue surface — leaving thin port-named facades here.
        identifier="custom_components/poise/coordinator.py",
        baseline_total=1311,
        baseline_code=697,
        headroom=50,
        note=(
            "growth guard only, no lowering target - the code metric is "
            "what counts. Deliberately WITHOUT a number pair: the "
            "baselines above are the single place that carries it, and a "
            "second copy in prose went stale twice."
        ),
    ),
    # ---- the three pure-pipeline modules (new with P.1) --------------------
    # The row added after the O.7 audit guarded control/tick_pipeline.py at
    # 1336/884 - 16 code lines below the DoD cap, the tightest margin in the
    # chain, and the reason the split plan exists. P.1 partitioned that file
    # along its actual consumers and DELETED it, so its row is gone and these
    # three replace it. Their baselines are MEASURED post-move sizes, not the
    # plan's per-module function-code column: the plan tabled 535/194/75 for
    # the function bodies alone, and each new file additionally carries its own
    # docstring, imports and constants. Measured, the three code counts sum to
    # 915 against the old 884 - the +31 is that per-module overhead, paid once,
    # and every one of the three now sits far below the cap instead of one file
    # sitting just under it.
    _Entry(
        identifier="custom_components/poise/control/pipeline_prepare.py",
        # +26 total from the module-level "HA-free synchronous, not pure"
        # definition and the P.2b decision docstring; code unchanged at 597.
        baseline_total=917,
        baseline_code=597,
        headroom=50,
        note="1200/900 total/code - plan DoD cap, effective from P.1",
    ),
    _Entry(
        identifier="custom_components/poise/control/pipeline_actuate.py",
        baseline_total=430,
        baseline_code=227,
        headroom=50,
        note="1200/900 total/code - plan DoD cap, effective from P.1",
    ),
    _Entry(
        # One function, deliberately: it marks the sequencer seam where
        # resume_prepare assembles the FinalizeContext, not a phase. A module
        # that marks a real boundary is allowed to be small (split plan
        # section 3); what it must not do is quietly become a dumping ground,
        # which is what this row watches for.
        identifier="custom_components/poise/control/pipeline_finalize.py",
        baseline_total=131,
        baseline_code=91,
        headroom=50,
        note="1200/900 total/code - plan DoD cap, effective from P.1",
    ),
    # ---- the gate measures ITSELF (plan S.2) --------------------------------
    # The predecessor of these seven files was one 2270/1272 module: 1.4x the
    # code cap it imposed on everything else, and the only file of the tick
    # chain absent from this table. A checker exempt from its own check is how
    # that happens. The DoD cap now covers the gate too - a deliberate
    # extension of a rule written for production modules, on the grounds that
    # a structure test nobody can read stops being a structure test.
    # Baselines are the measured post-split sizes; the split moved every
    # definition AST-identical, so these are relocation records, not new
    # allowances.
    _Entry(
        identifier="tests/structure_support.py",
        baseline_total=278,
        baseline_code=166,
        headroom=50,
        # +13/+6 in S.3: ``_component_sources``/``_rel`` became shared the
        # moment the ports gate needed to enumerate the package too - the
        # split's own rule (used by more than one gate -> support) applied.
        note="1200/900 total/code - the S.2 gate split; the gate measures itself",
    ),
    _Entry(
        identifier="tests/test_structure_ratchet.py",
        baseline_total=597,
        baseline_code=301,
        headroom=50,
        # Self-reference, and it bit on the first run: this row's own eight
        # lines - and its six siblings - are part of what it measures. The
        # baseline is therefore taken AFTER the block below existed, not
        # before. Editing the digits in place cannot move the count again.
        note="1200/900 total/code - the S.2 gate split; the gate measures itself",
    ),
    _Entry(
        identifier="tests/test_structure_snapshot.py",
        baseline_total=162,
        baseline_code=103,
        headroom=50,
        note="1200/900 total/code - the S.2 gate split; the gate measures itself",
    ),
    _Entry(
        # +58/+31 across S.3 and S.4a: the backreference invariant absorbed
        # its own anti-vacuum control (one test now carries both), and the
        # read boundary - true since the phase-4 split, enforced by nothing -
        # became a rule with its allowlist of four reasons.
        identifier="tests/test_structure_ports.py",
        baseline_total=322,
        baseline_code=170,
        headroom=50,
        note="1200/900 total/code - the S.2 gate split; the gate measures itself",
    ),
    _Entry(
        identifier="tests/test_structure_phases.py",
        baseline_total=683,
        baseline_code=388,
        headroom=50,
        note="1200/900 total/code - the S.2 gate split; the gate measures itself",
    ),
    _Entry(
        identifier="tests/test_structure_pipeline.py",
        baseline_total=328,
        baseline_code=178,
        headroom=50,
        note="1200/900 total/code - the S.2 gate split; the gate measures itself",
    ),
    _Entry(
        # +39/+17: the S.2 successor guard, added after a CI run showed the
        # pre-split file back in the checkout (web upload adds, never
        # deletes). Two failures that read like a code regression were in
        # truth one stale file; the guard now says which.
        # +43/+22: the dangling-gate-pointer guard. An external review found
        # two module docstrings still naming the deleted aggregate - prose
        # does not run, so nothing had failed. Both classes of stale
        # cross-reference now have a detector.
        identifier="tests/test_structure_meta.py",
        baseline_total=307,
        baseline_code=165,
        headroom=50,
        note="1200/900 total/code - the S.2 gate split; the gate measures itself",
    ),
)


# --- rule (1a): growth band - tight upward -----------------------------------


@pytest.mark.parametrize("entry", _RATCHET, ids=[e.identifier for e in _RATCHET])
def test_ratchet_does_not_exceed_ceiling(entry: _Entry) -> None:
    """Rule 1a: ist <= baseline + grow_slack for both metrics.

    The slack is small on purpose - a comment or a reflowed signature fits, a
    feature does not. When this fires, the honest first question is "can this
    be split?", and only if the answer is genuinely no does the baseline get
    pulled up with a reason in ``note``.
    """
    actual_total, actual_code = _measure(entry.identifier)
    budget = (
        f" (+{entry.budget_total}/{entry.budget_code} extraction budget: "
        f"{entry.budget_reason}, expires at {entry.budget_expires_at})"
        if entry.budget_total or entry.budget_code
        else ""
    )
    assert actual_total <= entry.max_total, (
        f"{entry.identifier}: total lines are {actual_total}, allowed is "
        f"{entry.max_total} (baseline {entry.baseline_total} + slack "
        f"{entry.grow_slack}){budget} -> GEWACHSEN. Split the code; raise the "
        f"baseline only with a reason in `note`."
    )
    assert actual_code <= entry.max_code, (
        f"{entry.identifier}: code lines are {actual_code}, allowed is "
        f"{entry.max_code} (baseline {entry.baseline_code} + slack "
        f"{entry.grow_slack}){budget} -> GEWACHSEN. Split the code; raise the "
        f"baseline only with a reason in `note`."
    )


# --- rule (1b): the DoD cap - a constant, not a per-row literal --------------

# Plan section 9: "no module of the tick chain above 1200 lines / 900 code
# lines". Only the CODE half is enforced, and deliberately so: section 18.5
# established that for this codebase the total-line count is a drift signal
# while the code count is the complexity signal, because a large share of
# these files is load-bearing proof documentation. Capping totals would put a
# gate against writing down why the tick is correct.
_DOD_CODE_CAP = 900


@pytest.mark.parametrize(
    "entry",
    [e for e in _RATCHET if e.is_file_row],
    ids=[e.identifier for e in _RATCHET if e.is_file_row],
)
def test_no_tick_chain_module_exceeds_the_dod_cap(entry: _Entry) -> None:
    """Rule 1b: the architecture cap from the plan's DoD.

    Unlike rule 1a this is NOT per-row editable - it is one constant for the
    whole tick chain. Rule 1a keeps a file from drifting away from its own
    measured size; this keeps the whole set under the ceiling the plan
    promised, no matter how often somebody pulls a baseline up.
    """
    _, actual_code = _measure(entry.identifier)
    assert actual_code <= _DOD_CODE_CAP, (
        f"{entry.identifier}: {actual_code} code lines exceed the plan's DoD "
        f"cap of {_DOD_CODE_CAP} for a tick-chain module. This one is not "
        f"negotiable by editing the table - the module has to be split."
    )


# --- rule (2): Ratchet-Baseline - tracks real improvements ------------------


@pytest.mark.parametrize("entry", _RATCHET, ids=[e.identifier for e in _RATCHET])
def test_ratchet_baseline_is_not_orphaned(entry: _Entry) -> None:
    """Rule 2, "Ratchet-Baseline": ist >= baseline - headroom for both
    metrics. If the code has shrunk by more than its headroom, the table's
    baseline is stale and must be pulled down to match reality - a shrink the
    table doesn't reflect is exactly as much a lie as a silent grow, and it
    silently widens the upward band of rule 1a by the same amount.
    """
    actual_total, actual_code = _measure(entry.identifier)
    floor_total = entry.baseline_total - entry.headroom
    floor_code = entry.baseline_code - entry.headroom
    assert actual_total >= floor_total, (
        f"{entry.identifier}: total lines are {actual_total}, baseline is "
        f"{entry.baseline_total} (headroom {entry.headroom}, floor "
        f"{floor_total}) -> LIMIT VERWAIST, bitte baseline nachziehen (the "
        f"table's baseline no longer reflects reality). Lower "
        f"baseline_total to the measured value."
    )
    assert actual_code >= floor_code, (
        f"{entry.identifier}: code lines are {actual_code}, baseline is "
        f"{entry.baseline_code} (headroom {entry.headroom}, floor "
        f"{floor_code}) -> LIMIT VERWAIST, bitte baseline nachziehen (the "
        f"table's baseline no longer reflects reality). Lower "
        f"baseline_code to the measured value."
    )


# --- the extraction budget must expire on schedule ---------------------------


@pytest.mark.parametrize("entry", _RATCHET, ids=[e.identifier for e in _RATCHET])
def test_extraction_budget_is_declared_and_expires(entry: _Entry) -> None:
    """An extraction budget must be justified and must self-destruct.

    The budget is the one sanctioned way the effective ceiling can sit above
    the frozen O.0 value, so it carries three obligations: a reason, an expiry
    step, and actually being gone by then. Once ``_CURRENT_STEP`` reaches
    ``budget_expires_at``, a leftover budget fails here - which is what keeps
    "temporary allowance" from quietly becoming "the new ceiling".
    """
    has_budget = bool(entry.budget_total or entry.budget_code)
    if not has_budget:
        assert not entry.budget_reason and not entry.budget_expires_at, (
            f"{entry.identifier}: budget metadata without a budget - drop the "
            f"leftover reason/expiry fields."
        )
        return

    assert entry.budget_reason, (
        f"{entry.identifier}: an extraction budget needs a reason naming which "
        f"steps consume it."
    )
    assert entry.budget_expires_at in _STEP_ORDER, (
        f"{entry.identifier}: budget_expires_at={entry.budget_expires_at!r} is "
        f"not a known step ({_STEP_ORDER!r})."
    )
    assert entry.budget_expires_at not in _ACTIVE_STEPS, (
        f"{entry.identifier}: the extraction budget "
        f"(+{entry.budget_total}/{entry.budget_code}, {entry.budget_reason}) "
        f"was declared to expire at {entry.budget_expires_at!r}, and "
        f"_CURRENT_STEP={_CURRENT_STEP!r} has reached it. Remove the budget "
        f"and pull ceiling/baseline down to the measured value."
    )


# --- anti-vacuum: a stale table row must fail loudly ------------------------


@pytest.mark.parametrize("entry", _RATCHET, ids=[e.identifier for e in _RATCHET])
def test_ratchet_entry_target_exists(entry: _Entry) -> None:
    """A table row naming a file/method that no longer exists must fail the
    suite, not be silently skipped (e.g. by an empty glob or a swallowed
    exception). ``_measure`` already asserts existence internally; this test
    makes that guarantee an explicit, independently named check.
    """
    _measure(entry.identifier)
