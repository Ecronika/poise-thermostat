"""Serve and auto-register Poise's bundled Lovelace card (ADR-0040).

The built ``poise-card.js`` (from ``card/``) ships inside the integration and is
served at ``CARD_URL_BASE``. In Lovelace storage mode the resource is registered
automatically; in YAML mode the file is reachable and the user adds it once.
This is HA glue (no HA runtime in the sandbox) — verified live, like the
coordinator. It never touches control state.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from ..const import CARD_MODULES, CARD_URL_BASE, VERSION

_LOGGER = logging.getLogger(__name__)


class JSModuleRegistration:
    """Register the bundled card as a static path + Lovelace resource."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.lovelace = hass.data.get("lovelace")

    async def async_register(self) -> None:
        await self._register_static_path()
        mode = getattr(self.lovelace, "mode", None)
        if mode == "storage":
            await self._wait_for_resources()

    async def _register_static_path(self) -> None:
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL_BASE, str(Path(__file__).parent), False)]
            )
        except RuntimeError:
            _LOGGER.debug("Poise card path already registered")

    async def _wait_for_resources(self) -> None:
        async def _check(_now: Any) -> None:
            resources = getattr(self.lovelace, "resources", None)
            if resources is None:
                return
            if getattr(resources, "loaded", False):
                await self._register_modules()
            else:
                async_call_later(self.hass, 5, _check)

        await _check(0)

    async def _register_modules(self) -> None:
        resources = self.lovelace.resources
        existing = [
            r for r in resources.async_items() if r["url"].startswith(CARD_URL_BASE)
        ]
        for module in CARD_MODULES:
            url = f"{CARD_URL_BASE}/{module['filename']}"
            versioned = f"{url}?v={VERSION}"
            match = next((r for r in existing if r["url"].split("?")[0] == url), None)
            if match is None:
                _LOGGER.info("Registering Poise card resource %s", versioned)
                await resources.async_create_item(
                    {"res_type": "module", "url": versioned}
                )
            elif match["url"] != versioned:
                await resources.async_update_item(
                    match["id"], {"res_type": "module", "url": versioned}
                )
