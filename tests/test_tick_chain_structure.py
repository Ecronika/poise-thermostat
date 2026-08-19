"""Structure ratchet gate (Plan O.0): a pure, HA-free size and structure lock
for the tick_orchestrator refactor.

Rationale and full spec: ``docs/Konzepte/2026-08-16_Refactoring-Plan_tick-
orchestrator.md``, section "O.0 - Structure Ratchet". Summary: the monolith
and its worst offender methods get frozen at their measured size the moment
this test lands (baseline == ceiling for every row today); as each later
O.n step shrinks a target, its ceiling drops - once, permanently - and its
baseline is pulled down to match. Two independent rules per row:

    (1) Architektur-Deckel  - one-sided, only ever drops:  ist <= ceiling
    (2) Ratchet-Baseline    - tracks reality:               ist >= baseline - H

One sanctioned exception exists, the EXTRACTION BUDGET. Steps O.1-O.4 pull
code out of ``resume_prepare`` & co. into new methods *inside the same file*,
which necessarily adds signature, result-construction and import lines; only
O.5 carries lines out of the file. Freezing the file at ist == ceiling with
zero headroom therefore made rules (1) and (2) unsatisfiable together. Instead
of raising the ceiling - which would destroy its one-way property - a row may
declare a bounded budget with a reason and an expiry step. It is added to the
ceiling, and ``test_extraction_budget_is_declared_and_expires`` fails the
suite once its expiry step is reached and it is still there.

The gate outlived that plan. Its successor,
``docs/Konzepte/2026-08-17_Split-Plan_tick-pipeline.md``, adds the P.1 block at
the end of this file: the symbol partition of the three ``control/pipeline_*``
modules. That block is NOT a size ratchet - it pins WHICH stage lives WHERE,
which is the part of a mechanical move that survives the move.

This file must NOT import ``homeassistant`` - it measures the target source
files by reading and parsing them as text (``ast``/``tokenize``), never by
importing them.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- refactor-step bookkeeping ---------------------------------------------

# The step this repository state has reached. Bump this (and only this) once
# a later O.n step lands and its target lines are actually shrunk; the two
# ratchet rules above and _ACTIVE_STEPS below both key off it.
_CURRENT_STEP = "O.7"

_STEP_ORDER: tuple[str, ...] = (
    "O.0",
    "O.1",
    "O.2",
    "O.3",
    "O.4",
    "O.5",
    "O.6",
    "O.7",
)

_ACTIVE_STEPS: tuple[str, ...] = _STEP_ORDER[: _STEP_ORDER.index(_CURRENT_STEP) + 1]


# --- line classification (measurement method, plan O.0) --------------------


def _classify_lines(src: str) -> list[str]:
    """Classify every physical line of ``src`` as "blank", "docstring",
    "comment", or "code" - each line exactly once, in that priority order.

    - "blank": the stripped line is empty.
    - "docstring": the line falls inside the *first* statement of a
      Module/ClassDef/FunctionDef/AsyncFunctionDef body, when that statement
      is an ``ast.Expr`` wrapping an ``ast.Constant`` string (an actual
      docstring, not just any string expression).
    - "comment": a ``tokenize`` COMMENT token whose *physical line*, once
      stripped, starts with ``#`` - i.e. a comment-only line. An inline
      comment after code (``x = 1  # note``) does NOT count here; that line
      is "code".
    - "code": everything else.
    """
    lines = src.splitlines()
    n = len(lines)
    cls: list[str | None] = [None] * (n + 1)  # 1-indexed; index 0 unused

    for i, line in enumerate(lines, start=1):
        if line.strip() == "":
            cls[i] = "blank"

    tree = ast.parse(src)
    docstring_nodes: list[ast.Expr] = []

    def _note_docstring(node: ast.AST) -> None:
        body = getattr(node, "body", None)
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.append(first)

    _note_docstring(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            _note_docstring(node)

    for dnode in docstring_nodes:
        assert dnode.end_lineno is not None
        for ln in range(dnode.lineno, dnode.end_lineno + 1):
            if cls[ln] is None:
                cls[ln] = "docstring"

    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            continue
        start_row = tok.start[0]
        if lines[start_row - 1].strip().startswith("#") and cls[start_row] is None:
            cls[start_row] = "comment"

    for i in range(1, n + 1):
        if cls[i] is None:
            cls[i] = "code"

    return cls[1:]  # type: ignore[return-value]


# --- per-entry measurement --------------------------------------------------


def _find_function(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Locate a function/method named ``name`` anywhere in ``tree``. Raises
    (not silently skips) if it is missing or ambiguous, so a stale table row
    - naming a method that got renamed or removed - fails the suite instead
    of quietly passing.
    """
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    assert matches, (
        f"method {name!r} not found - the ratchet table references a method "
        f"that no longer exists in this file. Update or remove the table row."
    )
    assert len(matches) == 1, (
        f"method {name!r} found {len(matches)} times - ambiguous; the "
        f"ratchet table needs an unambiguous target."
    )
    return matches[0]


def _measure(identifier: str) -> tuple[int, int]:
    """Return ``(total_lines, code_lines)`` for a table identifier, which is
    either ``"relative/path.py"`` (whole-file) or
    ``"relative/path.py::method_name"`` (single method/function).
    """
    rel_path, _, method_name = identifier.partition("::")
    path = REPO_ROOT / rel_path
    assert path.is_file(), (
        f"{identifier}: file {rel_path!r} does not exist - the ratchet table "
        f"references a stale path. Update or remove the table row."
    )

    src = path.read_text(encoding="utf-8")
    cls = _classify_lines(src)

    if not method_name:
        total = len(src.splitlines())
        code = sum(1 for c in cls if c == "code")
        return total, code

    tree = ast.parse(src)
    node = _find_function(tree, method_name)
    assert node.end_lineno is not None
    start, end = node.lineno, node.end_lineno
    total = end - start + 1
    code = sum(1 for c in cls[start - 1 : end] if c == "code")
    return total, code


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
        identifier="custom_components/poise/coordinator.py",
        baseline_total=1372,
        baseline_code=756,
        headroom=50,
        note="1358/750 - growth guard only; code metric is what counts",
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


# --- enforced structural invariants, active from O.2 ------------------------

_SNAPSHOT_MODULE = "custom_components/poise/ha/tick_snapshot.py"
_CONFIG_MODULE = "custom_components/poise/runtime/config.py"


def _dataclass_annotations(rel_path: str, class_name: str) -> dict[str, ast.expr]:
    """``field name -> annotation AST`` for one class, read as text.

    Parsed, never imported - same rule as every other measurement in this
    file. Only the class body's own ``AnnAssign`` statements count, so methods
    and nested scopes cannot smuggle a field in.
    """
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} does not exist"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name
    ]
    assert len(matches) == 1, (
        f"{rel_path}: expected exactly one class {class_name!r}, found {len(matches)}."
    )
    return {
        stmt.target.id: stmt.annotation
        for stmt in matches[0].body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }


def test_tick_config_snapshot_carries_no_entity_id_field() -> None:
    """Plan O.0 invariant (active from O.2): entity ids belong to
    ``ZoneBindings``, configuration never carries one.

    Enforced as a name grep of ``TickConfigSnapshot``'s fields against the
    ``ZoneBindings`` name list - the exact check the plan names, and the one
    Rev. 2 of the plan violated itself by putting ``_windows`` in the tuning
    object. The second half of the invariant is that the pre-existing parser
    contract ``runtime.config.ZoneTuning`` stays untouched: it must still
    exist where it always was, and the new module must not shadow the name.
    """
    config_fields = set(_dataclass_annotations(_SNAPSHOT_MODULE, "TickConfigSnapshot"))
    binding_fields = set(_dataclass_annotations(_SNAPSHOT_MODULE, "ZoneBindings"))
    assert binding_fields, "ZoneBindings has no fields - the grep would be vacuous"
    overlap = config_fields & binding_fields
    assert not overlap, (
        f"TickConfigSnapshot carries the entity-wiring field(s) {sorted(overlap)}; "
        f"identity and wiring belong to ZoneBindings."
    )
    # ``runtime.config.ZoneTuning`` is the untouched parser contract. Pinned
    # by its exact field set, not just by existing: the audit after O.7 noted
    # that an existence check would stay green while somebody renamed or
    # dropped fields, which is precisely the "unchanged" the DoD claims.
    assert (
        set(_dataclass_annotations(_CONFIG_MODULE, "ZoneTuning")) == _ZONE_TUNING_FIELDS
    ), (
        "runtime.config.ZoneTuning's field set changed. This is the parser "
        "contract the tick refactor promised NOT to touch (plan DoD); the "
        "O.2 rename to TickConfigSnapshot exists for exactly that reason. If "
        "the change is intentional and unrelated to the tick chain, update "
        "_ZONE_TUNING_FIELDS in the same commit that justifies it."
    )
    snapshot_classes = {
        n.name
        for n in ast.parse(
            (REPO_ROOT / _SNAPSHOT_MODULE).read_text(encoding="utf-8")
        ).body
        if isinstance(n, ast.ClassDef)
    }
    assert "ZoneTuning" not in snapshot_classes, (
        "tick_snapshot.py defines a second ZoneTuning - the name is taken by "
        "the parser contract in runtime/config.py."
    )


