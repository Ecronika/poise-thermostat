"""ADR status hygiene (Phase 8 ADR-Status-Linter).

The index table in ``docs/adr/README.md`` must stay in lockstep with each ADR's
own ``**Status:**`` header — that is the ADR-0000 convention ("Der Status in der
Tabelle entspricht dem Status-Header im jeweiligen ADR"). This test catches the
drift class where an ADR header is bumped per-increment but the index cell lags
(or vice versa) — exactly the 0020/0050/0052/0053/0056 lags found by hand during
the v0.148 doc sync. Pure and HA-free, so it runs in the ``quality`` job.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parents[1] / "docs" / "adr"

# The status vocabulary from docs/adr/README.md ("Status-Konventionen").
ALLOWED_BASES = {
    "Implementiert",
    "In Arbeit",
    "Vorgeschlagen",
    "Ersetzt",
    "Veraltet",
    "Gültig",
}

# The Wirkung (actuation-effect) vocabulary from docs/adr/README.md
# ("Wirkungs-Konventionen") — orthogonal to Status. Every ADR header carries a
# ``**Wirkung:** <token>`` field right after the ``**Status:**`` token.
ALLOWED_WIRKUNG = {
    "Live-A",  # actuates in the live write path
    "Live-D",  # runs every tick, diagnostic only
    "Shadow",  # computed, never writes
    "teilw.",  # partially wired
    "Harness",  # test-only
    "Doku",  # documentation/decision only
    "Gültig",  # meta/process record
    "n.a.",  # not applicable / not yet built
}


def _base(status: str) -> str:
    """The bare status word(s): drop any ``(… %)`` / ``(Shadow, …)`` detail and
    any ``durch ADR-XXXX`` tail so ``In Arbeit (Shadow, ~40 %)`` and
    ``In Arbeit (40 %)`` compare equal on their base."""
    s = re.sub(r"\s*\(.*?\)\s*", " ", status).strip()
    return re.sub(r"\s+durch\s+ADR-\d+.*$", "", s).strip()


def _pct(status: str) -> int | None:
    m = re.search(r"(\d+)\s*%", status)
    return int(m.group(1)) if m else None


def _headers() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(ADR_DIR.glob("ADR-*.md")):
        num = re.match(r"ADR-(\d{4})-", path.name)
        if num is None:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\*\*Status:\*\*\s*(.*?)\s*·", line)
            if m:
                out[num.group(1)] = m.group(1).strip()
                break
        else:
            raise AssertionError(f"{path.name}: no '**Status:** … ·' header line")
    return out


def _wirkungen() -> dict[str, str]:
    """The ``**Wirkung:** <token>`` value from each ADR's status line — parsed in
    the same style as ``_headers()`` (the field sits on the ``**Status:**`` line,
    ``·``-separated). Raises if an ADR header carries no ``**Wirkung:**`` field so
    a newly added ADR that forgets the dimension fails the lint."""
    out: dict[str, str] = {}
    for path in sorted(ADR_DIR.glob("ADR-*.md")):
        num = re.match(r"ADR-(\d{4})-", path.name)
        if num is None:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("**Status:**"):
                continue
            m = re.search(r"\*\*Wirkung:\*\*\s*([^·\n]+?)\s*(?:·|$)", line)
            if m is None:
                raise AssertionError(
                    f"{path.name}: '**Status:**' line lacks '**Wirkung:** <token>'"
                )
            out[num.group(1)] = m.group(1).strip()
            break
        else:
            raise AssertionError(f"{path.name}: no '**Status:** … ·' header line")
    return out


def _index() -> dict[str, str]:
    out: dict[str, str] = {}
    text = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        m = re.match(r"\|\s*\[(\d{4})\]", line)
        if m:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out[m.group(1)] = cells[-1]
    return out


def test_adr_index_and_headers_are_bijective() -> None:
    hdr, idx = _headers(), _index()
    assert set(hdr) == set(idx), (
        f"index-only rows={sorted(set(idx) - set(hdr))}; "
        f"ADR files without an index row={sorted(set(hdr) - set(idx))}"
    )


def test_adr_index_status_matches_header() -> None:
    hdr, idx = _headers(), _index()
    drift = [
        f"{n}: header={hdr[n]!r} index={idx[n]!r}"
        for n in sorted(set(hdr) & set(idx))
        if _base(hdr[n]) != _base(idx[n]) or _pct(hdr[n]) != _pct(idx[n])
    ]
    assert not drift, "ADR status drift (header vs index):\n  " + "\n  ".join(drift)


def test_adr_statuses_are_from_the_allowed_set() -> None:
    unknown = {n: s for n, s in _headers().items() if _base(s) not in ALLOWED_BASES}
    assert not unknown, f"unknown ADR status base(s): {unknown}"


def test_every_adr_has_a_wirkung_field() -> None:
    # _wirkungen() itself raises if any ADR header lacks a '**Wirkung:**' field;
    # this asserts every ADR file is covered (parity with the status headers).
    assert set(_wirkungen()) == set(_headers())


def test_adr_wirkung_tokens_are_from_the_allowed_set() -> None:
    unknown = {n: w for n, w in _wirkungen().items() if w not in ALLOWED_WIRKUNG}
    assert not unknown, f"unknown ADR Wirkung token(s): {unknown}"
