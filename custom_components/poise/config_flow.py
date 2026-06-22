"""Config flow for Poise — guided per-room onboarding + reconfigure (ADR-0008).

One entry per room. Pick the room sensor and the thermostat/TRV to control;
optional inputs improve accuracy. The reconfigure step lets the saved settings
be edited in place without removing the entry (so learning is preserved).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ACTUATOR,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_BOILER_POWER_THRESHOLD,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_ENTRY_TYPE,
    CONF_HUMIDITY_SENSOR,
    CONF_IRRADIANCE,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    DEFAULT_BOILER_COUNT_THRESHOLD,
    DEFAULT_COMFORT_BASE,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_SETBACK_DELTA,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)


def _temp() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    )


def _schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default="Living room"): str,
            vol.Required(CONF_TEMP_SENSOR): _temp(),
            vol.Required(CONF_ACTUATOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            vol.Optional(CONF_TRM_SENSOR): _temp(),
            vol.Optional(CONF_OUTDOOR_SENSOR): _temp(),
            vol.Optional(CONF_HUMIDITY_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
            vol.Optional(CONF_MRT_SENSOR): _temp(),
            vol.Optional(CONF_WINDOW_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class=["window", "opening", "door"],
                )
            ),
            vol.Required(CONF_CATEGORY, default="II"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["I", "II", "III"],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_COMFORT_BASE, default=DEFAULT_COMFORT_BASE
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=16.0,
                    max=26.0,
                    step=0.5,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_CLIMATE_MODE, default="auto"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["auto", "heat_only", "cool_only"],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_COMFORT_WEIGHT, default=DEFAULT_COMFORT_WEIGHT
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=5, mode=selector.NumberSelectorMode.SLIDER
                )
            ),
            vol.Optional(CONF_COMFORT_START): selector.TimeSelector(),
            vol.Optional(CONF_COMFORT_END): selector.TimeSelector(),
            vol.Required(
                CONF_SETBACK_DELTA, default=DEFAULT_SETBACK_DELTA
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=8.0,
                    step=0.5,
                    unit_of_measurement="K",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_OPTIMAL_START, default=True): selector.BooleanSelector(),
            vol.Optional(CONF_WEATHER): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(CONF_IRRADIANCE): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="irradiance"
                )
            ),
            vol.Optional(CONF_TRV_EXTERNAL_TEMP): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="number")
            ),
            vol.Required(
                CONF_OPERATIVE_INPUT, default=False
            ): selector.BooleanSelector(),
        }
    )


def _system_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_BOILER_COUNT_THRESHOLD, default=DEFAULT_BOILER_COUNT_THRESHOLD
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=20, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(CONF_BOILER_POWER_THRESHOLD): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100000, step=0.1, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
    )


class PoiseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guided per-room config flow with reconfigure support."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["room", "system"])

    async def async_step_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ACTUATOR])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(step_id="room", data_schema=_schema())

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # singleton hub entry (ADR-0038)
        await self.async_set_unique_id("poise_system")
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title="Poise System",
                data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, **user_input},
            )
        return self.async_show_form(step_id="system", data_schema=_system_schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(_schema(), entry.data),
        )
