"""Config flow for Poise — guided per-room onboarding (ADR-0008).

One entry per room. Pick the room sensor and the thermostat/TRV to control;
optional inputs (running-mean outdoor, humidity, MRT) improve accuracy and
unlock mould protection / operative-temperature control.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_HUMIDITY_SENSOR,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OUTDOOR_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)


def _temp() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    )


class PoiseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guided per-room config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ACTUATOR])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Living room"): str,
                vol.Required(CONF_TEMP_SENSOR): _temp(),
                vol.Required(CONF_ACTUATOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Optional(CONF_TRM_SENSOR): _temp(),
                vol.Optional(CONF_OUTDOOR_SENSOR): _temp(),
                vol.Optional(CONF_HUMIDITY_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="humidity"
                    )
                ),
                vol.Optional(CONF_MRT_SENSOR): _temp(),
                vol.Required(CONF_CATEGORY, default="II"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["I", "II", "III"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
