"""Serve and register Poise's bundled Lovelace card (ADR-0040, Nachtrag N1).

The built ``poise-card.js`` (from ``card/``) ships inside the integration. We
serve it under a *version-stamped URL* and register that URL in the **Lovelace
resource collection** — the one loading path the Home Assistant frontend
documentation describes, and the one HACS cards take.

WHY NOT ``add_extra_js_url`` ANY MORE (N1). Until v0.194.0 this module used the
frontend's module-URL list. It looked robust — it loads on every dashboard, it
needs no write access to the resource collection — and it is not: that list is
baked into the served app shell and the card factory does NOT wait for its
imports. On a fast client the import wins the race every time; on a slower one
it loses it every time, and the loser is whichever view is built first. The
frontend caches rendered views, so returning to a broken view returns the
broken view. Measured in the field: every Poise card on the phone showed
"Konfigurationsfehler" while HACS cards on the same dashboard, in the same app,
rendered — because the resource collection is fetched live and awaited before
cards are built. See ``docs/reviews/2026-09-12-Card-Konfigurationsfehler-App.md``.

EXACTLY ONE LOADING PATH. Registering both ways would import the same module
twice; the four ``customElements.define`` calls in the bundle are guarded, so
nothing would throw, but the second path only exists to mask a failure in the
first. ``add_extra_js_url`` therefore remains as a FALLBACK and only where the
resource collection is genuinely unavailable: YAML-mode dashboards (writing
there is not ours to do) and any API shape this code cannot use.

THE STAMPED PATH STAYS. ADR-0040's reason is unchanged and independent of the
loading path: HA's service worker may serve a cached asset even when only the
query string moves, so the version goes in the *path*. With the resource
collection the stale-shell risk that a stamped path would otherwise create does
not arise — the collection is live data and is rewritten here on every upgrade.
"""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from ..const import CARD_MODULES, CARD_URL_BASE, VERSION
from .resources import plan_resources

_LOGGER = logging.getLogger(__name__)

# The resource collection is loaded by the ``lovelace`` integration, which has
# no ordering relationship to ours. Poll rather than depend on it: a missing
# collection is a "not yet", not an error, until it has stayed missing for a
# minute — at which point the fallback is the honest answer.
_RETRY_S: float = 5.0
_MAX_ATTEMPTS: int = 12
# Ownership prefix — with the trailing slash, so a hypothetical ``/poiseXYZ``
# resource of someone else's is never claimed.
_OWNED_PREFIX: str = f"{CARD_URL_BASE}/"


def _versioned_urls() -> tuple[str, ...]:
    """The URLs this Poise version serves, one per bundled module."""
    urls: list[str] = []
    for module in CARD_MODULES:
        filename = module["filename"]
        stem, _, ext = filename.rpartition(".")
        urls.append(f"{_OWNED_PREFIX}{stem}-{VERSION}.{ext or 'js'}")
    return tuple(urls)


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled card and get its URL into the resource collection.

    Serving is immediate and unconditional; the registration waits for the
    ``lovelace`` integration, because at ``async_setup`` time during a normal
    start it has not run yet. Never raises — the caller already treats a card
    failure as non-fatal, and this keeps that promise at the source.
    """
    here = Path(__file__).parent
    urls = _versioned_urls()
    configs: list[StaticPathConfig] = []
    for module, url in zip(CARD_MODULES, urls, strict=True):
        configs.append(StaticPathConfig(url, str(here / module["filename"]), False))
    try:
        await hass.http.async_register_static_paths(configs)
    except RuntimeError:
        _LOGGER.debug("Poise card static path already registered")

    if hass.is_running:
        await _async_attach(hass, urls, 0)
    else:
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, partial(_async_started, hass, urls)
        )


async def _async_started(
    hass: HomeAssistant, urls: tuple[str, ...], _event: Any
) -> None:
    await _async_attach(hass, urls, 0)


async def _async_attach_later(
    hass: HomeAssistant, urls: tuple[str, ...], attempt: int, _now: Any
) -> None:
    await _async_attach(hass, urls, attempt)


def _lovelace_part(lovelace: Any, name: str) -> Any:
    """Read ``name`` off the lovelace data, dataclass or legacy dict."""
    if lovelace is None:
        return None
    value = getattr(lovelace, name, None)
    if value is None and isinstance(lovelace, dict):
        value = lovelace.get(name)
    return value


def _retry_or_fall_back(
    hass: HomeAssistant, urls: tuple[str, ...], attempt: int, reason: str
) -> None:
    if attempt >= _MAX_ATTEMPTS:
        _fall_back(hass, urls, f"{reason} after {attempt} attempts")
        return
    async_call_later(
        hass, _RETRY_S, partial(_async_attach_later, hass, urls, attempt + 1)
    )


def _fall_back(hass: HomeAssistant, urls: tuple[str, ...], reason: str) -> None:
    """The pre-N1 loading path, for the cases the resource collection cannot serve.

    Logged at WARNING and not at DEBUG on purpose: this is the path with the
    race, so an installation running on it should be able to find out why from
    its own log instead of from a bug report.
    """
    _LOGGER.warning(
        "Poise card: registering as a frontend module URL because the Lovelace "
        "resource collection is unavailable (%s). The card may show "
        "'Configuration error' on slow clients until the view is rebuilt; on "
        "YAML dashboards, add %s as a 'module' resource to avoid this.",
        reason,
        ", ".join(urls),
    )
    for url in urls:
        add_extra_js_url(hass, url)


async def _async_attach(
    hass: HomeAssistant, urls: tuple[str, ...], attempt: int
) -> None:
    """Reconcile the resource collection towards ``urls`` (one attempt)."""
    lovelace = hass.data.get("lovelace")
    resources = _lovelace_part(lovelace, "resources")
    if resources is None:
        _retry_or_fall_back(hass, urls, attempt, "lovelace not set up")
        return

    mode = _lovelace_part(lovelace, "mode") or _lovelace_part(lovelace, "resource_mode")
    if mode != "storage":
        # YAML dashboards own their resource list; writing into it is not ours
        # to do, and the user's file would not even be the target.
        _fall_back(hass, urls, f"dashboard mode is {mode!r}")
        return

    if not getattr(resources, "loaded", False):
        _retry_or_fall_back(hass, urls, attempt, "resource collection not loaded")
        return

    try:
        existing = [
            (str(item["id"]), str(item["url"]))
            for item in resources.async_items()
            if item.get("id") is not None and item.get("url") is not None
        ]
        plan = plan_resources(existing, urls, prefix=_OWNED_PREFIX)
        if plan.is_noop:
            _LOGGER.debug("Poise card resource already registered: %s", urls)
            return
        # Order matters: update/create first, delete last, so there is never an
        # instant without a registered card (see ``ResourcePlan``).
        for resource_id, url in plan.update:
            await resources.async_update_item(resource_id, {"url": url})
        for url in plan.create:
            await resources.async_create_item({"res_type": "module", "url": url})
        for resource_id in plan.delete:
            await resources.async_delete_item(resource_id)
        _LOGGER.debug(
            "Poise card resources reconciled: +%d ~%d -%d -> %s",
            len(plan.create),
            len(plan.update),
            len(plan.delete),
            urls,
        )
    except Exception:  # noqa: BLE001 - a card failure must never break setup
        _LOGGER.exception("Poise card: resource registration failed")
        _fall_back(hass, urls, "resource registration raised")
