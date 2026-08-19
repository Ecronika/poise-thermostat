"""Every raised translation key must exist in every language file.

A ``translation_key`` that has no entry does not fail loudly: Home Assistant
falls back to showing the raw key. The user then reads
``missing_required_setting`` instead of a sentence — worse than the English
message the key replaced, and nothing in the test suite would notice.

This scans the raise sites for ``translation_key=`` and checks the key against
``strings.json`` and every shipped translation, in both directions: no key
without an entry, and no entry without a raise site.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "poise"

_TRANSLATED_EXCEPTIONS = (
    "ConfigEntryError",
    "ConfigEntryNotReady",
    "HomeAssistantError",
)


def _raised_keys() -> dict[str, list[str]]:
    """Map ``translation_key`` -> the modules that raise with it."""
    found: dict[str, list[str]] = {}
    for path in sorted(COMPONENT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            func = node.exc.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name not in _TRANSLATED_EXCEPTIONS:
                continue
            for kw in node.exc.keywords:
                if kw.arg == "translation_key" and isinstance(kw.value, ast.Constant):
                    found.setdefault(str(kw.value.value), []).append(path.name)
    return found


def _locale_files() -> list[Path]:
    return [
        COMPONENT / "strings.json",
        *sorted((COMPONENT / "translations").glob("*.json")),
    ]


def test_translated_exceptions_are_actually_used() -> None:
    """Non-vacuity: the scan must find raise sites at all.

    Without this a broken matcher would report "every key is translated" for a
    component that translates nothing.
    """
    raised = _raised_keys()
    assert raised, "no translated exception raise site found — is the scan broken?"
    assert len(raised) >= 4, f"expected the known raise sites, found {sorted(raised)}"


@pytest.mark.parametrize("locale", _locale_files(), ids=lambda p: p.name)
def test_every_raised_key_exists_in_every_locale(locale: Path) -> None:
    """No raise may show the user a bare key instead of a sentence."""
    block = json.loads(locale.read_text(encoding="utf-8")).get("exceptions", {})
    missing = sorted(k for k in _raised_keys() if k not in block)
    assert not missing, f"{locale.name} has no `exceptions` entry for: {missing}"


@pytest.mark.parametrize("locale", _locale_files(), ids=lambda p: p.name)
def test_every_locale_entry_carries_a_message(locale: Path) -> None:
    """HA reads ``exceptions.<key>.message``; anything else renders nothing."""
    block = json.loads(locale.read_text(encoding="utf-8")).get("exceptions", {})
    broken = sorted(
        k for k, v in block.items() if not isinstance(v, dict) or not v.get("message")
    )
    assert not broken, f"{locale.name}: entries without a `message`: {broken}"


def test_no_orphan_exception_entry() -> None:
    """An entry nobody raises is dead text that drifts out of date unnoticed."""
    shipped = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8")).get(
        "exceptions", {}
    )
    orphans = sorted(set(shipped) - set(_raised_keys()))
    assert not orphans, f"`exceptions` entries nothing raises: {orphans}"


def test_placeholders_match_between_message_and_raise() -> None:
    """A placeholder the message names but the raise never fills renders raw.

    Checked against ``strings.json`` only: the translations are pinned to the
    same key set by the tests above, and HA formats them with the same dict.
    """
    import re

    shipped = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))[
        "exceptions"
    ]
    supplied: dict[str, set[str]] = {}
    for path in sorted(COMPONENT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            kws = {kw.arg: kw.value for kw in node.exc.keywords}
            key_node = kws.get("translation_key")
            holder = kws.get("translation_placeholders")
            if not isinstance(key_node, ast.Constant) or not isinstance(
                holder, ast.Dict
            ):
                continue
            names = {k.value for k in holder.keys if isinstance(k, ast.Constant)}
            supplied.setdefault(str(key_node.value), set()).update(names)

    problems = []
    for key, entry in shipped.items():
        wanted = set(re.findall(r"\{(\w+)\}", entry["message"]))
        given = supplied.get(key, set())
        if wanted - given:
            problems.append(
                f"{key}: message needs {sorted(wanted - given)}, "
                f"raise gives {sorted(given)}"
            )
    assert not problems, (
        "placeholder mismatch — HA would render the braces raw: " + "; ".join(problems)
    )