# The parser contract as of the O.0 baseline, frozen so "unchanged" is a
# measurement rather than a claim. 32 fields; git confirms runtime/config.py
# was not touched by any commit of this refactor.
_ZONE_TUNING_FIELDS = frozenset(
    {
        "active_comfort",
        "adaptive_cool_cfg",
        "adopt_external_mode",
        "adopt_external_setpoint",
        "category",
        "clo_offset",
        "comfort_base",
        "comp_min_off_opt",
        "comp_mode_hold_opt",
        "compressor_guard",
        "cool_hard_cap",
        "cool_lockout_enabled",
        "cool_min_outdoor",
        "dynamics_override",
        "hdh_cfg",
        "heat_lockout_enabled",
        "heat_max_outdoor",
        "mpc_params",
        "operative_input",
        "optimal_start",
        "optimal_stop",
        "override_cfg",
        "override_policy",
        "override_suggestions",
        "presence_cfg",
        "priority",
        "room_profile",
        "schedule",
        "thermal_shock_delta",
        "trace_enabled",
        "vent_notify",
        "window_auto_cfg",
    }
)

_MUTABLE_TYPE_NAMES = frozenset({"list", "dict", "set", "List", "Dict", "Set"})


@pytest.mark.parametrize("class_name", ["TickConfigSnapshot", "ZoneBindings"])
def test_snapshot_classes_have_no_mutable_sequence_field(class_name: str) -> None:
    """Plan O.0 invariant (active from O.2): no field of either frozen class
    may be typed ``list``/``dict``/``set``.

    ``@dataclass(frozen=True)`` freezes the field BINDING, not the object
    behind it - a ``list[str]`` field would make the class formally frozen but
    not a snapshot (``coordinator._windows`` is a live list, which is why
    ``windows`` is a ``tuple[str, ...]`` built with ``tuple(...)``). The check
    walks the whole annotation, so a nested ``tuple[list[str], ...]`` is
    caught too.
    """
    annotations = _dataclass_annotations(_SNAPSHOT_MODULE, class_name)
    assert annotations, f"{class_name} has no annotated fields"
    for field_name, annotation in annotations.items():
        for node in ast.walk(annotation):
            bad = (isinstance(node, ast.Name) and node.id in _MUTABLE_TYPE_NAMES) or (
                isinstance(node, ast.Attribute) and node.attr in _MUTABLE_TYPE_NAMES
            )
            assert not bad, (
                f"{class_name}.{field_name} is typed with a mutable container "
                f"({ast.unparse(annotation)}); sequences must be tuple[...] "
                f"and be copied with tuple(...) at build time."
            )


# --- enforced structural invariants, active from O.3 ------------------------

_ORCHESTRATOR_MODULE = "custom_components/poise/ha/tick_orchestrator.py"
_PORTS_MODULE = "custom_components/poise/ha/tick_ports.py"
# The one module that deliberately KEEPS a ``self._c`` (plan O.3: it also
# WRITES through it, and its rework is explicitly not part of this plan). It
# doubles as the positive control for the detector below - without it, a
# broken matcher would report "0 accesses" everywhere and look green.
_BACKREFERENCE_CONTROL = "custom_components/poise/ha/health_reporter.py"


def _self_attr_accesses(rel_path: str, attr: str) -> list[int]:
    """Line numbers of every ``self.<attr>`` AST node in one module.

    Matches the NODE, not the text: both the bare ``self.<attr>`` (e.g. passed
    as an argument) and every ``self.<attr>.<x>`` are counted, because the
    latter contains the former as its ``value``. Docstrings and comments that
    merely mention the name are invisible to this - which is deliberate, the
    plan's own prose still names the removed forms.
    """
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} does not exist"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ]


def _self_c_accesses(rel_path: str) -> list[int]:
    """``self._c`` accesses - the O.3 invariant's detector."""
    return _self_attr_accesses(rel_path, "_c")


def test_self_c_detector_is_not_vacuous() -> None:
    """Anti-vacuum control for the invariant below: the detector must still
    FIND a backreference where one legitimately exists.

    ``ha/health_reporter.py`` keeps its ``self._c`` on purpose (plan O.3 says
    so explicitly, and ``validate_configured_ext_temp`` writes through it). If
    this ever returns zero, the reporter was reworked - move the control to
    another real user or drop it; do not leave the invariant below guarded by
    a matcher nothing can trip.

    The same matcher backs the O.4 ``self._g`` invariant, so this one control
    covers both.
    """
    assert _self_c_accesses(_BACKREFERENCE_CONTROL), (
        f"{_BACKREFERENCE_CONTROL} no longer contains a single self._c node - "
        f"the detector in _self_attr_accesses can no longer be shown to work, "
        f"so the O.3/O.4 invariants below would be vacuously green."
    )


def test_tick_orchestrator_has_no_coordinator_backreference() -> None:
    """Plan O.0 invariant (active from O.3): ``tick_orchestrator.py`` AS A
    WHOLE holds 0 AST accesses to ``self._c``.

    Measured over the entire module - not just the ``_stage_*`` bodies - so
    ``_run_once``, ``_run_unavailable_tick``, ``prepare_until_forecast``,
    ``finalize_tick``, ``_maybe_record_trace`` and
    ``_write_unavailable_safe_state`` are all covered. What replaced it: the
    five typed port views and the ``TickSnapshotSource``, both implemented in
    ``ha/tick_ports.py``, which is the only place in the tick-orchestration
    chain that knows a ``PoiseCoordinator``.
    """
    hits = _self_c_accesses(_ORCHESTRATOR_MODULE)
    assert not hits, (
        f"{_ORCHESTRATOR_MODULE} accesses self._c on line(s) {hits}. After O.3 "
        f"every coordinator effect goes through ``self._ports`` and every "
        f"per-tick read view through ``self._source``."
    )


def test_port_adapter_is_not_a_service_locator() -> None:
    """Plan O.3 condition: the port module may not smuggle the backreference
    back in as dynamic dispatch.

    Two forms are forbidden, both as end state and as a transitional shortcut:
    a ``__getattr__`` anywhere in the module (that is ``self._c`` renamed), and
    a ``getattr(self._c, <variable>)`` (an untyped hole in the middle of a
    typed adapter). A ``getattr`` with a STRING LITERAL name would be
    equivalent to plain attribute access and is therefore not what this
    forbids - but none exists, and the message says so if one appears.
    """
    path = REPO_ROOT / _PORTS_MODULE
    assert path.is_file(), f"{_PORTS_MODULE} does not exist"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    dunder_getattr = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "__getattr__"
    ]
    assert not dunder_getattr, (
        f"{_PORTS_MODULE} defines __getattr__ on line(s) {dunder_getattr}; a "
        f"forwarding __getattr__ is self._c under a new name and is forbidden "
        f"by plan O.3, transitional forms included. Write the port out."
    )

    dynamic = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and not (
            len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        )
    ]
    assert not dynamic, (
        f"{_PORTS_MODULE} resolves an attribute dynamically on line(s) "
        f"{dynamic}; every port must be an explicit, typed method."
    )


# The five capability views of plan O.3, with the exact membership from the
# plan's table. Their union is the census number the whole step rests on.
_PORT_VIEWS: dict[str, frozenset[str]] = {
    "SequencerPorts": frozenset(
        {
            "emit_health",
            "save_if_due",
            "record_trace",
            "forecast_outdoor",
            "write_unavailable_safe_state",
            "fire_override_ended",
            "notify_convergence",
            "unavailable_logged",
        }
    ),
    "PreparePorts": frozenset(
        {
            "end_hold",
            "expire_timed_states",
            "notify_failure",
            "notify_cooling_failure",
            "set_mpc_params",
        }
    ),
    "ActuatePorts": frozenset(
        {
            "end_hold",
            "fire_override_ended",
            "set_mode_override",
            "set_override",
            "commit_execution",
        }
    ),
    "ShadowPorts": frozenset({"mpc_params"}),
    "ReportPorts": frozenset(
        {
            "sync_suggestion_issue",
            "sync_clo_suggestion_issue",
            "sync_season_hint_issue",
        }
    ),
}


