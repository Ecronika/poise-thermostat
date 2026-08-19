"""Port and backreference invariants (plans O.3/O.4), one of six gates.

The coordinator backreference (``self._c``) and its patch-surface twin
(``self._g``): who may still hold one, what the port adapter may expose, and
that the transitional re-export proxy is gone. Each detector carries its own
anti-vacuum control - a matcher that finds nothing everywhere looks exactly
like a codebase that is clean everywhere.
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
    _component_sources,
    _count_in_file,
    _parse,
    _rel,
    _self_attr_accesses,
    _self_c_accesses,
)

# The ONE module that keeps a coordinator reference by design: the port
# adapter of plan O.3 (``CoordinatorTickPorts``, ``__slots__ = ("_c",)``) — it
# exists precisely to be the single place that knows the coordinator, and
# ``test_port_adapter_is_not_a_service_locator`` below pins what it may expose.
# Since S.3 (the health reporter gave its backreference up) it is also the only
# one, which lets ONE test carry both jobs: the invariant AND its own
# anti-vacuum control. A matcher that found nothing anywhere would fail here
# for want of the positive hit, instead of reporting a clean codebase.
_BACKREFERENCE_ADAPTER = _PORTS_MODULE


def test_the_port_adapter_is_the_only_coordinator_backreference() -> None:
    """Plan O.3/S.3: ``self._c`` exists in exactly one module of the package.

    The health reporter used to be the second holder and doubled as this
    detector's positive control. S.3 replaced its five borrowed names with
    real owners (an ``IssueLedger``, constructor-injected identity, and an
    inverted responsibility for ``_trv_ext_temp``), so the control moved here
    — to the module whose whole purpose is to hold that reference.
    """
    holders = sorted(
        _rel(path) for path in _component_sources() if _self_c_accesses(_rel(path))
    )
    assert holders == [_BACKREFERENCE_ADAPTER], (
        f"modules holding a self._c backreference: {holders}. Exactly one is "
        f"expected ({_BACKREFERENCE_ADAPTER}); more means a new backreference "
        f"crept in, none means the detector stopped working and every "
        f"invariant below it is vacuously green."
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


# Written as a constant, never as a real directive, so this file's own source
# can carry the needle without ruff seeing a suppression here.
_NOQA_F401 = "noqa: F401"


_PROXY_CLASS = "_CoordinatorGlobals"


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


# --- S.4a: who may read the state machine at all ----------------------------

# ``hass.states`` is the tick's cheapest-looking and most expensive habit: one
# extra read per zone per tick is 1440 reads a day for nothing. The tick chain
# therefore funnels every read through ONE adapter, which is what makes the
# runtime read budget in ``tests/integration/test_tick_cost_glue.py``
# measurable at all. Three modules outside the tick may read directly, each
# for a stated reason; anything else is a new, unmeasured cost path.
_STATES_READERS: dict[str, str] = {
    "custom_components/poise/ha/input_reader.py": (
        "THE reading adapter of the tick chain (phase-4 read boundary)"
    ),
    "custom_components/poise/config_flow.py": (
        "setup/reconfigure dialogs - runs outside any tick"
    ),
    "custom_components/poise/__init__.py": ("entry setup guards - once per entry"),
    "custom_components/poise/ha/actuator_lifecycle.py": (
        "the shared hand-back lifecycle (park state read + TRV restore) - "
        "one-shot teardown/reconfigure reads, never on the tick "
        "(review 2026-08-19 P1)"
    ),
    "custom_components/poise/hub_coordinator.py": (
        "the boiler hub's own aggregation; it has no InputReader"
    ),
}


def _states_accesses(rel_path: str) -> list[int]:
    """Line numbers of every ``<x>.states`` attribute node in one module."""
    return [
        node.lineno
        for node in ast.walk(_parse(rel_path))
        if isinstance(node, ast.Attribute) and node.attr == "states"
    ]


def test_only_the_input_reader_reads_the_state_machine_in_the_tick_chain() -> None:
    """S.4a: the read boundary, enforced.

    It was already true and nothing said so - the kind of property that stays
    true until the first hurried patch. The reader itself is the positive
    control: a detector that found nothing would fail here rather than report
    a clean codebase.
    """
    readers = sorted(
        _rel(path) for path in _component_sources() if _states_accesses(_rel(path))
    )
    assert readers == sorted(_STATES_READERS), (
        f"modules touching hass.states: {readers}. Expected exactly "
        f"{sorted(_STATES_READERS)} - a new one inside the tick chain is an "
        f"unmeasured per-tick cost and belongs behind the InputReader."
    )
