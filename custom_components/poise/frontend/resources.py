"""Which Lovelace resource entries the bundled card needs — pure (ADR-0040 N1).

The decision half of the resource registration, kept free of Home Assistant so
it can be reasoned about and tested on its own. The dispatch half — waiting for
the resource collection, the storage/YAML gate, the actual create/update/delete
calls — lives in ``frontend/__init__.py``.

WHY A PLAN INSTEAD OF THREE IMPERATIVE CALLS. Poise stamps the card's URL with
its version, so every upgrade changes the URL that must be registered. Three
things can therefore be true at once when this runs: an entry with the right
URL already exists (do nothing), an entry with an OLD Poise URL exists (move it
to the new one), or several entries exist (the user added one by hand as a
workaround, or an earlier version created a second). Deciding all of that in one
place, over a list, is the only way the duplicate case stops being an accident.

OWNERSHIP is by URL prefix and nothing else: an entry whose path starts with
``/poise/`` belongs to this integration, everything else is someone's own
configuration and is never touched. The query string is ignored for the
comparison so a hand-added ``?v=…`` still counts as ours.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResourcePlan:
    """What to do to the Lovelace resource collection, in this order.

    ``update`` before ``delete`` on purpose: applied in that order there is
    never an instant in which no Poise resource is registered, so a dashboard
    loading during the upgrade still finds a card.
    """

    update: tuple[tuple[str, str], ...] = ()  # (resource_id, new url)
    create: tuple[str, ...] = ()  # urls
    delete: tuple[str, ...] = ()  # resource_ids

    @property
    def is_noop(self) -> bool:
        """True when the collection already says exactly the right thing.

        The normal case on every restart that did not change the version — and
        worth naming, because writing an unchanged item would bump the storage
        collection and make every open dashboard reload for nothing.
        """
        return not (self.update or self.create or self.delete)


def _path(url: str) -> str:
    """The URL without query or fragment — what ownership is judged by."""
    return url.split("?", 1)[0].split("#", 1)[0]


def plan_resources(
    existing: Sequence[tuple[str, str]],
    desired: Sequence[str],
    *,
    prefix: str,
) -> ResourcePlan:
    """Reconcile the resource collection towards ``desired``.

    ``existing`` is ``(resource_id, url)`` for every entry in the collection,
    ours and foreign alike; ``desired`` the URLs this Poise version serves.

    The rules, in the order they are applied:

    1. an owned entry that already carries a desired URL is left alone — and
       consumes that URL, so it is not created a second time;
    2. every remaining desired URL re-uses a remaining owned entry
       (``update``) before a new one is created — moving the old entry is what
       keeps the collection from growing by one per Poise release;
    3. owned entries still left over are deleted. That is the duplicate case:
       a second entry someone added by hand while debugging, or one from a
       version that registered twice.

    Foreign entries are invisible to all three rules.
    """
    mine = [(rid, url) for rid, url in existing if _path(url).startswith(prefix)]
    wanted = list(desired)

    # Rule 1 — but only ONE entry may satisfy a URL. A second entry carrying
    # the SAME correct URL is still a duplicate and stays claimable by rule 3.
    satisfied: set[str] = set()
    kept: set[str] = set()
    for rid, url in mine:
        if url in wanted and url not in satisfied:
            satisfied.add(url)
            kept.add(rid)

    free_ids = [rid for rid, _ in mine if rid not in kept]
    todo = [url for url in wanted if url not in satisfied]

    update: list[tuple[str, str]] = []
    for url in todo:
        if not free_ids:
            break
        update.append((free_ids.pop(0), url))

    create = tuple(todo[len(update) :])
    return ResourcePlan(update=tuple(update), create=create, delete=tuple(free_ids))