def _class_members(tree: ast.Module, class_name: str) -> set[str]:
    """Public member names a class declares: methods and properties alike.

    A property + setter pair counts ONCE (both are ``FunctionDef``s under the
    same name), which is exactly how the plan counts ``unavailable_logged``.
    """
    matches = [
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name
    ]
    assert len(matches) == 1, (
        f"expected exactly one class {class_name!r} in {_PORTS_MODULE}, "
        f"found {len(matches)}."
    )
    return {
        stmt.name
        for stmt in matches[0].body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not stmt.name.startswith("_")
    }


@pytest.mark.parametrize("view", sorted(_PORT_VIEWS))
def test_port_view_membership_matches_the_plan(view: str) -> None:
    """Plan O.3: each of the five views declares exactly its tabled ports.

    A view that quietly grows a method is a widened capability - the whole
    point of splitting one 20-method protocol into five is that a phase cannot
    reach past its own view (``ShadowPhase`` must not even be able to TYPE a
    ``commit_execution`` call).
    """
    tree = ast.parse((REPO_ROOT / _PORTS_MODULE).read_text(encoding="utf-8"))
    assert _class_members(tree, view) == set(_PORT_VIEWS[view])


def test_port_views_union_to_exactly_twenty_capabilities() -> None:
    """Plan O.3: the union of the five views is exactly the 20 ports the O.2
    census left on the backreference.

    ``end_hold`` and ``fire_override_ended`` are each in two views, so the
    memberships sum to 22 and the union is 20. The adapter must implement the
    union and nothing beyond it - a public method with no port behind it would
    be a back channel around the views.
    """
    union: set[str] = set()
    for members in _PORT_VIEWS.values():
        union |= members
    assert sum(len(m) for m in _PORT_VIEWS.values()) == 22
    assert len(union) == 20, f"union is {len(union)}: {sorted(union)}"

    tree = ast.parse((REPO_ROOT / _PORTS_MODULE).read_text(encoding="utf-8"))
    assert _class_members(tree, "CoordinatorTickPorts") == union, (
        "the coordinator adapter's public surface must be exactly the 20 ports"
    )


# --- enforced structural invariants, active from O.4 ------------------------

_COORDINATOR_MODULE = "custom_components/poise/coordinator.py"
# Written as a constant, never as a real directive, so this file's own source
# can carry the needle without ruff seeing a suppression here.
_NOQA_F401 = "noqa: F401"
_PROXY_CLASS = "_CoordinatorGlobals"


def _count_in_file(rel_path: str, needle: str) -> int:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} does not exist"
    return path.read_text(encoding="utf-8").count(needle)


def test_noqa_detector_is_not_vacuous() -> None:
    """Anti-vacuum control for the invariant below: the text matcher must
    actually find the marker it is supposed to forbid.

    Self-contained on purpose - an external "file that legitimately has one"
    control would rot the moment that file is cleaned up, and would then leave
    the O.4 invariant guarded by a matcher nothing can trip.
    """
    sample = f"import a  # {_NOQA_F401}\nimport b  # {_NOQA_F401}\nimport c\n"
    assert sample.count(_NOQA_F401) == 2


def test_coordinator_has_no_noqa_f401_reexports() -> None:
    """Plan O.0 invariant (active from O.4): ``coordinator.py`` holds 0
    occurrences of ``noqa: F401``.

    Those 15 suppressions existed for exactly one reason: the module imported
    the fault-injection functions it never calls, so that
    ``ha/tick_orchestrator.py`` could resolve them back through it at call time
    (``self._g.<name>``). O.4 moved every one of those calls onto the OWNING
    module, which is where the tests patch now, so the re-exports are dead
    weight - and a dead re-export is a second, silent patch target: patching it
    would look like it worked and inject nothing.

    ``tests/integration/test_o4_patch_surface.py`` holds the other half of this
    (the names are really gone from the module object, and the migrated patches
    really bite); this check is the pure, HA-free one.
    """
    hits = _count_in_file(_COORDINATOR_MODULE, _NOQA_F401)
    assert hits == 0, (
        f"{_COORDINATOR_MODULE} carries {hits} '{_NOQA_F401}' suppression(s). "
        f"After O.4 nothing is re-exported through the coordinator module for "
        f"the tick to resolve; a fault-injection point is patched on the module "
        f"that OWNS the function."
    )


def test_coordinator_globals_proxy_is_gone() -> None:
    """Plan O.4: ``_CoordinatorGlobals``, ``self._g`` and the
    ``coordinator_module`` wiring exist nowhere in the component any more.

    All three are one mechanism: the class, the attribute holding it and the
    ``sys.modules[__name__]`` handed to the constructor. Leaving any of them
    behind would leave a second way to resolve those names - and the whole
    point of O.4 is that there is exactly one.
    """
    sources = sorted((REPO_ROOT / "custom_components").rglob("*.py"))
    assert sources, "no component sources found - this check would be vacuous"

    proxy_hits = [
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in sources
        if _PROXY_CLASS in p.read_text(encoding="utf-8")
    ]
    assert not proxy_hits, (
        f"{_PROXY_CLASS} still appears in {proxy_hits}; O.4 removed the "
        f"call-time proxy onto the coordinator module's namespace."
    )

    g_hits = {
        str(p.relative_to(REPO_ROOT)).replace("\\", "/"): lines
        for p in sources
        if (
            lines := _self_attr_accesses(
                str(p.relative_to(REPO_ROOT)).replace("\\", "/"), "_g"
            )
        )
    }
    assert not g_hits, (
        f"self._g is still accessed in {g_hits}. After O.4 a fault-injection "
        f"function is called as ``<owner_module>.<name>(...)``, so the patch "
        f"target is the owner and no proxy attribute is needed."
    )

    wiring_hits = [
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in sources
        if "coordinator_module" in p.read_text(encoding="utf-8")
    ]
    assert not wiring_hits, (
        f"the ``coordinator_module`` constructor wiring survives in "
        f"{wiring_hits}; the orchestrator no longer needs the module object."
    )


# --- enforced structural invariants, active from O.5 ------------------------
#
# The phase split. Seven invariants, one per plan row; each has an anti-vacuum
# control right next to it, because every one of them is a "count is zero"
# assertion and those go green for free when the matcher breaks.

_PHASE_MODULES: dict[str, str] = {
    "PreparePhase": "custom_components/poise/ha/phase_prepare.py",
    "ActuatePhase": "custom_components/poise/ha/phase_actuate.py",
    "ShadowPhase": "custom_components/poise/ha/phase_shadow.py",
    "ReportPhase": "custom_components/poise/ha/phase_report.py",
}
_AWAIT_FREE_PHASES = (
    "custom_components/poise/ha/phase_prepare.py",
    "custom_components/poise/ha/phase_shadow.py",
    "custom_components/poise/ha/phase_report.py",
)
_ACTUATE_MODULE = "custom_components/poise/ha/phase_actuate.py"
_COORDINATOR_TYPE = "PoiseCoordinator"
_EXECUTOR_ATTR = "_executor"

# Plan section 9: the named collaborator allowlist per class. The gate checks
# ``__slots__`` AND the ``self.x =`` assignments of ``__init__`` against these
# exact names - explicit rather than numeric, so dependency creep shows up as
# a name and not as an off-by-one.
_COLLABORATOR_ALLOWLIST: dict[str, frozenset[str]] = {
    "TickOrchestrator": frozenset(
        {
            "_runtime",
            "_reader",
            "_hass",
            "_ports",
            "_source",
            "_log",
            "_trace_recorder",
            "_trace_slug",
            "_prepare",
            "_actuate",
            "_shadow",
            "_report",
        }
    ),
    "PreparePhase": frozenset(
        {"_runtime", "_reader", "_forecast", "_hass", "_ports", "_log"}
    ),
    "ActuatePhase": frozenset({"_runtime", "_reader", "_executor", "_ports", "_log"}),
    "ShadowPhase": frozenset({"_runtime", "_reader", "_ports", "_log"}),
    "ReportPhase": frozenset({"_runtime", "_reader", "_diag", "_ports", "_log"}),
}
# Which port view each holder is allowed to reach (plan O.3 table + O.5).
_PHASE_PORT_VIEW: dict[str, tuple[str, str]] = {
    "TickOrchestrator": (_ORCHESTRATOR_MODULE, "SequencerPorts"),
    "PreparePhase": (_PHASE_MODULES["PreparePhase"], "PreparePorts"),
    "ActuatePhase": (_PHASE_MODULES["ActuatePhase"], "ActuatePorts"),
    "ShadowPhase": (_PHASE_MODULES["ShadowPhase"], "ShadowPorts"),
    "ReportPhase": (_PHASE_MODULES["ReportPhase"], "ReportPorts"),
}
# The executor awaits, split by the path they sit on (plan O.5).
_NORMAL_PATH_AWAITS = frozenset(
    {
        "run_mode_nudge",
        "run_fan_write",
        "run_setpoint_write",
        "run_ext_temp",
        "run_frost_rescue",
    }
)
_UNAVAILABLE_PATH_METHOD = "write_unavailable_safe_state"
_UNAVAILABLE_PATH_AWAITS = frozenset({"run_unavailable_safe"})


