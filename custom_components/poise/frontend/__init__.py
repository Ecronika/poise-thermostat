"""Serve and load Poise's bundled Lovelace card (ADR-0040).

The built ``poise-card.js`` (from ``card/``) ships inside the integration. We
serve it as a static path and load it as a **frontend module URL**
(`add_extra_js_url`) — the robust, widely-used way to ship an integration-owned
card: it loads on every dashboard, so the card self-registers in the card picker
without touching the (HA-version-fragile) Lovelace resource collection. This is
HA glue (no HA runtime in the sandbox) — verified live. It never touches control
state.
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
    """Serve the bundled card directory and load the card module(s)."""
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(Path(__file__).parent), False)]
        )
    except RuntimeError:
        _LOGGER.debug("Poise card static path already registered")
    for module in CARD_MODULES:
        url = f"{CARD_URL_BASE}/{module['filename']}?v={VERSION}"
        add_extra_js_url(hass, url)
        _LOGGER.debug("Poise card module loaded: %s", url)
