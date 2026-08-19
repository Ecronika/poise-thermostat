"""The gate's own honesty (plans O.0/S.2), one of six structure gates.

Two rules that are about the RULES rather than about the code: the refactor
step must be a known one and no invariant may sit silently deactivated, and
no module of the component may become an orphan - the generic catch for the
upload debris that once put a deleted module back into the tree.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.structure_support import (
    _ACTIVE_STEPS,
    _CURRENT_STEP,
    _STEP_ORDER,
    REPO_ROOT,
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