def _parse(rel_path: str) -> ast.Module:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} does not exist"
    return ast.parse(path.read_text(encoding="utf-8"))


def _name_references(rel_path: str, name: str) -> list[int]:
    """Line numbers where ``name`` is REFERENCED as an identifier: imported
    (also under ``TYPE_CHECKING``), used as a bare name, or read as an
    attribute. Mentions inside docstrings/comments are invisible - a prose
    reference is not a dependency.
    """
    tree = _parse(rel_path)
    hits: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id == name
            or isinstance(node, ast.Attribute)
            and node.attr == name
        ):
            hits.append(node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == name or alias.asname == name:
                    hits.append(node.lineno)
    return sorted(hits)


def _coordinator_module_imports(rel_path: str) -> list[int]:
    """Line numbers of any import that pulls in the ``coordinator`` module
    itself - the second way to reach the type, next to naming it."""
    tree = _parse(rel_path)
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [a.name for a in node.names]
            # ``from ..coordinator import x`` AND ``from .. import coordinator``
            # AND ``import ....coordinator`` - all three doors.
            if module.split(".")[-1] == "coordinator" or any(
                n.split(".")[-1] == "coordinator" for n in names
            ):
                hits.append(node.lineno)
    return sorted(hits)


def _awaits(rel_path: str) -> list[tuple[str, int, str]]:
    """``(enclosing function, line, awaited expression)`` for every ``await``."""
    tree = _parse(rel_path)
    out: list[tuple[str, int, str]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Await):
                out.append((fn.name, node.lineno, ast.unparse(node.value)))
    return out


def _class_node(rel_path: str, class_name: str) -> ast.ClassDef:
    tree = _parse(rel_path)
    matches = [
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name
    ]
    assert len(matches) == 1, (
        f"{rel_path}: expected exactly one class {class_name!r}, found "
        f"{len(matches)} - the O.5 table names a class that moved or was renamed."
    )
    return matches[0]


# --- (1) no coordinator backreference and no coordinator TYPE in a phase ----


def test_phase_module_coordinator_detector_is_not_vacuous() -> None:
    """Anti-vacuum control for the invariant below.

    Both matchers must still FIRE where a reference legitimately exists:
    ``ha/tick_ports.py`` is the ONE module of the tick chain that knows the
    coordinator - it holds ``self._c`` and imports the ``PoiseCoordinator``
    TYPE under ``TYPE_CHECKING``, which is exactly the form the phase rule
    forbids ("including under TYPE_CHECKING"). If either list ever came back
    empty here, the invariant below would be guarded by a matcher nothing can
    trip.
    """
    assert _self_c_accesses(_PORTS_MODULE), (
        f"{_PORTS_MODULE} no longer holds a self._c node - the self._c matcher "
        f"can no longer be shown to work."
    )
    assert _name_references(_PORTS_MODULE, _COORDINATOR_TYPE), (
        f"{_PORTS_MODULE} no longer references {_COORDINATOR_TYPE} - the name "
        f"matcher can no longer be shown to work."
    )
    assert _coordinator_module_imports(_PORTS_MODULE), (
        f"{_PORTS_MODULE} no longer imports the coordinator module - the "
        f"import matcher can no longer be shown to work."
    )


@pytest.mark.parametrize("rel_path", sorted(_PHASE_MODULES.values()))
def test_phase_modules_know_nothing_about_the_coordinator(rel_path: str) -> None:
    """Plan O.0 invariant (active from O.5): every ``ha/phase_*.py`` holds 0
    ``self._c`` accesses and 0 references to ``PoiseCoordinator``, the
    ``TYPE_CHECKING`` import included.

    The type reference is part of the rule on purpose: a phase that can NAME
    the coordinator can grow a parameter of that type, and the backreference is
    back the next time someone needs "just one more attribute". Inside the tick
    chain only ``ha/tick_ports.py`` may know it.

    "Reference" means an IDENTIFIER - an import (``TYPE_CHECKING`` included), a
    bare name, an attribute - measured on the AST. A module docstring that
    spells out the dispatch chain (``phase_actuate.py`` does, and should) names
    nothing the interpreter can reach; prose is not a dependency. The third
    door, importing the coordinator MODULE without naming the class, is closed
    separately below.
    """
    backref = _self_c_accesses(rel_path)
    assert not backref, (
        f"{rel_path} accesses self._c on line(s) {backref}. A phase reaches the "
        f"coordinator only through its own port view."
    )
    typeref = _name_references(rel_path, _COORDINATOR_TYPE)
    assert not typeref, (
        f"{rel_path} references {_COORDINATOR_TYPE} on line(s) {typeref} "
        f"(TYPE_CHECKING counts). Only ha/tick_ports.py may name the "
        f"coordinator inside the tick chain."
    )
    modref = _coordinator_module_imports(rel_path)
    assert not modref, (
        f"{rel_path} imports the coordinator module on line(s) {modref}; a "
        f"phase must not be able to reach it at all."
    )


# --- (2) the three await-free phases ----------------------------------------


def test_await_detector_is_not_vacuous() -> None:
    """Anti-vacuum control: the await matcher must find the awaits that DO
    exist, in the one phase that is allowed them and in the sequencer.
    """
    assert _awaits(_ACTUATE_MODULE), (
        f"{_ACTUATE_MODULE} reports no await at all - the matcher is broken "
        f"(this module holds all six executor awaits)."
    )
    assert _awaits(_ORCHESTRATOR_MODULE), (
        f"{_ORCHESTRATOR_MODULE} reports no await at all - the matcher is broken."
    )


@pytest.mark.parametrize("rel_path", _AWAIT_FREE_PHASES)
def test_prepare_shadow_report_are_await_free(rel_path: str) -> None:
    """Plan O.0 invariant (active from O.5): ``phase_prepare.py``,
    ``phase_shadow.py`` and ``phase_report.py`` contain 0 ``await``
    expressions.

    This is the structural half of the whole plan's premise (section 5): the
    cut follows the AWAIT TOPOLOGY, so "await-free" is not a description of
    these modules, it is their definition. An await appearing here would mean a
    suspension point inside a window whose position proofs all read "no
    suspension point exists between X and Y".
    """
    found = _awaits(rel_path)
    assert not found, (
        f"{rel_path} awaits at {[(f, ln) for f, ln, _ in found]}; this phase is "
        f"await-free by construction (plan section 5)."
    )


# --- (3) the actuation phase's await topology, semantically ------------------


def test_actuate_phase_await_topology() -> None:
    """Plan O.0 invariant (active from O.5): ``phase_actuate.py`` awaits the
    executor exactly 5 times on the normal tick path and exactly once on the
    unavailable path, and awaits nothing else.

    Formulated semantically rather than as a count of 6, because a count alone
    would not notice an await MOVED between the two paths - and the unavailable
    path is precisely the one the plan had to re-decide (Review round 4). Every
    await must be an ``self._executor.<run_*>`` call, and the named sets must
    match exactly.
    """
    normal: dict[str, list[int]] = {}
    unavailable: dict[str, list[int]] = {}
    for fn, lineno, expr in _awaits(_ACTUATE_MODULE):
        assert expr.startswith("self._executor."), (
            f"{_ACTUATE_MODULE}:{lineno} awaits {expr!r} in {fn!r}; the only "
            f"awaits allowed in the actuation phase are executor sequences."
        )
        called = expr[len("self._executor.") :].partition("(")[0]
        bucket = unavailable if fn == _UNAVAILABLE_PATH_METHOD else normal
        bucket.setdefault(called, []).append(lineno)

    assert set(normal) == set(_NORMAL_PATH_AWAITS), (
        f"normal-path executor awaits are {sorted(normal)}, expected "
        f"{sorted(_NORMAL_PATH_AWAITS)}."
    )
    assert set(unavailable) == set(_UNAVAILABLE_PATH_AWAITS), (
        f"unavailable-path executor awaits are {sorted(unavailable)}, expected "
        f"{sorted(_UNAVAILABLE_PATH_AWAITS)} (inside "
        f"{_UNAVAILABLE_PATH_METHOD!r})."
    )
    multiples = {k: v for k, v in {**normal, **unavailable}.items() if len(v) != 1}
    assert not multiples, (
        f"an executor sequence is awaited more than once: {multiples}. Each "
        f"segment dispatches exactly once per tick."
    )


# --- (4) executor capability narrowing --------------------------------------

_EXECUTOR_FREE_MODULES = (
    _ORCHESTRATOR_MODULE,
    "custom_components/poise/ha/phase_prepare.py",
    "custom_components/poise/ha/phase_shadow.py",
    "custom_components/poise/ha/phase_report.py",
)


def test_executor_detector_is_not_vacuous() -> None:
    """Anti-vacuum control: the text matcher must find ``_executor`` where it
    legitimately lives - in the actuation phase (holder) and in
    ``coordinator.py`` (the composition root, which may create and wire it).
    """
    assert _count_in_file(_ACTUATE_MODULE, _EXECUTOR_ATTR) > 0, (
        f"{_ACTUATE_MODULE} contains no '{_EXECUTOR_ATTR}' - the matcher is "
        f"broken, or the executor left the one class that may hold it."
    )
    assert _count_in_file(_COORDINATOR_MODULE, _EXECUTOR_ATTR) > 0, (
        f"{_COORDINATOR_MODULE} contains no '{_EXECUTOR_ATTR}' - the "
        f"composition root no longer builds the executor?"
    )


@pytest.mark.parametrize("rel_path", _EXECUTOR_FREE_MODULES)
def test_executor_capability_is_narrowed_to_the_actuation_phase(
    rel_path: str,
) -> None:
    """Plan O.0 invariant (active from O.5): 0 occurrences of ``_executor`` in
    ``tick_orchestrator.py``, ``phase_prepare.py``, ``phase_shadow.py`` and
    ``phase_report.py``.

    Deliberately a TEXT count, not an AST attribute count: a constructor
    parameter named ``actuator_executor``, a stored field, or a type import
    would each be a way back to the writer, and only the raw token catches all
    three. A module that cannot mention the executor cannot write to the
    device - the dependency direction then carries the same cut as the await
    topology, which is the whole argument of plan section 9.
    ``coordinator.py`` is exempt as the composition root and is the positive
    control above.
    """
    hits = _count_in_file(rel_path, _EXECUTOR_ATTR)
    assert hits == 0, (
        f"{rel_path} mentions '{_EXECUTOR_ATTR}' {hits} time(s). Within the "
        f"tick execution only ActuatePhase may hold or name the "
        f"ActuatorExecutor (plan section 9)."
    )


# --- (5) constructor fields / __slots__ against the named allowlist ---------


def _declared_collaborators(
    rel_path: str, class_name: str
) -> tuple[set[str], set[str]]:
    """``(slots, fields assigned in __init__)`` for one class, read as text."""
    node = _class_node(rel_path, class_name)
    slots: set[str] = set()
    for stmt in node.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__slots__"
        ):
            assert isinstance(stmt.value, (ast.Tuple, ast.List)), (
                f"{rel_path}:{class_name}.__slots__ is not a literal tuple/list, "
                f"so it cannot be read statically."
            )
            for elt in stmt.value.elts:
                assert isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                slots.add(elt.value)
    init = [
        s
        for s in node.body
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))
        and s.name == "__init__"
    ]
    assert len(init) == 1, f"{rel_path}:{class_name} has no single __init__"
    fields = {
        t.attr
        for stmt in ast.walk(init[0])
        for t in (
            stmt.targets
            if isinstance(stmt, ast.Assign)
            else [stmt.target]
            if isinstance(stmt, ast.AnnAssign)
            else []
        )
        if isinstance(t, ast.Attribute)
        and isinstance(t.value, ast.Name)
        and t.value.id == "self"
    }
    return slots, fields


