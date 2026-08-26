"""Phase-module invariants (plans O.5/O.6), one of six structure gates.

The four ``ha/phase_*.py`` modules: no coordinator type or backreference, the
await topology (three await-free phases, one actuation phase whose awaits are
named), the executor capability narrowed to that one phase, the named
collaborator allowlist per class, each holder calling only its own port view,
and the outcome-fold decomposition of the report phase.
"""

from __future__ import annotations

import ast

import pytest

from tests.structure_support import (
    _COORDINATOR_MODULE,
    _ORCHESTRATOR_MODULE,
    _PORT_VIEWS,
    _PORTS_MODULE,
    REPO_ROOT,
    _count_in_file,
    _measure,
    _parse,
    _self_c_accesses,
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
        "run_calibration",
        "run_frost_rescue",
    }
)


# P1.4 exception to "each sequence awaited exactly once": ``run_calibration``
# is ONE boundary dispatched at exactly TWO mutually exclusive sites — the
# segment-H restore (ownership handoff, D3) and the segment-W regulation
# write (live calibration path). A third site would be an unreviewed dispatch.
_NORMAL_PATH_AWAIT_COUNTS: dict[str, int] = {"run_calibration": 2}


_UNAVAILABLE_PATH_METHOD = "write_unavailable_safe_state"


_UNAVAILABLE_PATH_AWAITS = frozenset({"run_unavailable_safe"})


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
        f"(this module holds all eight executor awaits)."
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
    executor exactly 7 times on the normal tick path (P1.4: ``run_calibration``
    at its two sanctioned sites) and exactly once on the
    unavailable path, and awaits nothing else.

    Formulated semantically rather than as a count of 8, because a count alone
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
    multiples = {
        k: v
        for k, v in {**normal, **unavailable}.items()
        if len(v) != _NORMAL_PATH_AWAIT_COUNTS.get(k, 1)
    }
    assert not multiples, (
        f"an executor sequence is awaited at an unreviewed number of sites: "
        f"{multiples}. Each segment dispatches exactly once per tick "
        f"(sanctioned exceptions: {_NORMAL_PATH_AWAIT_COUNTS})."
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
