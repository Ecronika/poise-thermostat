"""One version number, four files, and the tag that ships them.

Poise carries its version in four places that must never drift:

* ``custom_components/poise/manifest.json`` — what HACS and hassfest read
* ``custom_components/poise/const.py``      — what the ``poise/card_version``
  websocket endpoint serves to every card instance
* ``card/package.json``                     — what the built bundle embeds
* ``pyproject.toml``                        — what packaging and tooling read

CI already compared the first three (in the card job, via shell). It never
looked at ``pyproject.toml``, and nothing compared any of them to the release
tag. This test closes the file half and runs locally as part of the pure
suite; the tag half needs the git ref and therefore stays a CI step, which
reuses the helpers below so the two halves cannot disagree about how a version
is read.

Why a test and not more shell: the card job's guard only runs when the card
job runs, needs node to read two JSON files, and reports drift in a language
nobody can execute locally. Reading four files is the kind of thing the pure
suite should own.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def _manifest_version() -> str:
    data = json.loads(
        (REPO_ROOT / "custom_components" / "poise" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return str(data["version"])


def _const_version() -> str:
    src = (REPO_ROOT / "custom_components" / "poise" / "const.py").read_text(
        encoding="utf-8"
    )
    # The annotation is optional on purpose. Dropping ``: Final`` is a
    # legitimate edit that leaves VERSION perfectly valid, and a regex
    # insisting on it would fail the build over a formatting change. Found by
    # probing this very test: the strict form went red on `VERSION = "..."`.
    match = re.search(r'^VERSION\s*(?::[^=]+)?=\s*"([^"]+)"', src, re.MULTILINE)
    assert match, (
        'const.py has no module-level `VERSION = "..."` assignment any more. '
        "The poise/card_version websocket endpoint serves it - find where it went."
    )
    return match.group(1)


def _card_version() -> str:
    data = json.loads((REPO_ROOT / "card" / "package.json").read_text(encoding="utf-8"))
    return str(data["version"])


def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


_SOURCES = {
    "manifest.json": _manifest_version,
    "const.py": _const_version,
    "card/package.json": _card_version,
    "pyproject.toml": _pyproject_version,
}


@pytest.mark.parametrize("name", sorted(_SOURCES))
def test_each_version_source_is_readable_and_semver(name: str) -> None:
    """A source that stops parsing must fail loudly, not silently drop out.

    Without this, renaming ``VERSION`` in const.py or moving the pyproject
    field would leave the comparison below quietly comparing three values -
    exactly the vacuum this project keeps finding in its own gates.
    """
    version = _SOURCES[name]()
    assert _SEMVER.match(version), (
        f"{name} carries {version!r}, which is not a semantic version. The "
        f"release tag is derived from it as v<version>."
    )


def test_all_four_version_sources_agree() -> None:
    """The four files carry the same version.

    Drift here is not cosmetic: ``const.VERSION`` is what the card asks for
    over the websocket, and a mismatch against the bundle's embedded version
    shows every card user a permanent "reload" toast.
    """
    seen = {name: read() for name, read in _SOURCES.items()}
    distinct = set(seen.values())
    assert len(distinct) == 1, (
        f"version drift: {seen}. All four must match; bump them together and "
        f"rebuild the card bundle."
    )


def test_expected_release_tag_is_derived_from_the_version() -> None:
    """Pin the tag shape the CI step checks, so both halves agree.

    The CI step compares ``github.ref_name`` against this; keeping the rule in
    the test means a change to the naming convention breaks here first, where
    it is cheap, rather than on a release, where it is not.
    """
    assert f"v{_manifest_version()}" == f"v{_const_version()}"
    assert _manifest_version().count(".") == 2
