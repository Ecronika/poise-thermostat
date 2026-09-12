"""The Lovelace resource plan: one entry, ours, current (ADR-0040 N1).

Pure — no Home Assistant, no fixtures. The dispatch half in
``frontend/__init__.py`` does nothing this module does not decide, so a green
here is a statement about the real registration.

Background: ``docs/reviews/2026-09-12-Card-Konfigurationsfehler-App.md``. The
card was loaded through the frontend's module-URL list, whose imports the card
factory does not await; on the Android Companion app every Poise card showed
"Konfigurationsfehler" while HACS cards on the same dashboard rendered. The
resource collection is the path HACS takes — and it has to be reconciled rather
than appended to, because the URL carries the version.
"""

from __future__ import annotations

from custom_components.poise.frontend.resources import ResourcePlan, plan_resources

_P = "/poise/"
_V1 = "/poise/poise-card-0.194.0.js"
_V2 = "/poise/poise-card-0.194.1.js"


def test_a_fresh_install_creates_exactly_one_entry() -> None:
    plan = plan_resources([], [_V2], prefix=_P)
    assert plan == ResourcePlan(create=(_V2,))


def test_an_unchanged_version_writes_nothing() -> None:
    """The normal restart. A write here would bump the storage collection and
    make every open dashboard reload for no reason."""
    assert plan_resources([("1", _V2)], [_V2], prefix=_P).is_noop


def test_an_upgrade_moves_the_entry_instead_of_adding_one() -> None:
    """The whole reason a plan exists: the URL carries the version, so a
    create-only registration would grow the collection by one per release —
    and every stale entry points at a 404, because only the CURRENT version's
    static path is served."""
    plan = plan_resources([("1", _V1)], [_V2], prefix=_P)
    assert plan == ResourcePlan(update=(("1", _V2),))


def test_a_hand_added_duplicate_is_consolidated_on_upgrade() -> None:
    """The workaround case, and it is not hypothetical: while the module-URL
    path was broken the documented interim fix was to add the resource by
    hand. The next upgrade must end with ONE entry, not three."""
    plan = plan_resources([("1", _V1), ("2", _V1)], [_V2], prefix=_P)
    assert plan.update == (("1", _V2),)
    assert plan.create == ()
    assert plan.delete == ("2",)


def test_a_duplicate_of_the_correct_url_is_still_removed() -> None:
    """Two entries with the same, right URL are not 'already correct' — the
    card would import once but the picker would list it twice."""
    plan = plan_resources([("1", _V2), ("2", _V2)], [_V2], prefix=_P)
    assert plan.update == () and plan.create == ()
    assert plan.delete == ("2",)


def test_foreign_resources_are_invisible() -> None:
    """Ownership is the URL prefix and nothing else. A HACS entry, a user's own
    module, a card from another integration — none of them may be moved or
    deleted by us, ever."""
    existing = [
        ("h1", "/hacsfiles/better-thermostat-ui-card/x.js"),
        ("h2", "/local/my-card.js"),
        ("1", _V2),
    ]
    assert plan_resources(existing, [_V2], prefix=_P).is_noop


def test_a_neighbouring_prefix_is_not_ours() -> None:
    """``/poise`` without the trailing slash would claim ``/poisedon/...``."""
    plan = plan_resources([("x", "/poisedon/card.js")], [_V2], prefix=_P)
    assert plan == ResourcePlan(create=(_V2,))
    assert "x" not in plan.delete


def test_a_hand_added_query_version_is_recognised_as_ours() -> None:
    """Ownership ignores the query string, so the documented manual workaround
    (with or without ``?v=``) is adopted rather than duplicated."""
    plan = plan_resources([("1", f"{_V1}?v=0.194.0")], [_V2], prefix=_P)
    assert plan == ResourcePlan(update=(("1", _V2),))


def test_the_plan_orders_deletes_last() -> None:
    """Applied as ``update -> create -> delete`` there is never an instant in
    which no Poise resource is registered — a dashboard loading during the
    upgrade still finds a card. The dataclass field order IS that contract."""
    fields = list(ResourcePlan.__dataclass_fields__)
    assert fields == ["update", "create", "delete"]
