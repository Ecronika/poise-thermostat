"""Config flow for Poise (ADR-0008 zero-question hub).

Adding the integration creates a single hub entry immediately — no questions.
Rooms/zones are configured afterward via the options flow (Phase 5). The
``single_config_entry`` flag in the manifest enforces the single instance.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class PoiseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Zero-question hub config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single Poise hub entry."""
        return self.async_create_entry(title="Poise", data={})