def test_collaborator_allowlist_detector_is_not_vacuous() -> None:
    """Anti-vacuum control: the reader must actually return names, and the
    allowlist must not be trivially satisfiable by an empty class.
    """
    slots, fields = _declared_collaborators(
        _PHASE_MODULES["ActuatePhase"], "ActuatePhase"
    )
    assert slots and fields, "the __slots__/__init__ reader returned nothing"
    assert _EXECUTOR_ATTR in slots and _EXECUTOR_ATTR in fields, (
        "ActuatePhase no longer declares the executor it is defined by - the "
        "reader is looking at the wrong class."
    )


@pytest.mark.parametrize("class_name", sorted(_COLLABORATOR_ALLOWLIST))
def test_class_collaborators_match_the_named_allowlist(class_name: str) -> None:
    """Plan O.0 invariant (active from O.5): the ``__slots__`` and the
    ``__init__`` fields of each tick class are EXACTLY the names plan section 9
    allows it.

    Explicit names, not a count: the point is that ``_executor`` exists only on
    ``ActuatePhase``, ``_diag`` only on ``ReportPhase``, ``_forecast`` only on
    ``PreparePhase``. Both directions fail - an added collaborator (dependency
    creep) and a removed one (a stale table row).
    """
    rel_path = (
        _ORCHESTRATOR_MODULE
        if class_name == "TickOrchestrator"
        else _PHASE_MODULES[class_name]
    )
    allowed = set(_COLLABORATOR_ALLOWLIST[class_name])
    slots, fields = _declared_collaborators(rel_path, class_name)
    assert slots == allowed, (
        f"{rel_path}:{class_name}.__slots__ is {sorted(slots)}, the plan's "
        f"allowlist is {sorted(allowed)}."
    )
    assert fields == allowed, (
        f"{rel_path}:{class_name}.__init__ assigns {sorted(fields)}, the plan's "
        f"allowlist is {sorted(allowed)}."
    )


# --- (6) each holder calls only the port methods of its own view ------------


def _ports_calls(rel_path: str) -> set[str]:
    """Every ``self._ports.<name>`` attribute reached in one module."""
    tree = _parse(rel_path)
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "_ports"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    }


def test_ports_call_detector_is_not_vacuous() -> None:
    """Anti-vacuum control: the ``self._ports.<x>`` matcher must return the
    real call set for a module known to use several ports.
    """
    found = _ports_calls(_ORCHESTRATOR_MODULE)
    assert len(found) >= 5, (
        f"the port-call matcher found only {sorted(found)} in "
        f"{_ORCHESTRATOR_MODULE}; it is supposed to see the sequencer's eight."
    )


@pytest.mark.parametrize("class_name", sorted(_PHASE_PORT_VIEW))
def test_each_holder_calls_only_its_own_port_view(class_name: str) -> None:
    """Plan O.0 invariant (active from O.5): every module reaches exactly the
    ports of ITS view - no more (a widened capability) and no fewer (a dead
    port in the adapter).

    This is what the five-way split buys: ``ShadowPhase`` cannot call
    ``commit_execution``, and ``commit_execution`` sits in ``ActuatePorts``
    alone. The equality direction matters too - the views were MEASURED from
    these call sites, so an unused port means the measurement went stale.
    """
    rel_path, view = _PHASE_PORT_VIEW[class_name]
    used = _ports_calls(rel_path)
    expected = set(_PORT_VIEWS[view])
    assert used == expected, (
        f"{rel_path} calls {sorted(used)} on self._ports; {view} declares "
        f"{sorted(expected)}. Extra names are a widened capability, missing "
        f"ones a dead port."
    )


# --- (7) the expected module list, and the end of the transitional view -----


def test_phase_modules_exist_and_the_transitional_union_is_gone() -> None:
    """Plan O.0 invariant (active from O.5): the four phase modules exist, each
    declaring its one class, and ``MonolithTickPorts`` exists nowhere.

    The union view was explicitly transitional (plan O.3): it existed only
    because one class still held methods of all five capability groups. Once
    the split lands it is the single easiest way to undo the whole step - one
    annotation, and every holder can reach every port again.
    """
    for class_name, rel_path in sorted(_PHASE_MODULES.items()):
        assert (REPO_ROOT / rel_path).is_file(), f"{rel_path} is missing"
        _class_node(rel_path, class_name)  # exactly one, or it raises

    sources = sorted((REPO_ROOT / "custom_components").rglob("*.py"))
    assert sources, "no component sources found - this check would be vacuous"
    leftovers = [
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in sources
        if "MonolithTickPorts" in p.read_text(encoding="utf-8")
    ]
    assert not leftovers, (
        f"MonolithTickPorts still appears in {leftovers}; the transitional "
        f"union of the five port views ends with O.5."
    )


