"""Phase-4 read-boundary grep gate (refactoring plan, phase 4).

Pins the module boundary this phase established: ``ha/input_reader.py`` is the
single READING Home-Assistant adapter. ``coordinator.py`` must contain no
direct state read (``hass.states.get`` / ``….states.get(…``) and no registry
discovery read (``er.async_entries_for_device``) — every read goes through the
``InputReader`` (``snapshot()`` for the pre-first-await segment, positioned
reader calls for everything after an await).

Pure source-text test: no Home Assistant import, runs in the py3.10 pure gate.

The tree-wide check carries an explicit, documented exception list — every
entry is either the reader itself or a module deliberately OUT of phase-4
scope. Shrinking this list is the job of later phases; growing it would mean
a new direct read slipped in and must fail here.
"""

from __future__ import annotations

from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "poise"

# The gate strings. ``.states.get(`` (leading dot) also catches reads through
# an aliased hass reference (``self.hass.states.get`` / ``self._hass.…``).
READ_PATTERNS = ("hass.states.get", ".states.get(", "er.async_entries_for_device")

# file (posix path relative to custom_components/poise) -> why it may contain
# a gate string. Goal state: only the ha/ entries remain (later phases).
ALLOWED = {
    "ha/input_reader.py": (
        "the single reading HA adapter itself — every hass.states.get and the "
        "device-guard registry discovery live here by design (plan section 2)"
    ),
    "ha/__init__.py": (
        "package docstring NAMES the hass.states.get pattern to document the "
        "boundary; contains no code read"
    ),
    "hub_coordinator.py": (
        "system-hub coordinator — explicitly NOT part of phase 4 (the plan "
        "refactors the ZONE coordinator; the hub keeps its two boiler-entity "
        "reads until its own phase)"
    ),
    "config_flow.py": (
        "foreign parallel work — explicitly out of phase-4 scope (orchestrator "
        "directive: config_flow.py untouched); its reads are setup-wizard "
        "previews, not tick reads"
    ),
    "__init__.py": (
        "entry setup/teardown lifecycle reads (required-entity check, TRV "
        "sensor-source restore on removal) — move with the later ha/ phases, "
        "not with the tick's read boundary"
    ),
}


def _hits(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [p for p in READ_PATTERNS if p in text]


def test_coordinator_has_no_direct_state_reads() -> None:
    """coordinator.py: zero direct reads — the exception list is EMPTY."""
    assert _hits(COMPONENT / "coordinator.py") == []


def test_input_reader_is_the_only_reading_module() -> None:
    """No module outside the exception list contains a gate string."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(COMPONENT.rglob("*.py")):
        rel = path.relative_to(COMPONENT).as_posix()
        if rel in ALLOWED:
            continue
        found = _hits(path)
        if found:
            offenders[rel] = found
    assert offenders == {}, (
        "direct HA state/registry reads outside ha/input_reader.py — route "
        f"them through the InputReader (plan phase 4): {offenders}"
    )


def test_exception_list_is_not_stale() -> None:
    """Every allowed file still needs its exception (and still exists).

    The moment a later phase cleans one of these up, its entry must be
    deleted here so the gate tightens instead of silently rotting.
    """
    for rel, why in ALLOWED.items():
        path = COMPONENT / rel
        assert path.is_file(), f"exception entry for a missing file: {rel}"
        assert _hits(path), f"{rel} no longer needs its exception ({why})"
