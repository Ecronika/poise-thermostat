"""Plan O.2 proofs for ``TickConfigSnapshot`` / ``ZoneBindings``.

Spec: ``docs/Konzepte/2026-08-16_Refactoring-Plan_tick-orchestrator.md``,
section "O.2". Three independent proofs, all pure (no ``homeassistant``
import — the module under test keeps ``PoiseCoordinator`` under
``TYPE_CHECKING``):

1. **Bijection field <-> source.** Every field of either frozen class maps to
   exactly ONE named coordinator attribute (AST over ``from_coordinator``),
   and after the build the value IS that attribute's value (sentinel build
   against a stand-in coordinator; ``windows`` as ``tuple(...)`` of the live
   list).
2. **Writer allowlist per field group.** An AST scan over
   ``custom_components/poise/**`` collects, for every one of the 39 source
   attributes, which qualified function assigns it. Each group has its own
   permitted-writer set; a new writer anywhere else fails the suite. Plus the
   pin that ``HealthReporter.validate_configured_ext_temp`` — the one writer
   that is NOT ``__init__`` — is called only from ``async_bootstrap``, i.e.
   before the first tick. Together these prove the property the snapshot needs:
   **no mutation of a source while a tick is running.**
3. **Migration gate (one-off).** The 62 ``self._c`` attribute names measured
   BEFORE O.2 partition disjointly into snapshot sources (30), bindings
   sources (9), stable collaborators (3) and ports (20).

Deliberately NOT tested (it is false): "every field ``_apply_hot_tuning``
writes must be in the snapshot". That method also writes ``_override_timer_h``,
``_boost_duration_min``, ``_presence_home_entities`` and others the tick never
reads; a hot-applyed value the tick does not read must not fail anything.
"""

from __future__ import annotations

import ast
import collections
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from custom_components.poise.ha.tick_snapshot import TickConfigSnapshot, ZoneBindings
from custom_components.poise.runtime.config import ZoneTuning

REPO_ROOT = Path(__file__).resolve().parents[1]
_PKG = REPO_ROOT / "custom_components" / "poise"
_SNAPSHOT_SRC = _PKG / "ha" / "tick_snapshot.py"


def sample_tick_config() -> TickConfigSnapshot:
    """A realistic config view for tests that only need to FILL the field.

    Shared helper (imported by ``test_phase1_tick_result`` and
    ``test_phase6b_stages``, which carry the ``PreparedState`` /
    ``FinalizeContext`` pins): all 30 snapshot fields are also
    ``runtime.config.ZoneTuning`` fields, so the parser's defaults give a
    value-realistic object without spelling 30 literals out.
    """
    tuning = ZoneTuning.from_merged({})
    return TickConfigSnapshot(
        **{f.name: getattr(tuning, f.name) for f in fields(TickConfigSnapshot)}
    )


# ---------------------------------------------------------------------------
# Proof 1 — bijection field <-> coordinator attribute
# ---------------------------------------------------------------------------


def _from_coordinator_map(class_name: str) -> dict[str, str]:
    """Map ``field name -> coordinator attribute`` by reading the class's
    ``from_coordinator`` body as AST.

    Accepted value shapes are exactly two: ``coordinator.<attr>`` and
    ``tuple(coordinator.<attr>)`` (the immutability copy). Anything else — a
    computed value, a constant, two attributes combined — is rejected here,
    because it would break the "exactly one named source" property this proof
    is about.
    """
    tree = ast.parse(_SNAPSHOT_SRC.read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name
    )
    fn = next(
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "from_coordinator"
    )
    (param,) = [a.arg for a in fn.args.args if a.arg != "cls"]
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "cls"
    ]
    assert len(calls) == 1, f"{class_name}.from_coordinator must build once"
    mapping: dict[str, str] = {}
    for kw in calls[0].keywords:
        assert kw.arg is not None, f"{class_name}: no **kwargs expansion allowed"
        value = kw.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "tuple"
            and len(value.args) == 1
        ):
            value = value.args[0]
        assert isinstance(value, ast.Attribute), (
            f"{class_name}.{kw.arg} is not a plain attribute read"
        )
        assert isinstance(value.value, ast.Name) and value.value.id == param, (
            f"{class_name}.{kw.arg} does not read off the coordinator parameter"
        )
        mapping[kw.arg] = value.attr
    return mapping


class _CoordinatorStub:
    """Stand-in coordinator: every attribute yields a value unique to its name.

    ``_windows`` is a real ``list`` on purpose — the coordinator holds one, and
    the ``tuple(...)`` copy in ``ZoneBindings.from_coordinator`` is exactly
    what this stub is here to catch if it ever disappears.
    """

    def __init__(self) -> None:
        self._windows = ["binary_sensor.w1", "binary_sensor.w2"]

    def __getattr__(self, name: str) -> str:
        return f"<{name}>"