# --- enforced structural invariants, active from O.6 ------------------------
#
# The outcome-diag fold split. ONE shared rule instead of six ratchet rows,
# and the reasoning is worth writing down because the table's habit is a row
# per target:
#
#   * the plan states the O.6 size target as a CLASS rule ("every fold <= 80
#     code / 110 total"), not as six numbers. Six frozen rows would enforce
#     six snapshots and would NOT notice a seventh fold appearing at 200
#     lines; the rule below reads the folds off the AST, so a new one is
#     covered the moment it exists;
#   * the folds are new code with no lowering step, so ratchet rule 2
#     ("baseline tracks a real shrink") has nothing to track for them - only
#     rule 1, the cap, carries meaning, and that is exactly what this is;
#   * aggregate growth is still capped: the phase_report.py file row absorbed
#     the +64/+21 and holds the 1200/900 module cap, and the dispatcher keeps
#     its own one-way row at 60/40. Together with the cap below that is the
#     coverage six rows would have given;
#   * and it pins something no size row can express: every fold is called
#     from inside the ONE ``safe_collect`` closure and from nowhere else.
#     That is the structural half of "O.6 did not move the error boundary" -
#     a fold reachable from outside the closure would be an entry point
#     outside the try. The behavioural half is
#     ``tests/integration/test_o6_outcome_folds.py``, which injects a fault
#     into each fold and pins the degradation.
#
# The exact name tuple is part of the rule: adding, renaming or removing a
# fold must be a deliberate edit here, not a silent one.

_REPORT_MODULE = _PHASE_MODULES["ReportPhase"]
_OUTCOME_CLOSURE = "_collect_outcome_diag"
_OUTCOME_FOLDS: tuple[str, ...] = (
    "_fold_hdh_and_outcome",
    "_fold_regulation_quality",
    "_fold_tier2_activation",
    "_fold_tier2_inputs",
    "_fold_reference_offset",
    "_fold_tau_settle",
)
# Plan O.6 target sizes, binding for every fold from this step on.
_FOLD_CEILING_TOTAL = 110
_FOLD_CEILING_CODE = 80


def _fold_methods(rel_path: str) -> tuple[str, ...]:
    """The ``_fold_*`` methods ``ReportPhase`` declares, in SOURCE order.

    Read off the class body (not ``ast.walk``) so the order is the file's own
    and a nested helper cannot masquerade as a fold.
    """
    return tuple(
        stmt.name
        for stmt in _class_node(rel_path, "ReportPhase").body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        and stmt.name.startswith("_fold_")
    )


def _fold_references(node: ast.AST) -> list[tuple[str, int]]:
    """``(fold name, line)`` for every ``self._fold_*`` reached under ``node``."""
    return sorted(
        (n.attr, n.lineno)
        for n in ast.walk(node)
        if isinstance(n, ast.Attribute)
        and n.attr.startswith("_fold_")
        and isinstance(n.value, ast.Name)
        and n.value.id == "self"
    )


def test_outcome_fold_set_is_exactly_the_declared_one() -> None:
    """Plan O.0 invariant (active from O.6): ``ReportPhase`` declares exactly
    the six named folds, in text order.

    This is the anti-vacuum control for the two checks below - both iterate
    the discovered folds, so an empty or wrong discovery would make them
    green for free - and at the same time the deliberate-change gate: the
    tuple above is the plan's fold list, and editing it is the review.
    """
    assert _fold_methods(_REPORT_MODULE) == _OUTCOME_FOLDS


@pytest.mark.parametrize("fold", _OUTCOME_FOLDS)
def test_each_outcome_fold_stays_under_the_per_fold_cap(fold: str) -> None:
    """Plan O.6 target, now binding: no fold above 80 code / 110 total lines.

    A cap rather than a frozen measurement, because these methods have no
    lowering step - the risk they guard against is one of them growing back
    into the 228-code-line monolith O.6 took apart.
    """
    total, code = _measure(f"{_REPORT_MODULE}::{fold}")
    assert code <= _FOLD_CEILING_CODE, (
        f"{fold}: {code} code lines, plan O.6 caps a fold at "
        f"{_FOLD_CEILING_CODE}. Split it further along a state seam - do not "
        f"raise the cap."
    )
    assert total <= _FOLD_CEILING_TOTAL, (
        f"{fold}: {total} total lines, plan O.6 caps a fold at "
        f"{_FOLD_CEILING_TOTAL} (code metric is the complexity signal, plan "
        f"section 18.5 - but this one is a drift signal and it moved)."
    )


def test_every_outcome_fold_is_called_only_inside_the_collector_closure() -> None:
    """Plan O.0 invariant (active from O.6): every ``self._fold_*`` call sits
    inside ``_collect_outcome_diag``, each exactly once.

    THE structural statement of O.6. The folds hold the state updates that
    used to run inside ``DiagnosticsCollector.safe_collect``'s single ``try``;
    a call site outside that closure would be a second entry point OUTSIDE
    the error boundary, and the degradation contract (fold N fails -> defaults
    stand, folds N+1.. are skipped) would no longer describe the code.
    Measured as (name, line) pairs, so a second call to the same fold shows up
    even though the name set would still look right.
    """
    tree = _parse(_REPORT_MODULE)
    closures = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == _OUTCOME_CLOSURE
    ]
    assert len(closures) == 1, (
        f"{_REPORT_MODULE}: expected exactly one {_OUTCOME_CLOSURE!r}, found "
        f"{len(closures)} - the ONE collector closure is the boundary."
    )

    module_wide = _fold_references(tree)
    in_closure = _fold_references(closures[0])
    assert [name for name, _ in in_closure] == sorted(_OUTCOME_FOLDS), (
        f"the closure calls {[n for n, _ in in_closure]}; the declared folds "
        f"are {sorted(_OUTCOME_FOLDS)} and each must be called exactly once."
    )
    assert module_wide == in_closure, (
        f"a fold is referenced outside {_OUTCOME_CLOSURE!r}: "
        f"{sorted(set(module_wide) - set(in_closure))}. Every fold runs inside "
        f"the one safe_collect boundary or the degradation contract breaks."
    )


# --- enforced structural invariants, active from P.1 ------------------------
#
# The pure-pipeline split (docs/Konzepte/2026-08-17_Split-Plan_tick-pipeline.md,
# section 7b). Section 7 of that plan separates two proofs that Rev. 2 had
# conflated, and the separation is the reason this block looks the way it does:
#
#   * 7a, the MIGRATION proof, compared ast.dump() of all 15 functions against
#     the parent commit and read the full diff for the comments ast.dump cannot
#     see. It ran once, in the P.1 commit, and is deliberately NOT left behind
#     as a test: the same commit deletes control/tick_pipeline.py, so a later
#     run would have no "before" to compare against. A test that compares a
#     deleted state is a ruin, not a gate.
#   * 7b, THIS block, conserves what outlives the move: the PARTITION. Which
#     pure stage lives in which module, that the three sets are disjoint, that
#     together they are still exactly the fifteen functions the old file held,
#     and that the old file is gone with nothing importing it.
#
# Checked as EQUALITY per module, never as a subset - the failure this guards
# against is a function drifting into the wrong module or appearing in two,
# and a subset check sees neither. Same construction as the O.5 port-view gate.

_PIPELINE_MODULES: dict[str, str] = {
    "pipeline_prepare": "custom_components/poise/control/pipeline_prepare.py",
    "pipeline_actuate": "custom_components/poise/control/pipeline_actuate.py",
    "pipeline_finalize": "custom_components/poise/control/pipeline_finalize.py",
}
# The module P.1 deleted. Named here because "it is gone" is an invariant, not
# a one-off cleanup: a compatibility re-export would restore the old
# aggregation point and become the preferred import path again on the next
# change (split plan section 6, step 4).
_DELETED_PIPELINE_MODULE = "custom_components/poise/control/tick_pipeline.py"
_PIPELINE_MODULE_NAME = "tick_pipeline"
_GUARDED_STAGE = "_stage_observe_guarded"

# The cut of split plan section 3, following the real consumers: PreparePhase,
# ActuatePhase, and the sequencer seam that builds the FinalizeContext.
_PIPELINE_PARTITION: dict[str, frozenset[str]] = {
    "pipeline_prepare": frozenset(
        {
            "evaluate_health_issues",
            "stage_ingest",
            "learn_step",
            "observe_window_auto",
            "observe_seasonless",
            "stage_observe",
            _GUARDED_STAGE,
            "stage_safety_floors",
            "stage_schedule_gate",
            "stage_comfort_solve",
            "stage_intents",
        }
    ),
    "pipeline_actuate": frozenset(
        {
            "stage_mode_resolution",
            "stage_setpoint_observe",
            "plan_setpoint_write",
        }
    ),
    "pipeline_finalize": frozenset({"build_finalize_context"}),
}

