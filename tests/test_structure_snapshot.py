"""Snapshot and ownership invariants (plan O.2), one of six structure gates.

What ``TickConfigSnapshot`` and ``ZoneBindings`` may and may not carry: no
entity id in the tuning snapshot, no mutable sequence field anywhere. Both
rules exist because a snapshot that carries the wrong KIND of value silently
turns a per-tick copy into a stale one.
"""

from __future__ import annotations

import ast

import pytest

from tests.structure_support import (
    REPO_ROOT,
)

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