@pytest.mark.parametrize(
    ("cls", "name"),
    [(TickConfigSnapshot, "TickConfigSnapshot"), (ZoneBindings, "ZoneBindings")],
    ids=["TickConfigSnapshot", "ZoneBindings"],
)
def test_every_field_maps_to_exactly_one_coordinator_attribute(
    cls: type, name: str
) -> None:
    """Proof 1a: the field set and the read set are the same set, and the
    mapping is injective — no field fed from two attributes, no attribute
    feeding two fields."""
    mapping = _from_coordinator_map(name)
    field_names = [f.name for f in fields(cls)]
    assert sorted(mapping) == sorted(field_names), (
        f"{name}: from_coordinator keywords and dataclass fields differ"
    )
    sources = list(mapping.values())
    assert len(set(sources)) == len(sources), (
        f"{name}: two fields read the same coordinator attribute {sources!r}"
    )
    # The naming rule IS the contract: field name == attribute minus the one
    # leading underscore (``zone_name`` has none).
    for field_name, attr in mapping.items():
        assert attr.lstrip("_") == field_name, (
            f"{name}.{field_name} reads {attr!r} — the field must be named "
            f"after its source attribute (leading underscore dropped)."
        )


def test_config_snapshot_has_thirty_fields_and_copies_their_values() -> None:
    """Proof 1b (config): 30 fields, each equal to its source after the build."""
    stub = _CoordinatorStub()
    snap = TickConfigSnapshot.from_coordinator(stub)  # type: ignore[arg-type]
    mapping = _from_coordinator_map("TickConfigSnapshot")
    assert len(fields(TickConfigSnapshot)) == 30
    for field_name, attr in mapping.items():
        assert getattr(snap, field_name) == getattr(stub, attr)


def test_zone_bindings_has_nine_fields_and_copies_their_values() -> None:
    """Proof 1b (bindings): 9 fields; ``windows`` is the tuple of the live
    list, not the list object itself."""
    stub = _CoordinatorStub()
    binds = ZoneBindings.from_coordinator(stub)  # type: ignore[arg-type]
    mapping = _from_coordinator_map("ZoneBindings")
    assert len(fields(ZoneBindings)) == 9
    for field_name, attr in mapping.items():
        expected: Any = getattr(stub, attr)
        if field_name == "windows":
            expected = tuple(expected)
        assert getattr(binds, field_name) == expected
    assert binds.windows == ("binary_sensor.w1", "binary_sensor.w2")
    # The frozen dataclass would NOT freeze a list's contents: mutating the
    # coordinator's live list after the build must not touch the snapshot.
    stub._windows.append("binary_sensor.w3")
    assert binds.windows == ("binary_sensor.w1", "binary_sensor.w2")


# ---------------------------------------------------------------------------
# Proof 2 — writer allowlist per field group
# ---------------------------------------------------------------------------

_HOT_APPLYED = (
    "_active_comfort",
    "_adaptive_cool_cfg",
    # Hot-applyable since schema 2.3: the adopt gates were init-only (one
    # reload per toggle) until ``_apply_hot_tuning`` took them over.
    "_adopt_external_mode",
    "_adopt_external_setpoint",
    "_category",
    "_clo_offset",
    "_comfort_base",
    "_comp_min_off_opt",
    "_comp_mode_hold_opt",
    "_compressor_guard",
    "_cool_hard_cap",
    "_cool_lockout_enabled",
    "_cool_min_outdoor",
    "_dynamics_override",
    "_hdh_cfg",
    "_heat_lockout_enabled",
    "_heat_max_outdoor",
    "_operative_input",
    "_optimal_start",
    "_optimal_stop",
    "_override_policy",
    "_presence_cfg",
    "_priority",
    "_room_profile",
    "_schedule",
    "_thermal_shock_delta",
    "_trace_enabled",
    "_vent_notify",
)
# Both are default-constructed constants the parser never config-reads, so
# there is nothing for a hot-apply to re-read.
_INIT_ONLY_CONFIG = (
    "_window_auto_cfg",
    "_override_cfg",
)
_BINDINGS_INIT_ONLY = (
    "_entry_id",
    "zone_name",
    "_temp",
    "_humidity",
    "_weather",
    "_outdoor_humidity",
    "_actuator",
    "_windows",
)

_INIT = "PoiseCoordinator.__init__"
_HOT = "PoiseCoordinator._apply_hot_tuning"
_BOOTSTRAP = "PoiseCoordinator.async_bootstrap"
# S.3: the reporter keeps its OWN ``_entry_id``/``_actuator`` slots. The
# scan below is receiver-agnostic on purpose (that is how it once caught
# ``self._c._trv_ext_temp = ...``), so those constructor assignments show
# up here even though they can no longer touch the coordinator - the
# reporter has no reference to it any more, which
# ``test_the_port_adapter_is_the_only_coordinator_backreference`` pins.
_REPORTER_INIT = "HealthReporter.__init__"