# The fifteen functions control/tick_pipeline.py held at 0ab7a174, the commit
# P.1 was cut from. Written out independently instead of being derived from the
# table above: if the union were computed FROM the partition, a function
# dropped out of a module would also silently vanish from what the union is
# compared against, and the completeness check would pass on a smaller world.
_PIPELINE_FUNCTIONS_BEFORE_SPLIT: frozenset[str] = frozenset(
    {
        "evaluate_health_issues",
        "stage_ingest",
        "learn_step",
        "observe_window_auto",
        "observe_seasonless",
        "stage_observe",
        "_stage_observe_guarded",
        "stage_safety_floors",
        "stage_schedule_gate",
        "stage_comfort_solve",
        "stage_intents",
        "stage_mode_resolution",
        "stage_setpoint_observe",
        "plan_setpoint_write",
        "build_finalize_context",
    }
)


def _module_functions_from(tree: ast.Module) -> frozenset[str]:
    """Names of the functions a module declares AT TOP LEVEL.

    Read off ``tree.body`` rather than ``ast.walk`` on purpose: a nested
    helper or a method is not a module-level stage, and counting one would let
    a function "move" into a module by being hidden inside another.
    """
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _module_imports(tree: ast.Module, module_name: str) -> list[int]:
    """Line numbers of every import that reaches the module ``module_name``.

    All three doors, the same enumeration ``_coordinator_module_imports`` uses:
    ``from x.<name> import sym``, ``from x import <name>`` and
    ``import a.b.<name>``.
    """
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [a.name for a in node.names]
            if module.split(".")[-1] == module_name or any(
                n.split(".")[-1] == module_name for n in names
            ):
                hits.append(node.lineno)
    return sorted(hits)


def _component_sources() -> list[Path]:
    sources = sorted((REPO_ROOT / "custom_components").rglob("*.py"))
    assert sources, "no component sources found - this scan would be vacuous"
    return sources


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


# Synthetic sources for the two anti-vacuum controls below. Self-contained on
# purpose (the pattern of ``test_noqa_detector_is_not_vacuous``): a control
# that points at a real file rots the moment that file is cleaned up, and then
# leaves a zero-assertion guarded by a matcher nothing can trip.
_FUNCTION_READER_PROBE = """
def top_level_stage() -> None:
    def nested_helper() -> None:
        pass


class Holder:
    def method(self) -> None:
        pass
"""
_IMPORT_PROBE = """
from ..control import tick_pipeline as _pipeline
from ..control.tick_pipeline import plan_setpoint_write
import custom_components.poise.control.tick_pipeline
from ..control import pipeline_prepare as _prepare
from ..control.pipeline_actuate import stage_mode_resolution
"""


def test_pipeline_function_reader_is_not_vacuous() -> None:
    """Anti-vacuum control for the partition checks: the reader must return
    the top-level functions and ONLY those.

    Both halves matter. If it returned nothing, every equality below would
    reduce to "declared set == empty set" and fail loudly - but if it returned
    too much (nested defs, methods) the equalities would fail for the wrong
    reason and get "fixed" by widening the table.
    """
    assert _module_functions_from(ast.parse(_FUNCTION_READER_PROBE)) == frozenset(
        {"top_level_stage"}
    )
    for rel_path in sorted(_PIPELINE_MODULES.values()):
        assert _module_functions_from(_parse(rel_path)), (
            f"{rel_path} reports no top-level function at all - the reader is "
            f"broken, or the module was emptied."
        )


def test_deleted_module_import_detector_is_not_vacuous() -> None:
    """Anti-vacuum control for the "nothing imports it" invariant.

    The invariant below is a count-is-zero assertion, so it goes green for free
    the moment the matcher stops matching. Here the matcher is shown to fire on
    all three import forms - and to leave the two sibling modules alone, so a
    matcher that simply says "yes" to everything fails too.
    """
    tree = ast.parse(_IMPORT_PROBE)
    hits = _module_imports(tree, _PIPELINE_MODULE_NAME)
    assert len(hits) == 3, (
        f"the import matcher found {len(hits)} of the three tick_pipeline "
        f"import forms in the probe (lines {hits})."
    )
    assert _module_imports(tree, "pipeline_prepare") == [5]
    assert _module_imports(tree, "pipeline_actuate") == [6]
    assert not _module_imports(tree, "no_such_module")


@pytest.mark.parametrize("module", sorted(_PIPELINE_MODULES))
def test_pipeline_module_declares_exactly_its_partition(module: str) -> None:
    """Split plan section 7b: each of the three modules declares EXACTLY the
    functions the plan assigned it.

    Equality in both directions. An extra name means a stage landed in the
    wrong module (or a new helper grew to module level unreviewed); a missing
    one means the module lost a stage the rest of the chain still routes
    through. Editing this table is the review.
    """
    declared = _module_functions_from(_parse(_PIPELINE_MODULES[module]))
    assert declared == _PIPELINE_PARTITION[module], (
        f"{_PIPELINE_MODULES[module]} declares {sorted(declared)}; the split "
        f"plan assigns it {sorted(_PIPELINE_PARTITION[module])}."
    )


def test_pipeline_partition_is_complete_and_disjoint() -> None:
    """Split plan section 7b: the three modules PARTITION the old fifteen.

    Three statements, and all three are needed. The union must be the pre-split
    set (nothing lost, nothing invented), the pairwise intersections must be
    empty (no function in two modules), and the memberships must sum to the
    size of the union (the arithmetic restatement, which catches a duplicate
    inside one frozenset that set semantics would swallow).
    """
    union: set[str] = set()
    for names in _PIPELINE_PARTITION.values():
        union |= set(names)
    assert union == set(_PIPELINE_FUNCTIONS_BEFORE_SPLIT), (
        f"the partition covers {sorted(union)}; control/tick_pipeline.py held "
        f"{sorted(_PIPELINE_FUNCTIONS_BEFORE_SPLIT)}."
    )
    assert len(_PIPELINE_FUNCTIONS_BEFORE_SPLIT) == 15
    assert sum(len(n) for n in _PIPELINE_PARTITION.values()) == len(union)

    modules = sorted(_PIPELINE_PARTITION)
    for i, first in enumerate(modules):
        for second in modules[i + 1 :]:
            overlap = _PIPELINE_PARTITION[first] & _PIPELINE_PARTITION[second]
            assert not overlap, (
                f"{first} and {second} both claim {sorted(overlap)}; the three "
                f"modules are a partition, not three overlapping views."
            )


def test_the_old_pipeline_module_is_gone_and_nothing_imports_it() -> None:
    """Split plan section 6 step 4 / section 7b: ``control/tick_pipeline.py``
    does not exist, and no production module imports it.

    Both halves, because they fail differently. The file check catches the
    obvious restoration; the import scan catches the subtler one - a
    compatibility shim under a new name that re-exports the fifteen functions
    would conserve the aggregation point the split removed and would become the
    preferred import path again at the next change. Prose is deliberately NOT
    matched: the three new modules name their origin in their docstrings, and a
    provenance note is not a dependency (same rule as ``_name_references``).
    """
    assert not (REPO_ROOT / _DELETED_PIPELINE_MODULE).exists(), (
        f"{_DELETED_PIPELINE_MODULE} is back. P.1 partitioned it into "
        f"{sorted(_PIPELINE_MODULES.values())} and deleted it; no "
        f"compatibility re-export is sanctioned."
    )
    importers = {
        _rel(path): hits
        for path in _component_sources()
        if (
            hits := _module_imports(
                ast.parse(path.read_text(encoding="utf-8")), _PIPELINE_MODULE_NAME
            )
        )
    }
    assert not importers, (
        f"production code still imports {_PIPELINE_MODULE_NAME}: {importers}. "
        f"The pure stages are reached through pipeline_prepare / "
        f"pipeline_actuate / pipeline_finalize."
    )


def test_guarded_observe_stage_exists_exactly_once_in_prepare() -> None:
    """Split plan section 7b: ``_stage_observe_guarded`` is defined exactly
    once in the whole component, and it is in ``pipeline_prepare.py``.

    P.1 MOVED this function, it did not split it - that question is P.2's, with
    two sanctioned answers. Until then the one thing that must stay true is
    that there is exactly one of it: a second copy (a "temporary" variant left
    behind during the P.2 analysis) would double the swallowing log boundary
    the ratchet row above is measuring. Searched with ``ast.walk``, so a nested
    or method-level second definition counts too.
    """
    found = [
        (_rel(path), node.lineno)
        for path in _component_sources()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == _GUARDED_STAGE
    ]
    assert len(found) == 1, (
        f"{_GUARDED_STAGE} is defined {len(found)} time(s): {found}. Exactly "
        f"one definition, in pipeline_prepare.py."
    )
    assert found[0][0] == _PIPELINE_MODULES["pipeline_prepare"], (
        f"{_GUARDED_STAGE} lives in {found[0][0]}; the split plan puts the "
        f"whole observe family in {_PIPELINE_MODULES['pipeline_prepare']}."
    )


