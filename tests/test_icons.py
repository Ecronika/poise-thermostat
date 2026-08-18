"""``icons.json`` consistency (quality scale: icon-translations).

Three things can silently rot once an integration ships icon translations,
and none of them is caught by hassfest's schema check:

1. an icon keyed on a ``translation_key`` that no longer exists (rename in
   ``strings.json`` / the platform module) — the icon just stops applying,
   nothing errors;
2. a ``state`` icon for a state the entity can never report;
3. the *reverse* of the rule: an entity that keeps a hardcoded ``_attr_icon``.
   ``Entity.icon`` wins over the icon translation (HA
   ``helpers/entity.py``: ``if hasattr(self, "_attr_icon"): return
   self._attr_icon``), so such an entity silently ignores ``icons.json``.

The third check is a RATCHET, not a pass/fail on the goal state: three
platform modules still carry ``_attr_icon`` today (removing them is a
production-code change, tracked as the open half of the ``icon-translations``
rule in ``quality_scale.yaml``). The test pins that set so it can only shrink,
and pins that every hardcoded literal is ALSO in ``icons.json`` — which makes
the eventual removal a behaviour-preserving deletion.

Pure and dependency-free: ``services.yaml`` is read with a top-level-key regex
rather than PyYAML, which the pinned dev/CI tooling does not install.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "poise"

# hassfest accepts more (entity_component, triggers, …); Poise deliberately
# ships only these two. Widening the set is a decision, not an accident.
ALLOWED_TOP_LEVEL = {"entity", "services"}

_MDI = re.compile(r"^mdi:[a-z0-9-]+$")
_TOP_LEVEL_YAML_KEY = re.compile(r"^([a-z_][a-z0-9_]*):", re.MULTILINE)
_MDI_LITERAL = re.compile(r'"(mdi:[a-z0-9-]+)"')

# The modules that still set ``_attr_icon`` instead of relying on
# ``icons.json``. RATCHET: this set may shrink, never grow.


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
    return data


def _icons() -> dict[str, Any]:
    return _load("icons.json")


def _strings() -> dict[str, Any]:
    return _load("strings.json")


def _service_names() -> set[str]:
    text = (COMPONENT / "services.yaml").read_text(encoding="utf-8")
    return set(_TOP_LEVEL_YAML_KEY.findall(text))


def _icon_values(node: Any) -> list[str]:
    """Every icon string anywhere in the icons.json tree."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [v for child in node.values() for v in _icon_values(child)]
    return []


def test_icons_json_only_uses_the_declared_sections() -> None:
    extra = set(_icons()) - ALLOWED_TOP_LEVEL
    assert not extra, f"unexpected icons.json section(s): {sorted(extra)}"


def test_every_icon_value_is_a_valid_mdi_name() -> None:
    bad = [v for v in _icon_values(_icons()) if not _MDI.match(v)]
    assert not bad, f"not an `mdi:<slug>` icon: {bad}"


def test_entity_icon_keys_exist_as_translation_keys() -> None:
    """An icon keyed on a dead translation_key applies to nothing."""
    entity_strings = _strings()["entity"]
    missing: list[str] = []
    for domain, keys in _icons()["entity"].items():
        known = entity_strings.get(domain, {})
        missing += [f"{domain}.{key}" for key in keys if key not in known]
    assert not missing, (
        "icons.json names translation keys that strings.json does not define "
        f"(renamed or removed?): {missing}"
    )


def test_state_icons_reference_declared_states() -> None:
    """A ``state`` icon for a state the entity cannot report is dead weight."""
    entity_strings = _strings()["entity"]
    offenders: list[str] = []
    for domain, keys in _icons()["entity"].items():
        for key, spec in keys.items():
            states = spec.get("state")
            if not states:
                continue
            declared = set(entity_strings.get(domain, {}).get(key, {}).get("state", {}))
            offenders += [
                f"{domain}.{key}.{state}" for state in states if state not in declared
            ]
    assert not offenders, (
        f"state icons for states strings.json does not declare: {offenders}"
    )


def test_every_entity_icon_has_a_default() -> None:
    """``default`` is what applies outside the enumerated states."""
    missing = [
        f"{domain}.{key}"
        for domain, keys in _icons()["entity"].items()
        for key, spec in keys.items()
        if "default" not in spec
    ]
    assert not missing, f"entity icon without a `default`: {missing}"


def test_service_icons_match_the_registered_services() -> None:
    icons_services = set(_icons().get("services", {}))
    assert icons_services <= _service_names(), (
        "icons.json has an icon for a service services.yaml does not declare: "
        f"{sorted(icons_services - _service_names())}"
    )
    assert icons_services <= set(_strings()["services"]), (
        "icons.json service key missing from strings.json: "
        f"{sorted(icons_services - set(_strings()['services']))}"
    )


def test_translations_carry_the_iconed_entity_keys() -> None:
    """``icons.json`` is language-neutral, but its keys must survive a rename
    in every shipped translation — otherwise one locale silently loses both
    the name and the icon."""
    for locale in sorted((COMPONENT / "translations").glob("*.json")):
        entity_strings = json.loads(locale.read_text(encoding="utf-8"))["entity"]
        missing = [
            f"{domain}.{key}"
            for domain, keys in _icons()["entity"].items()
            for key in keys
            if key not in entity_strings.get(domain, {})
        ]
        assert not missing, f"{locale.name} is missing iconed keys: {missing}"


def _modules_with_hardcoded_icons() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(COMPONENT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "_attr_icon" not in text and "icon=" not in text:
            continue
        literals = _MDI_LITERAL.findall(text)
        if literals:
            found[path.name] = literals
    return found


def test_no_entity_hardcodes_an_icon() -> None:
    """No ``_attr_icon`` anywhere: it wins over ``icons.json`` silently.

    ``helpers/entity.py`` returns ``self._attr_icon`` before it ever consults
    the icon translations, so a single hardcoded literal makes the shipped
    ``icons.json`` entry dead weight that nobody notices - the icon still
    looks right.

    This started as a ratchet over the three modules that carried literals
    (binary_sensor / switch / button). They are gone, so the rule is now the
    absolute one; its own non-vacuity guard is the detector test below, which
    proves the scan reaches real files with real content.
    """
    found = _modules_with_hardcoded_icons()
    assert not found, (
        "entity icon(s) hardcoded past icons.json - move them into "
        f"icons.json instead: { {m: sorted(set(i)) for m, i in found.items()} }"
    )


def test_hardcoded_icon_detector_reads_real_modules() -> None:
    """Non-vacuity for the rule above.

    ``_modules_with_hardcoded_icons`` returning ``{}`` is only meaningful if
    the scan actually opened the platform modules and would recognise an
    ``mdi:`` literal. Both halves are checked here, so "no hardcoded icons"
    cannot be produced by a broken glob or a broken pattern.
    """
    scanned = sorted(p.name for p in COMPONENT.rglob("*.py"))
    assert scanned, "the component glob matched nothing"
    for platform in ("binary_sensor.py", "button.py", "switch.py", "sensor.py"):
        assert platform in scanned, f"{platform} was not scanned: {scanned}"
    assert _MDI_LITERAL.findall('_attr_icon = "mdi:fire"') == ["mdi:fire"], (
        "the mdi literal pattern no longer matches the form it is meant to find"
    )
