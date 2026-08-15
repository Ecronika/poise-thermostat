"""Announced HA removals, pinned as project invariants (pure, AST/source).

Deprecations are invisible to a passing test suite: HA reports most of them
through its own logging, not as ``DeprecationWarning``, so the glue suite
stays green right up to the release that removes the old form. These tests
therefore assert the *shape of our source* instead of runtime behaviour —
they are the only thing that fails before the deadline rather than after.

Covered (see docs/reviews/2026-08-15-ha-drift-2026-02-bis-2026-08.md):

* ``async_extract_config_entry_ids`` lost its leading ``hass`` argument;
  HA marks the shim ``breaks_in_ha_version="2026.10"``. Passing ``hass``
  after that binds it as the ``service_call`` — no clean TypeError, just a
  broken attribute access on the targeted service path.
* A config-entry update listener together with a RELOADING flow method is
  deprecated since HA 2026.6 and an error from 2026.12 (double load / race).
  Poise keeps the listener — it hot-applies tuning without a reload, which
  is what preserves the learned model — so nothing else may reload:
  neither ``async_update_reload_and_abort`` nor an ``OptionsFlowWithReload``
  base class.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "custom_components" / "poise"
INIT_SRC = SRC / "__init__.py"
FLOW_SRC = SRC / "config_flow.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _calls(path: Path) -> list[ast.Call]:
    return [n for n in ast.walk(_tree(path)) if isinstance(n, ast.Call)]


def _name_of(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def test_extract_config_entry_ids_is_called_without_hass() -> None:
    """Breaks in HA 2026.10 — the helper takes only the ServiceCall now.

    Scans the WHOLE package (not just ``__init__.py``): the deadline applies
    wherever the helper is called, and a future caller elsewhere must not slip
    through. A violation is any call carrying a second positional argument or
    a ``hass=`` keyword — not just the literal name ``hass``.
    """
    offenders: list[str] = []
    found = 0
    for path in sorted(SRC.rglob("*.py")):
        for call in _calls(path):
            if _name_of(call) != "async_extract_config_entry_ids":
                continue
            found += 1
            kwargs = {k.arg for k in call.keywords}
            if len(call.args) >= 2 or "hass" in kwargs:
                offenders.append(f"{path.name}:{call.lineno}")
    assert found, (
        "no async_extract_config_entry_ids call found any more — if the caller "
        "was removed on purpose, retire this test with it"
    )
    assert not offenders, (
        "async_extract_config_entry_ids(hass, call) breaks in HA 2026.10 "
        f"({offenders}) — pass the ServiceCall only"
    )


def test_no_reloading_flow_method_while_an_update_listener_exists() -> None:
    """Error from HA 2026.12: listener + reloading flow method may not mix.

    The listener stays (tuning hot-apply keeps the learned model), so the
    reload has to be triggered there — never by the flow.
    """
    listener = [c for c in _calls(INIT_SRC) if _name_of(c) == "add_update_listener"]
    assert listener, (
        "this invariant assumes Poise registers an update listener; if the "
        "listener was removed on purpose, retire this test with it"
    )
    reloading = [
        c.lineno
        for c in _calls(FLOW_SRC)
        if _name_of(c) == "async_update_reload_and_abort"
    ]
    assert not reloading, (
        "async_update_reload_and_abort together with an update listener is an "
        f"error from HA 2026.12 (lines {reloading}) — store with "
        "self.hass.config_entries.async_update_entry(...) + "
        "self.async_abort(...) and let the listener decide reload vs. "
        "hot-apply. NOT async_update_and_abort: that helper only reaches "
        "ConfigFlow in HA 2025.12, above our minimum."
    )


def test_no_options_flow_reloads_on_its_own() -> None:
    """Same deprecation from the other side: ``OptionsFlowWithReload`` makes
    HA reload the entry after the options flow — next to our listener that is
    exactly the forbidden double reload."""
    offenders = [
        node.name
        for node in ast.walk(_tree(FLOW_SRC))
        if isinstance(node, ast.ClassDef)
        and any(
            (b.id if isinstance(b, ast.Name) else getattr(b, "attr", ""))
            == "OptionsFlowWithReload"
            for b in node.bases
        )
    ]
    assert not offenders, (
        f"{offenders} inherit from OptionsFlowWithReload — that reloads on top "
        "of our update listener (error from HA 2026.12). Use plain OptionsFlow."
    )


def test_abort_if_unique_id_configured_never_reloads() -> None:
    """Same deprecation: a call that UPDATES an existing entry reloads it.

    Only calls that actually pass updates can reload (``reload_on_update``
    gates exactly that path), so the invariant is scoped to those — a bare
    duplicate-abort is harmless and must not be forced to carry a misleading
    ``reload_on_update=False``.
    """
    offenders = []
    for call in _calls(FLOW_SRC):
        if _name_of(call) != "_abort_if_unique_id_configured":
            continue
        kw = {k.arg: k.value for k in call.keywords}
        updates = bool(call.args) or "updates" in kw
        if not updates:
            continue
        val = kw.get("reload_on_update")
        if not (isinstance(val, ast.Constant) and val.value is False):
            offenders.append(call.lineno)
    assert not offenders, (
        "_abort_if_unique_id_configured(updates=...) reloads the existing entry "
        f"by default (lines {offenders}) — pass reload_on_update=False and let "
        "the update listener do it"
    )