# --- structural invariants (activation-gated, plan O.0 section 6) ----------


@dataclass(frozen=True)
class _PendingInvariant:
    """A structural invariant from the plan that is not yet enforced because
    the step making it satisfiable hasn't been reached. Turning one on, once
    its step lands, means implementing the actual AST/grep check as a real
    test in this file - this table entry alone is not the enforcement, only
    the anti-silent-skip guard below is.
    """

    description: str
    active_from: str


_STRUCTURE_INVARIANTS: tuple[_PendingInvariant, ...] = (
    # This table is EMPTY as of O.5, and that is the point: every structural
    # invariant the plan tabled is now an enforced check in this file.
    #   O.2 -> test_tick_config_snapshot_carries_no_entity_id_field
    #          test_snapshot_classes_have_no_mutable_sequence_field
    #   O.3 -> test_tick_orchestrator_has_no_coordinator_backreference
    #   O.4 -> test_coordinator_has_no_noqa_f401_reexports
    #          test_coordinator_globals_proxy_is_gone
    #   O.5 -> test_phase_modules_know_nothing_about_the_coordinator
    #          test_prepare_shadow_report_are_await_free
    #          test_actuate_phase_await_topology
    #          test_executor_capability_is_narrowed_to_the_actuation_phase
    #          test_class_collaborators_match_the_named_allowlist
    #          test_each_holder_calls_only_its_own_port_view
    #          test_phase_modules_exist_and_the_transitional_union_is_gone
    #   O.6 -> test_outcome_fold_set_is_exactly_the_declared_one
    #          test_each_outcome_fold_stays_under_the_per_fold_cap
    #          test_every_outcome_fold_is_called_only_inside_the_collector_closure
    # A future step that tables a not-yet-satisfiable invariant adds its row
    # here; the guard below then holds it to its activation step.
)


def test_current_step_is_a_known_step() -> None:
    """``_CURRENT_STEP`` must name a real step, because everything else keys
    off it: a typo would silently empty ``_ACTIVE_STEPS`` and disarm the
    anti-silent-skip guard below.

    Deliberately NOT pinned to one specific step - the guard below already
    enforces, for every step, that no reached invariant is left as an inert
    placeholder row. A second assertion naming a single step would have to be
    rewritten on every bump without adding coverage.
    """
    assert _CURRENT_STEP in _STEP_ORDER
    assert _ACTIVE_STEPS[-1] == _CURRENT_STEP


@pytest.mark.parametrize(
    "inv",
    _STRUCTURE_INVARIANTS,
    ids=[i.description for i in _STRUCTURE_INVARIANTS],
)
def test_pending_invariant_not_silently_skipped(inv: _PendingInvariant) -> None:
    """Anti-silent-skip guard: every deactivated invariant must name an
    ``active_from`` step that has genuinely not been reached yet. If
    ``_CURRENT_STEP`` is bumped past a row's ``active_from`` without that
    row's check being implemented as a real, enforced test, this assertion
    catches the omission instead of letting the row rot into dead
    documentation.
    """
    assert inv.active_from in _STEP_ORDER, (
        f"invariant {inv.description!r} names an unknown step "
        f"{inv.active_from!r}; fix the typo against _STEP_ORDER={_STEP_ORDER!r}."
    )
    assert inv.active_from not in _ACTIVE_STEPS, (
        f"invariant {inv.description!r} is tabled as "
        f"active_from={inv.active_from!r}, but _CURRENT_STEP={_CURRENT_STEP!r} "
        f"has already reached it (_ACTIVE_STEPS={_ACTIVE_STEPS!r}). This "
        f"invariant must now be implemented as an enforced check in this "
        f"file, not left as an inert placeholder row."
    )


# --- orphan-module guard: catch upload debris generically -------------------

# Every module of the component must be reachable by an import from another
# module - unless it is on this list, which names WHY it is not.
#
# Motivation, from a real failure: P.1 deleted control/tick_pipeline.py, but
# the GitHub tree is maintained by web upload, which adds files and does not
# delete them. The old aggregate module therefore survived there and CI went
# red on the P.1 gate. That gate is specific to one filename; this one is the
# general form. A stale module is not merely dead weight - it is exactly the
# "compatibility shim" the split forbade, and the next change may well import
# from it again.
_HA_ENTRY_POINTS = frozenset(
    {
        # Home Assistant imports these BY NAME from the component package;
        # nothing in the package imports them, and that is correct.
        "__init__",
        "climate",
        "sensor",
        "binary_sensor",
        "switch",
        "button",
        "config_flow",
        "repairs",
        "diagnostics.entry",
    }
)

# Modules that are deliberately not wired yet. Each names its ADR, so the entry
# is a decision on record rather than a place to hide forgotten code.
_UNWIRED_BY_DESIGN: dict[str, str] = {
    "pipeline": (
        "ADR-0006/0014 reference tick skeleton - exercised by the pure core "
        "and the closed-loop harness, deliberately not the production path"
    ),
    "control.calibration": (
        "ADR-0015 TRV calibration - implemented ahead of its wiring, covered "
        "by tests/test_calibration.py"
    ),
    "multi.schema": (
        "ADR-0046 section 12 capability-driven field selection - implemented "
        "ahead of its wiring"
    ),
}


def _component_module_graph() -> tuple[dict[str, Path], set[str]]:
    """Return (module name -> path, set of module names imported by someone)."""
    root = REPO_ROOT / "custom_components" / "poise"
    modules = {
        ".".join(p.relative_to(root).with_suffix("").parts): p
        for p in sorted(root.rglob("*.py"))
        if "__pycache__" not in p.parts
    }
    imported: set[str] = set()
    for name, path in modules.items():
        package = name.rsplit(".", 1)[0] if "." in name else ""
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom):
                if node.level:  # relative
                    base = package.split(".") if package else []
                    if node.level > 1:
                        base = base[: len(base) - (node.level - 1)]
                    tail = node.module.split(".") if node.module else []
                    resolved = ".".join([*base, *tail]).strip(".")
                elif (node.module or "").startswith("custom_components.poise"):
                    resolved = (node.module or "")[len("custom_components.poise.") :]
                else:
                    continue
                targets.append(resolved)
                # `from .pkg import module` also imports pkg.module
                targets += [
                    f"{resolved}.{a.name}" if resolved else a.name for a in node.names
                ]
            elif isinstance(node, ast.Import):
                targets += [
                    a.name[len("custom_components.poise.") :]
                    for a in node.names
                    if a.name.startswith("custom_components.poise.")
                ]
            imported.update(t for t in targets if t in modules)
    return modules, imported


def test_no_orphan_module_in_the_component() -> None:
    """No module is unreachable, so upload debris cannot sit in the tree.

    A file that nothing imports and that is not a declared entry point or a
    declared unwired module is either dead code or a leftover. Both are
    findings; neither should be able to arrive quietly.
    """
    modules, imported = _component_module_graph()
    packages = {m for m in modules if m.endswith("__init__")}
    orphans = sorted(
        set(modules) - imported - _HA_ENTRY_POINTS - set(_UNWIRED_BY_DESIGN) - packages
    )
    assert not orphans, (
        f"module(s) nothing imports: {orphans}. Either they are leftovers (a "
        f"deleted file that came back, e.g. through a web upload that adds but "
        f"never removes) - then delete them - or they are intentional, and then "
        f"they belong in _UNWIRED_BY_DESIGN with their ADR."
    )


def test_orphan_detector_is_not_vacuous() -> None:
    """The detector must actually resolve imports.

    Without this, a broken resolver would report "no orphans" for every tree,
    including one full of debris. Positive control: the three declared unwired
    modules exist and really are unimported - if the resolver started matching
    everything, this set would come back empty.
    """
    modules, imported = _component_module_graph()
    assert len(modules) > 100, f"only {len(modules)} modules found - resolver broken?"
    assert len(imported) > 50, f"only {len(imported)} imports resolved - too few"
    for name, reason in _UNWIRED_BY_DESIGN.items():
        assert name in modules, f"{name} is listed as unwired but does not exist"
        assert name not in imported, (
            f"{name} is listed as unwired but IS imported now - remove the "
            f"exemption ({reason})"
        )
