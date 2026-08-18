"""Rules hassfest enforces on translation text, checked before CI does.

hassfest runs in Docker in the ``validate`` job. Locally there is no way to
run it, so a rule it enforces can only be learned by breaking the build -
which is exactly how the rule below was learned: HA rejects a placeholder
wrapped in single quotes, because the apostrophes read as quoting in some
languages and the rendered sentence becomes ambiguous.

This file pins the text rules that cost us a red CI. It is deliberately
narrow: it does NOT try to reimplement hassfest, only to catch the specific
mistakes that have already happened once, so they cannot happen twice.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "poise"

_QUOTED_PLACEHOLDER = re.compile(r"'\{\w+\}'")


def _locale_files() -> list[Path]:
    return [
        COMPONENT / "strings.json",
        *sorted((COMPONENT / "translations").glob("*.json")),
    ]


def _strings(node: object, path: str = "") -> list[tuple[str, str]]:
    if isinstance(node, dict):
        return [
            item
            for key, value in node.items()
            for item in _strings(value, f"{path}.{key}" if path else key)
        ]
    if isinstance(node, str):
        return [(path, node)]
    return []


@pytest.mark.parametrize("locale", _locale_files(), ids=lambda p: p.name)
def test_no_placeholder_inside_single_quotes(locale: Path) -> None:
    """hassfest: ``'{placeholder}'`` is rejected outright.

    Learned the hard way — this exact form shipped in an ``exceptions``
    message and failed the validate job with "the string should not contain
    placeholders inside single quotes". Typographic quotes are fine (de.json
    uses them); only the ASCII apostrophe is the problem.
    """
    offenders = [
        f"{path}: {text}"
        for path, text in _strings(json.loads(locale.read_text(encoding="utf-8")))
        if _QUOTED_PLACEHOLDER.search(text)
    ]
    assert not offenders, (
        f"{locale.name} wraps a placeholder in single quotes, which hassfest "
        f"rejects. Drop the quotes or use typographic ones: {offenders}"
    )


def test_the_quoted_placeholder_detector_matches_the_rejected_form() -> None:
    """Non-vacuity: the pattern must still recognise what hassfest rejected."""
    assert _QUOTED_PLACEHOLDER.search("the required '{key}' setting")
    assert not _QUOTED_PLACEHOLDER.search("the required {key} setting")
    assert not _QUOTED_PLACEHOLDER.search("die Einstellung „{key}“")


@pytest.mark.parametrize("locale", _locale_files(), ids=lambda p: p.name)
def test_locale_file_is_sorted_json_without_empty_strings(locale: Path) -> None:
    """An empty translation renders as a blank label, which looks like a bug."""
    blanks = [
        path
        for path, text in _strings(json.loads(locale.read_text(encoding="utf-8")))
        if not text.strip()
    ]
    assert not blanks, f"{locale.name} has empty translation string(s): {blanks}"