# Permitted writers, NOT expected writers: a field may be written by a subset
# (most hot-applyed ones are only written in _apply_hot_tuning, which __init__
# calls). Every field must have at least one writer, and none outside its set.
_WRITER_ALLOWLIST: dict[str, frozenset[str]] = {
    **{attr: frozenset({_INIT, _HOT}) for attr in _HOT_APPLYED},
    **{attr: frozenset({_INIT}) for attr in _INIT_ONLY_CONFIG},
    **{attr: frozenset({_INIT}) for attr in _BINDINGS_INIT_ONLY},
    # Same NAME, different object: the health reporter's own identity slots.
    "_entry_id": frozenset({_INIT, _REPORTER_INIT}),
    "_actuator": frozenset({_INIT, _REPORTER_INIT}),
    # The one documented exception, and the reason ZoneBindings is rebuilt per
    # tick instead of once in the constructor. Since S.3 the invalidating
    # write is the COORDINATOR's: the reporter reports a verdict, the owner
    # acts on it, and the field keeps exactly one writer per scope.
    "_trv_ext_temp": frozenset({_INIT, _BOOTSTRAP}),
}


def _scan_package(
    visit: Callable[[ast.AST, tuple[str, ...]], None],
) -> None:
    """Call ``visit(node, scope)`` for every AST node of every package module.

    ``scope`` is the enclosing class/function path, so a hit can be reported
    as ``PoiseCoordinator._apply_hot_tuning`` rather than just "somewhere in
    coordinator.py".
    """

    def walk(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            inner = scope
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = (*scope, child.name)
            visit(child, inner)
            walk(child, inner)

    for path in sorted(_PKG.rglob("*.py")):
        walk(ast.parse(path.read_text(encoding="utf-8")), ())


def _qualified_writers() -> dict[str, set[str]]:
    """``attribute -> {qualified function that assigns it}`` over the package.

    Any attribute assignment counts, whatever the receiver expression is —
    ``self._trv_ext_temp = ...`` in the coordinator and (until S.3 removed it)
    ``self._c._trv_ext_temp = ...`` in the health reporter were both writers of
    the same coordinator attribute, and a scan keyed on ``self.`` alone would
    have missed the second one. The price of that reach is that an unrelated
    class writing the same NAME lands here too; the allowlist says which.
    """
    writers: dict[str, set[str]] = collections.defaultdict(set)
    watched = set(_WRITER_ALLOWLIST)

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            return
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            for sub in ast.walk(target):
                if (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.ctx, ast.Store)
                    and sub.attr in watched
                ):
                    writers[sub.attr].add(".".join(scope) or "<module>")

    _scan_package(visit)
    return writers


@pytest.mark.parametrize("attr", sorted(_WRITER_ALLOWLIST))
def test_snapshot_source_writers_stay_inside_their_allowlist(attr: str) -> None:
    """Proof 2: only the permitted functions may assign a snapshot/bindings
    source. A new writer (as ``_set_mpc_params`` would be for ``_mpc_params``)
    breaks the "constant for the tick duration" argument, so it breaks here.
    """
    writers = _qualified_writers()
    found = writers.get(attr, set())
    assert found, (
        f"{attr}: no writer found at all — the AST scan or the attribute name "
        f"is stale, and a vacuously green allowlist proves nothing."
    )
    allowed = _WRITER_ALLOWLIST[attr]
    assert found <= allowed, (
        f"{attr} is written by {sorted(found - allowed)}, which is outside its "
        f"permitted set {sorted(allowed)}. A snapshot source may not be "
        f"mutated from anywhere else — least of all during a tick."
    )


def test_ext_temp_validation_runs_only_from_bootstrap() -> None:
    """Proof 2 (addendum): the one non-``__init__`` writer of ``_trv_ext_temp``
    is reachable ONLY from ``async_bootstrap``. Without this pin the allowlist
    would permit "some time", not "before the first tick"."""
    callers: set[str] = set()

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "validate_configured_ext_temp"
        ):
            callers.add(".".join(scope) or "<module>")

    _scan_package(visit)
    assert callers == {"PoiseCoordinator.async_bootstrap"}, (
        f"validate_configured_ext_temp is called from {sorted(callers)}; it "
        f"must stay a setup-time call so its _trv_ext_temp write can never "
        f"land inside a running tick."
    )


# ---------------------------------------------------------------------------
# Proof 3 — one-off migration gate for the 62 pre-O.2 backreference names
# ---------------------------------------------------------------------------

