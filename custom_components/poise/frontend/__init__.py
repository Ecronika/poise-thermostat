"""Serve and load Poise's bundled Lovelace card (ADR-0040).

The built ``poise-card.js`` (from ``card/``) ships inside the integration. We
serve it under a *version-stamped URL* and load it as a **frontend module URL**
(``add_extra_js_url``) — the robust, widely-used way to ship an
integration-owned card: it loads on every dashboard, so the card self-registers
in the card picker without touching the (HA-version-fragile) Lovelace resource
collection. This is HA glue (no HA runtime in the sandbox) — verified live. It
never touches control state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from ..const import CARD_MODULES, CARD_URL_BASE, VERSION

_LOGGER = logging.getLogger(__name__)


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled card under a version-stamped URL and load it.

    HA's frontend service worker caches asset URLs aggressively and may serve a
    stale module even when only the query string (``?v=``) changes. Stamping the
    *path* with the version (``poise-card-<version>.js``) yields a URL the browser
    has never seen before, so each upgrade is fetched fresh — no manual
    hard-reload, no stale card overflowing its grid cell. The versioned URL is
    mapped onto the single on-disk file via a per-file static path, so no extra
    files accumulate on disk.
    """
    here = Path(__file__).parent
    configs = []
    urls = []
    for module in CARD_MODULES:
        filename = module["filename"]
        stem, _, ext = filename.rpartition(".")
        versioned = f"{CARD_URL_BASE}/{stem}-{VERSION}.{ext or 'js'}"
        configs.append(StaticPathConfig(versioned, str(here / filename), False))
        urls.append(versioned)
    try:
        await hass.http.async_register_static_paths(configs)
    except RuntimeError:
        _LOGGER.debug("Poise card static path already registered")
    for url in urls:
        add_extra_js_url(hass, url)
        _LOGGER.debug("Poise card module loaded: %s", url)
