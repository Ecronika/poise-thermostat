"""Shared measurement and vocabulary for the structure gates (plan S.2).

Not a test module: the six ``test_structure_*.py`` files each own ONE kind of
invariant, and this module holds what more than one of them needs — the line
classification and per-entry measurement of the ratchet, the AST primitives
every detector is built from, the refactor-step bookkeeping, and the module
paths/port vocabulary that the port and phase gates both speak.

Anything used by exactly one gate lives with that gate. That rule is what
keeps this module from becoming the junk drawer the split was meant to end.

Like its callers it must NOT import ``homeassistant``: the gates read and
parse their target files as text, never by importing them.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

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


# --- enforced structural invariants, active from O.3 ------------------------

_ORCHESTRATOR_MODULE = "custom_components/poise/ha/tick_orchestrator.py"


_PORTS_MODULE = "custom_components/poise/ha/tick_ports.py"


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


# --- enforced structural invariants, active from O.4 ------------------------

_COORDINATOR_MODULE = "custom_components/poise/coordinator.py"


def _count_in_file(rel_path: str, needle: str) -> int:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} does not exist"
    return path.read_text(encoding="utf-8").count(needle)


def _parse(rel_path: str) -> ast.Module:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} does not exist"
    return ast.parse(path.read_text(encoding="utf-8"))


# --- package file enumeration (shared: pipeline + ports gates) --------------


def _component_sources() -> list[Path]:
    sources = sorted((REPO_ROOT / "custom_components").rglob("*.py"))
    assert sources, "no component sources found - this scan would be vacuous"
    return sources


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