# FROZEN ON PURPOSE — do NOT re-derive this from the code at runtime.
# This is the AST census of ``self._c.<x>`` in ha/tick_orchestrator.py as it
# stood BEFORE O.2 (62 distinct attribute names). Reading the live set instead
# would make this test vacuously green from O.3 onwards, when the set is
# empty. It is a ONE-OFF migration gate: it proves the O.2 classification was
# total and overlap-free. From O.3 the permanent gates carry the load
# (``self._c`` count, the bijection above, the writer allowlist, the
# collaborator allowlist and the port capability views).
_PRE_O2_BACKREFERENCE_NAMES: frozenset[str] = frozenset(
    {
        "_active_comfort",
        "_actuator",
        "_adaptive_cool_cfg",
        "_adopt_external_mode",
        "_adopt_external_setpoint",
        "_category",
        "_clo_offset",
        "_comfort_base",
        "_comp_min_off_opt",
        "_comp_mode_hold_opt",
        "_compressor_guard",
        "_cool_hard_cap",
        "_cool_lockout_enabled",
        "_cool_min_outdoor",
        "_dynamics_override",
        "_end_hold",
        "_entry_id",
        "_expire_timed_states",
        "_fire_override_ended",
        "_forecast_outdoor",
        "_forecast_provider",
        "_hdh_cfg",
        "_health",
        "_heat_lockout_enabled",
        "_heat_max_outdoor",
        "_humidity",
        "_input_reader",
        "_maybe_record_trace",
        "_maybe_save",
        "_mpc_params",
        "_notify_convergence",
        "_notify_cooling_failure",
        "_notify_failure",
        "_operative_input",
        "_optimal_start",
        "_optimal_stop",
        "_outdoor_humidity",
        "_override_cfg",
        "_override_policy",
        "_presence_cfg",
        "_priority",
        "_room_profile",
        "_schedule",
        "_set_mode_override",
        "_set_mpc_params",
        "_sync_clo_suggestion_issue",
        "_sync_season_hint_issue",
        "_sync_suggestion_issue",
        "_temp",
        "_thermal_shock_delta",
        "_trace_enabled",
        "_trv_ext_temp",
        "_unavailable_logged",
        "_vent_notify",
        "_weather",
        "_window_auto_cfg",
        "_windows",
        "_write_unavailable_safe_state",
        "commit_execution",
        "hass",
        "set_override",
        "zone_name",
    }
)

# The three stable collaborators (constructive injection at O.3, never ports).
_STABLE_COLLABORATORS: frozenset[str] = frozenset(
    {"_input_reader", "_forecast_provider", "hass"}
)

# The 20 ports O.3 turns into capability views: 17 coordinator facades,
# ``_health`` (late-binding duty), ``_unavailable_logged`` (adapter state the
# orchestrator writes) and the per-tick derived ``_mpc_params``/
# ``_set_mpc_params``.
_PORTS: frozenset[str] = frozenset(
    {
        "_end_hold",
        "_expire_timed_states",
        "_fire_override_ended",
        "_forecast_outdoor",
        "_health",
        "_maybe_record_trace",
        "_maybe_save",
        "_mpc_params",
        "_notify_convergence",
        "_notify_cooling_failure",
        "_notify_failure",
        "_set_mode_override",
        "_set_mpc_params",
        "_sync_clo_suggestion_issue",
        "_sync_season_hint_issue",
        "_sync_suggestion_issue",
        "_unavailable_logged",
        "_write_unavailable_safe_state",
        "commit_execution",
        "set_override",
    }
)


def test_pre_o2_backreference_partitions_into_the_four_categories() -> None:
    """Proof 3: the frozen 62-name set splits disjointly and completely into
    snapshot sources (30), bindings sources (9), stable collaborators (3) and
    ports (20)."""
    snapshot_sources = {f"_{f.name}" for f in fields(TickConfigSnapshot)}
    bindings_sources = {attr for attr in _from_coordinator_map("ZoneBindings").values()}
    groups = {
        "snapshot": snapshot_sources,
        "bindings": bindings_sources,
        "collaborators": set(_STABLE_COLLABORATORS),
        "ports": set(_PORTS),
    }
    assert (len(snapshot_sources), len(bindings_sources)) == (30, 9)
    assert (len(_STABLE_COLLABORATORS), len(_PORTS)) == (3, 20)
    assert len(_PRE_O2_BACKREFERENCE_NAMES) == 62

    names = sorted(groups)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            overlap = groups[a] & groups[b]
            assert not overlap, f"{a} and {b} both claim {sorted(overlap)}"

    union: set[str] = set()
    for members in groups.values():
        union |= members
    assert union == set(_PRE_O2_BACKREFERENCE_NAMES), (
        f"unclassified: {sorted(set(_PRE_O2_BACKREFERENCE_NAMES) - union)}; "
        f"invented: {sorted(union - set(_PRE_O2_BACKREFERENCE_NAMES))}"
    )
