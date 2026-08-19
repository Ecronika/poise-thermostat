"""Pipeline partition (plan P.1), one of six structure gates.

Not a size rule: it pins WHICH stage lives in WHICH of the three
``control/pipeline_*`` modules - the part of a mechanical move that survives
the move - plus the guarded observe stage and the proof that the old
aggregate module is gone with nothing importing it. Full spec:
``docs/Konzepte/2026-08-17_Split-Plan_tick-pipeline.md``.
"""

from __future__ import annotations

import ast

import pytest

from tests.structure_support import (
    REPO_ROOT,
    _component_sources,
    _parse,
    _rel,
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
