"""The set of repair issues this entry currently owns (plan S.3).

A three-line wrapper around a ``set[str]`` earns its place for one reason:
IDENTITY. The coordinator re-adopts the entry's issues during
``async_bootstrap``, and it used to do that by REBINDING the attribute
(``self._active_issues = {...}``). Anything that had taken a reference to the
old set — the health reporter, which was constructed long before — silently
pointed at a dead object from that moment on. That is why the reporter carried
a coordinator backreference at all: not because it needed the coordinator, but
because it needed the *current* set.

``adopt()`` replaces the CONTENT in place, so a holder keeps working. The
backreference then has no reason left to exist, which is what S.3 removed.

Pure: no Home Assistant, no logging, no I/O. The registry side effects stay in
``ha/health_reporter.py`` — this only remembers which ids are raised.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator


class IssueLedger:
    """Which repair-issue ids are currently raised for one config entry."""

    __slots__ = ("_ids",)

    def __init__(self, ids: Iterable[str] = ()) -> None:
        self._ids: set[str] = set(ids)

    def __contains__(self, issue_id: str) -> bool:
        return issue_id in self._ids

    def __iter__(self) -> Iterator[str]:
        return iter(self._ids)

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, issue_id: str) -> None:
        self._ids.add(issue_id)

    def discard(self, issue_id: str) -> None:
        self._ids.discard(issue_id)

    def adopt(self, ids: Iterable[str]) -> None:
        """Replace the content in place (the bootstrap re-adoption).

        In place, not by rebinding: every holder of this ledger must observe
        the new set. That is the whole point of the class.
        """
        self._ids = set(ids)

    def snapshot(self) -> tuple[str, ...]:
        """A stable copy for iteration while the ledger is being mutated.

        The teardown path deletes issues one by one and discards them as it
        goes; iterating the live set during that would be undefined.
        """
        return tuple(sorted(self._ids))
