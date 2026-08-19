"""What third-party code can reach a Poise user — and whether it is pinned.

The integration itself ships ``"requirements": []`` (manifest), so the Python
side is a DEV toolchain: a compromised pytest never reaches an installation.
The card is the opposite. ``card/build.mjs`` runs esbuild with ``bundle:
true``, so ``lit`` is compiled INTO ``custom_components/poise/frontend/
poise-card.js`` — the 59 kB file every user downloads. npm is therefore the
only third-party supply chain with a path to users, and the lockfile is the
only thing standing in it.

This test guards the property ``npm ci`` needs in order to mean anything: a
lockfile entry pins CONTENT (an ``integrity`` hash against a registry URL),
not merely a version number. It is pure and offline — the network half
(``npm audit`` against the advisory database) is a scheduled CI job, because a
freshly published advisory must not turn an unrelated commit red.

Found by writing it: eight entries — the whole ``lit`` family, ``esbuild`` and
``typescript`` — carried version numbers and NO hash, i.e. exactly the packages
that end up in the shipped bundle.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = REPO_ROOT / "card" / "package-lock.json"
PACKAGE_JSON = REPO_ROOT / "card" / "package.json"
MANIFEST = REPO_ROOT / "custom_components" / "poise" / "manifest.json"

# The official registry. A mirror, a git URL or a raw tarball would all install
# fine and all defeat the audit trail, so the host is part of the assertion.
_REGISTRY = "https://registry.npmjs.org/"
# An exact version — no ``^``, no ``~``, no range, no tag. The card has three
# direct dependencies; "resolves to whatever is newest" is not a property this
# project wants for code that ships to users.
_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

# Every direct dependency, by name. Adding one is a deliberate act that has to
# pass through this list — which is the point: the tree is small enough that a
# new name deserves a conscious decision, not a silent lockfile line.
_ALLOWED_RUNTIME = frozenset({"lit"})
_ALLOWED_DEV = frozenset({"esbuild", "typescript"})


def _lockfile() -> dict[str, Any]:
    return json.loads(LOCKFILE.read_text(encoding="utf-8"))


def _package_json() -> dict[str, Any]:
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))


def is_hash_pinned(entry: dict[str, Any]) -> bool:
    """True when this lockfile entry pins CONTENT, not just a version."""
    resolved = entry.get("resolved")
    return bool(
        entry.get("integrity")
        and isinstance(resolved, str)
        and resolved.startswith(_REGISTRY)
    )


def is_exact_pin(spec: str) -> bool:
    """True for an exact version spec (no range, no tag, no URL)."""
    return bool(_EXACT_VERSION.match(spec))


def test_every_locked_package_is_content_pinned() -> None:
    """``npm ci`` verifies a tarball against the lockfile hash — when there is
    one. Without ``integrity`` it installs whatever the registry serves for
    that version today, which is the whole attack."""
    packages = _lockfile()["packages"]
    unpinned = sorted(
        name for name, entry in packages.items() if name and not is_hash_pinned(entry)
    )
    assert not unpinned, (
        "lockfile entries without an integrity hash from the official "
        f"registry: {unpinned}. `npm ci` cannot verify these — regenerate the "
        "lockfile with `rm -rf node_modules package-lock.json && npm install`."
    )


def test_direct_dependencies_are_the_allowlist_and_exactly_pinned() -> None:
    pkg = _package_json()
    runtime = pkg.get("dependencies", {})
    dev = pkg.get("devDependencies", {})
    assert set(runtime) == _ALLOWED_RUNTIME, (
        f"runtime dependencies changed: {sorted(runtime)} != "
        f"{sorted(_ALLOWED_RUNTIME)}. A runtime dependency is BUNDLED into the "
        "card and shipped to users — add it here on purpose or not at all."
    )
    assert set(dev) == _ALLOWED_DEV, (
        f"dev dependencies changed: {sorted(dev)} != {sorted(_ALLOWED_DEV)}. "
        "The build toolchain produces the shipped bundle, so it is part of the "
        "supply chain too."
    )
    loose = sorted(
        f"{name}@{spec}"
        for name, spec in {**runtime, **dev}.items()
        if not is_exact_pin(spec)
    )
    assert not loose, f"direct dependencies must be pinned exactly: {loose}"


def test_lockfile_root_version_tracks_the_card_package() -> None:
    """The lockfile carries its own copy of the package version; it sat at
    0.150.0 while the card shipped 0.192.0. Harmless on its own, but a
    lockfile that is not regenerated is exactly how hashes go missing."""
    assert _lockfile()["version"] == _package_json()["version"]


def test_the_integration_ships_no_python_runtime_dependency() -> None:
    """The Python side stays a dev-only chain. A runtime requirement here
    would open a second, user-facing supply chain that nothing above covers."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["requirements"] == [], (
        "the integration declared a Python runtime dependency — that is a new "
        "user-facing supply chain and needs its own gate (ADR/quality scale)."
    )


@pytest.mark.parametrize(
    ("label", "entry"),
    [
        ("no integrity at all", {"version": "3.3.3"}),
        (
            "version + resolved but no hash",
            {"version": "3.3.3", "resolved": f"{_REGISTRY}lit/-/lit-3.3.3.tgz"},
        ),
        (
            "hash but a git source",
            {"integrity": "sha512-x", "resolved": "git+ssh://git@github.com/x/y.git"},
        ),
        (
            "hash but a foreign mirror",
            {"integrity": "sha512-x", "resolved": "https://npm.internal.example/lit"},
        ),
    ],
)
def test_pin_detector_rejects_the_known_bad_shapes(
    label: str, entry: dict[str, Any]
) -> None:
    """Anti-vacuum control for ``is_hash_pinned``: the four shapes that install
    happily and verify nothing must each be caught. Self-contained on purpose —
    a control pointing at a real file would rot the moment that file is fixed.
    """
    assert not is_hash_pinned(entry), f"detector accepted {label}"


@pytest.mark.parametrize("spec", ["^3.3.3", "~3.3.3", ">=3.0.0", "latest", "3.3"])
def test_exact_pin_detector_rejects_ranges_and_tags(spec: str) -> None:
    assert not is_exact_pin(spec)


def test_detectors_accept_the_good_shape() -> None:
    """The other half of the control: both detectors must still say YES to a
    valid entry, or the two tests above would pass on a matcher that rejects
    everything."""
    assert is_hash_pinned(
        {"integrity": "sha512-x", "resolved": f"{_REGISTRY}lit/-/lit-3.3.3.tgz"}
    )
    assert is_exact_pin("3.3.3")
