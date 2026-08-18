"""``quality_scale.yaml`` stays machine-readable and honest.

Why this lives in the GLUE suite and not next to the other pure static-file
tests: it needs a YAML parser, and the pinned dev/CI tooling
(``requirements-dev.txt``) deliberately does not install PyYAML. The HA test
harness does, so the integration job is the only place the check can actually
run. It imports no Home Assistant API of its own.

The trigger: the file was **unparseable YAML** for a long time without anyone
noticing — an unquoted ``comment:`` value contained a ``": "``
(``manifest requirements: []``), which ends a plain scalar. hassfest only
schema-checks ``quality_scale.yaml`` for CORE integrations, so nothing in CI
looked at it, and a self-assessment nobody can machine-read is worth very
little.

The second assertion is the project rule from the task that produced this
file: a rule that is not ``done`` must say what is still missing, otherwise
the entry is a to-do nobody can act on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

QUALITY_SCALE = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "poise"
    / "quality_scale.yaml"
)

VALID_STATUS = {"done", "exempt", "todo"}


def _rules() -> dict[str, Any]:
    data = yaml.safe_load(QUALITY_SCALE.read_text(encoding="utf-8"))
    rules: dict[str, Any] = data["rules"]
    return rules


def _status(value: Any) -> str:
    return value if isinstance(value, str) else str(value["status"])


def test_quality_scale_is_parseable_yaml() -> None:
    rules = _rules()
    assert rules, "quality_scale.yaml parsed but carries no rules"


def test_every_status_is_from_the_documented_vocabulary() -> None:
    bad = {name: _status(v) for name, v in _rules().items()}
    offenders = {n: s for n, s in bad.items() if s not in VALID_STATUS}
    assert not offenders, f"unknown status value(s): {offenders}"


def test_non_done_rules_explain_what_is_missing() -> None:
    """``exempt`` needs a reason, ``todo`` needs the outstanding work."""
    silent = [
        name
        for name, value in _rules().items()
        if _status(value) != "done"
        and not (isinstance(value, dict) and str(value.get("comment", "")).strip())
    ]
    assert not silent, (
        "exempt/todo rule(s) without a comment — an unexplained non-done entry "
        f"is not actionable: {silent}"
    )
