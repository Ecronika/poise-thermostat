"""Config flow for Poise — guided per-room onboarding + reconfigure (ADR-0008).

One entry per room. Pick the room sensor and the thermostat/TRV to control;
optional inputs improve accuracy. The reconfigure step lets the saved settings
be edited in place without removing the entry (so learning is preserved).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.util.unit_system import US_CUSTOMARY_UNITS

from .adaptive_cool import adaptive_cool_mode
from .comfort.thermal_shock import DEFAULT_HARD_CAP_C, DEFAULT_SHOCK_DELTA_K
from .config_reconcile import reconcile_reconfigure
from .config_sections import flatten_sections, nest_by_section
from .const import (
    COMPRESSOR_GUARD_AUTO,
    COMPRESSOR_GUARD_OFF,
    CONF_ABSENCE_AFTER_MIN,
    CONF_ACTUATOR,
    CONF_ADAPTIVE_COOL,
    CONF_ANNUAL_KWH,
    CONF_BOILER_ACTIVATION_DELAY,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_BOILER_KEEPALIVE,
    CONF_BOILER_MIN_OFF,
    CONF_BOILER_MIN_ON,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_BOILER_POWER_THRESHOLD,
    CONF_BOOST_DURATION_MIN,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_COMPRESSOR_GROUP,
    CONF_COMPRESSOR_GUARD,
    CONF_COMPRESSOR_MIN_OFF,
    CONF_COMPRESSOR_MODE_HOLD,
    CONF_CONTROLS_BOILER,
    CONF_COOL_HARD_CAP,
    CONF_COOL_LOCKOUT_ENABLED,
    CONF_COOL_MIN_OUTDOOR,
    CONF_CURRENT_POWER_SENSOR,
    CONF_DECLARED_POWER,
    CONF_DEFAULT_SOURCE,
    CONF_DYNAMICS,
    CONF_ENTRY_TYPE,
    CONF_FLOW_HYSTERESIS,
    CONF_FLOW_TEMP,
    CONF_HEAT_LOCKOUT_ENABLED,
    CONF_HEAT_MAX_OUTDOOR,
    CONF_HUMIDITY_SENSOR,
    CONF_IRRADIANCE,
    CONF_MAX_FLOW_TEMP,
    CONF_MAX_POWER_SENSOR,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_OVERRIDE_END_ON_PRESENCE,
    CONF_OVERRIDE_MAX_H,
    CONF_OVERRIDE_POLICY,
    CONF_OVERRIDE_TIMER_H,
    CONF_PRESENCE_HOME,
    CONF_PRICE_EUR_KWH,
    CONF_SETBACK_DELTA,
    CONF_SOURCE_POLICY,
    CONF_TEMP_SENSOR,
    CONF_THERMAL_SHOCK_DELTA,
    CONF_TRACE_RECORDING,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    DEFAULT_ABSENCE_AFTER_MIN,
    DEFAULT_ADAPTIVE_COOL,
    DEFAULT_ANNUAL_KWH,
    DEFAULT_BOILER_ACTIVATION_DELAY_S,
    DEFAULT_BOILER_COUNT_THRESHOLD,
    DEFAULT_BOILER_KEEPALIVE_S,
    DEFAULT_BOILER_MIN_OFF_S,
    DEFAULT_BOILER_MIN_ON_S,
    DEFAULT_BOOST_DURATION_MIN,
    DEFAULT_COMFORT_BASE,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_COOL_LOCKOUT_ENABLED,
    DEFAULT_COOL_MIN_OUTDOOR_C,
    DEFAULT_DYNAMICS,
    DEFAULT_FLOW_HYSTERESIS_C,
    DEFAULT_HEAT_LOCKOUT_ENABLED,
    DEFAULT_HEAT_MAX_OUTDOOR_C,
    DEFAULT_HEAT_SOURCE,
    DEFAULT_MAX_FLOW_TEMP_C,
    DEFAULT_OVERRIDE_END_ON_PRESENCE,
    DEFAULT_OVERRIDE_MAX_H,
    DEFAULT_OVERRIDE_POLICY,
    DEFAULT_OVERRIDE_TIMER_H,
    DEFAULT_PRICE_EUR_KWH,
    DEFAULT_SETBACK_DELTA,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    FROST_FLOOR_C,
)
from .control.hub_aggregate import parse_service_action

_DYNAMICS_OPTIONS = ["auto", "fast_air", "slow_hydronic", "very_slow"]

# Options-flow section groups (ADR-0008): the single source of truth for which
# tuning field lives in which collapsible section. Drives both the schema and the
# flatten (submit) / nest (display) of the sectioned values (config_sections).
_OPTIONS_SECTIONS: dict[str, tuple[str, ...]] = {
    "comfort": (
        CONF_COMFORT_BASE,
        CONF_CATEGORY,
        CONF_COMFORT_WEIGHT,
    ),
    "schedule": (
        CONF_COMFORT_START,
        CONF_COMFORT_END,
        CONF_SETBACK_DELTA,
        CONF_OPTIMAL_START,
    ),
    "heat_cool": (
        CONF_ADAPTIVE_COOL,
        CONF_COOL_MIN_OUTDOOR,
        CONF_COOL_LOCKOUT_ENABLED,
        CONF_HEAT_MAX_OUTDOOR,
        CONF_HEAT_LOCKOUT_ENABLED,
    ),
    "presence": (CONF_PRESENCE_HOME, CONF_OCCUPANCY_SENSOR, CONF_ABSENCE_AFTER_MIN),
    "manual_override": (
        CONF_OVERRIDE_POLICY,
        CONF_OVERRIDE_TIMER_H,
        CONF_OVERRIDE_MAX_H,
        CONF_OVERRIDE_END_ON_PRESENCE,
        CONF_BOOST_DURATION_MIN,
        # CONF_OVERRIDE_SUGGESTIONS is latent (L2/v2, ADR-0059) and intentionally
        # not exposed in the UI yet; kept in const.py for the future override
        # learning feature.
    ),
    "advanced": (
        CONF_COOL_HARD_CAP,
        CONF_THERMAL_SHOCK_DELTA,
        CONF_OPERATIVE_INPUT,
        CONF_DYNAMICS,
        CONF_COMPRESSOR_GUARD,
        CONF_COMPRESSOR_MIN_OFF,
        CONF_COMPRESSOR_MODE_HOLD,
        CONF_TRACE_RECORDING,
    ),
    "energy": (CONF_ANNUAL_KWH, CONF_PRICE_EUR_KWH),
}


_RECONFIGURE_SECTIONS: dict[str, tuple[str, ...]] = {
    "sensors": (
        CONF_TRM_SENSOR,
        CONF_OUTDOOR_SENSOR,
        CONF_HUMIDITY_SENSOR,
        CONF_MRT_SENSOR,
        CONF_WINDOW_SENSOR,
        CONF_WEATHER,
        CONF_IRRADIANCE,
        CONF_TRV_EXTERNAL_TEMP,
    ),
    "anlagen": (
        CONF_CONTROLS_BOILER,
        CONF_COMPRESSOR_GROUP,
        CONF_DECLARED_POWER,
        CONF_FLOW_TEMP,
        CONF_SOURCE_POLICY,
    ),
}


def _temp(exclude: list[str] | None = None) -> selector.EntitySelector:
    cfg = selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    if exclude:
        cfg["exclude_entities"] = exclude
    return selector.EntitySelector(cfg)


def _reconfigure_schema(
    hass: HomeAssistant, hub_exists: bool | None = None
) -> vol.Schema:
    """Room reconfigure (ADR-0008): structural wiring only — the room sensor +
    actuator, the optional sensor entities, and (only when a system hub exists) the
    shared-plant fields. Tuning is edited hot in the options flow, so it is not
    repeated here; reconcile_reconfigure carries any tuning still in data across."""
    reg = er.async_get(hass)
    own = [e.entity_id for e in reg.entities.values() if e.platform == DOMAIN]
    climate_cfg = selector.EntitySelectorConfig(domain="climate")
    if own:
        climate_cfg["exclude_entities"] = own
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_TEMP_SENSOR): _temp(own),
        vol.Required(CONF_ACTUATOR): selector.EntitySelector(climate_cfg),
        vol.Required("sensors"): section(
            vol.Schema(
                {
                    vol.Optional(CONF_TRM_SENSOR): _temp(own),
                    vol.Optional(CONF_OUTDOOR_SENSOR): _temp(own),
                    vol.Optional(CONF_HUMIDITY_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor",
                            device_class="humidity",
                            exclude_entities=own,
                        )
                    ),
                    vol.Optional(CONF_MRT_SENSOR): _temp(own),
                    vol.Optional(CONF_WINDOW_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="binary_sensor",
                            device_class=["window", "opening", "door"],
                            multiple=True,
                            exclude_entities=own,
                        )
                    ),
                    vol.Optional(CONF_WEATHER): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="weather")
                    ),
                    vol.Optional(CONF_IRRADIANCE): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor", device_class="irradiance"
                        )
                    ),
                    vol.Optional(CONF_TRV_EXTERNAL_TEMP): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="number", exclude_entities=own
                        )
                    ),
                }
            ),
            {"collapsed": True},
        ),
    }
    if hub_exists is None:
        hub_exists = any(
            e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM
            for e in hass.config_entries.async_entries(DOMAIN)
        )
    if hub_exists:
        schema[vol.Required("anlagen")] = section(
            vol.Schema(
                {
                    vol.Required(
                        CONF_CONTROLS_BOILER, default=False
                    ): selector.BooleanSelector(),
                    vol.Optional(CONF_COMPRESSOR_GROUP): selector.TextSelector(),
                    vol.Optional(CONF_DECLARED_POWER): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100000,
                            step=0.1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(CONF_FLOW_TEMP): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=20,
                            max=80,
                            step=1,
                            unit_of_measurement="°C",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(CONF_SOURCE_POLICY): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["auto", "radiator", "heat_pump"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            {"collapsed": True},
        )
    return vol.Schema(schema)


def _setup_schema(hass: HomeAssistant) -> vol.Schema:
    """Slim room onboarding (ADR-0008): only the room sensor + actuator up front
    (the name is derived from the actuator), with the accuracy-improving optional
    inputs behind a collapsed section. All tuning has good defaults and is edited
    later in the options flow."""
    # Don't offer Poise's own entities (its zone climate + diagnostic sensors) in
    # the pickers — selecting one would wire a zone to itself.
    reg = er.async_get(hass)
    own = [e.entity_id for e in reg.entities.values() if e.platform == DOMAIN]
    climate_cfg = selector.EntitySelectorConfig(domain="climate")
    if own:
        climate_cfg["exclude_entities"] = own
    return vol.Schema(
        {
            vol.Optional(CONF_NAME): selector.TextSelector(),
            vol.Required(CONF_TEMP_SENSOR): _temp(own),
            vol.Required(CONF_ACTUATOR): selector.EntitySelector(climate_cfg),
            vol.Required("accuracy"): section(
                vol.Schema(
                    {
                        vol.Optional(
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
                        vol.Optional(
                            CONF_CATEGORY, default="II"
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=["I", "II", "III"],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Optional(CONF_OUTDOOR_SENSOR): _temp(own),
                        vol.Optional(CONF_HUMIDITY_SENSOR): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="sensor",
                                device_class="humidity",
                                exclude_entities=own,
                            )
                        ),
                        vol.Optional(CONF_WINDOW_SENSOR): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="binary_sensor",
                                device_class=["window", "opening", "door"],
                                multiple=True,
                                exclude_entities=own,
                            )
                        ),
                        vol.Optional(CONF_WEATHER): selector.EntitySelector(
                            selector.EntitySelectorConfig(domain="weather")
                        ),
                    }
                ),
                {"collapsed": True},
            ),
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
            vol.Optional(CONF_BOILER_ON_ACTION): selector.TextSelector(),
            vol.Optional(CONF_BOILER_OFF_ACTION): selector.TextSelector(),
            vol.Required(
                CONF_BOILER_ACTIVATION_DELAY, default=DEFAULT_BOILER_ACTIVATION_DELAY_S
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=600,
                    step=5,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_BOILER_KEEPALIVE, default=DEFAULT_BOILER_KEEPALIVE_S
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=600,
                    step=5,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_BOILER_MIN_ON, default=DEFAULT_BOILER_MIN_ON_S
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=120,
                    max=3600,
                    step=30,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_BOILER_MIN_OFF, default=DEFAULT_BOILER_MIN_OFF_S
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=120,
                    max=3600,
                    step=30,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_MAX_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_CURRENT_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Required(
                CONF_MAX_FLOW_TEMP, default=DEFAULT_MAX_FLOW_TEMP_C
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=30,
                    max=90,
                    step=1,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_FLOW_HYSTERESIS, default=DEFAULT_FLOW_HYSTERESIS_C
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=10,
                    step=0.5,
                    unit_of_measurement="K",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_DEFAULT_SOURCE, default=DEFAULT_HEAT_SOURCE
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["radiator", "heat_pump"],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _options_schema(hass: HomeAssistant) -> vol.Schema:
    """Volatile tuning, hot-applied without a reload (A10), grouped into
    collapsible sections (ADR-0008). Only fields the coordinator can update in
    place live here; structural inputs stay in the reconfigure step. The sectioned
    submit is flattened before storage (config_sections)."""
    box = selector.NumberSelectorMode.BOX
    reg = er.async_get(hass)
    own = [e.entity_id for e in reg.entities.values() if e.platform == DOMAIN]
    return vol.Schema(
        {
            vol.Required("comfort"): section(
                vol.Schema(
                    {
                        vol.Required(CONF_COMFORT_BASE): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=16.0,
                                max=26.0,
                                step=0.5,
                                unit_of_measurement="°C",
                                mode=box,
                            )
                        ),
                        vol.Required(CONF_CATEGORY): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=["I", "II", "III"],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Required(
                            CONF_COMFORT_WEIGHT, default=DEFAULT_COMFORT_WEIGHT
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0,
                                max=100,
                                step=5,
                                mode=selector.NumberSelectorMode.SLIDER,
                            )
                        ),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("schedule"): section(
                vol.Schema(
                    {
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
                                mode=box,
                            )
                        ),
                        vol.Required(
                            CONF_OPTIMAL_START, default=True
                        ): selector.BooleanSelector(),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("heat_cool"): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_ADAPTIVE_COOL, default=DEFAULT_ADAPTIVE_COOL
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=["auto", "on", "off"],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                translation_key="adaptive_cool",
                            )
                        ),
                        vol.Optional(
                            CONF_COOL_MIN_OUTDOOR, default=DEFAULT_COOL_MIN_OUTDOOR_C
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=-30.0,
                                max=30.0,
                                step=0.5,
                                unit_of_measurement="°C",
                                mode=box,
                            )
                        ),
                        vol.Required(
                            CONF_COOL_LOCKOUT_ENABLED,
                            default=DEFAULT_COOL_LOCKOUT_ENABLED,
                        ): selector.BooleanSelector(),
                        vol.Optional(
                            CONF_HEAT_MAX_OUTDOOR, default=DEFAULT_HEAT_MAX_OUTDOOR_C
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=5.0,
                                max=45.0,
                                step=0.5,
                                unit_of_measurement="°C",
                                mode=box,
                            )
                        ),
                        vol.Required(
                            CONF_HEAT_LOCKOUT_ENABLED,
                            default=DEFAULT_HEAT_LOCKOUT_ENABLED,
                        ): selector.BooleanSelector(),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("presence"): section(
                vol.Schema(
                    {
                        vol.Optional(CONF_PRESENCE_HOME): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain=[
                                    "person",
                                    "device_tracker",
                                    "binary_sensor",
                                    "group",
                                ],
                                multiple=True,
                                exclude_entities=own,
                            )
                        ),
                        vol.Optional(CONF_OCCUPANCY_SENSOR): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="binary_sensor",
                                device_class=["occupancy", "motion", "presence"],
                                multiple=True,
                            )
                        ),
                        vol.Optional(
                            CONF_ABSENCE_AFTER_MIN, default=DEFAULT_ABSENCE_AFTER_MIN
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=5,
                                max=240,
                                step=5,
                                unit_of_measurement="min",
                                mode=box,
                            )
                        ),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("manual_override"): section(
                vol.Schema(
                    {
                        # ADR-0059 §6: how a manual setpoint/preset override ends —
                        # follow the next schedule change, auto-revert after a timer,
                        # or hold until cleared (poise.resume_schedule / Boost).
                        vol.Required(
                            CONF_OVERRIDE_POLICY, default=DEFAULT_OVERRIDE_POLICY
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=["schedule", "timer", "permanent"],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                translation_key="override_policy",
                            )
                        ),
                        vol.Required(
                            CONF_OVERRIDE_TIMER_H, default=DEFAULT_OVERRIDE_TIMER_H
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0.5,
                                max=24,
                                step=0.5,
                                unit_of_measurement="h",
                                mode=box,
                            )
                        ),
                        vol.Required(
                            CONF_OVERRIDE_MAX_H, default=DEFAULT_OVERRIDE_MAX_H
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=1,
                                max=24,
                                step=1,
                                unit_of_measurement="h",
                                mode=box,
                            )
                        ),
                        vol.Required(
                            CONF_OVERRIDE_END_ON_PRESENCE,
                            default=DEFAULT_OVERRIDE_END_ON_PRESENCE,
                        ): selector.BooleanSelector(),
                        vol.Required(
                            CONF_BOOST_DURATION_MIN,
                            default=DEFAULT_BOOST_DURATION_MIN,
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=15,
                                max=180,
                                step=5,
                                unit_of_measurement="min",
                                mode=box,
                            )
                        ),
                        # CONF_OVERRIDE_SUGGESTIONS (override learning) is latent —
                        # L2/v2 (ADR-0059). Kept in const.py but intentionally not
                        # surfaced here until the suggestion engine ships.
                    }
                ),
                {"collapsed": True},
            ),
            vol.Required("advanced"): section(
                vol.Schema(
                    {
                        # ADR-0051 §1: latent tuning now surfaced. cool_hard_cap is
                        # the ASR ceiling (lower = more cooling; raising > 26 opt-in);
                        # thermal_shock 0 = feature off.
                        vol.Optional(
                            CONF_COOL_HARD_CAP, default=DEFAULT_HARD_CAP_C
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=23.0,
                                max=30.0,
                                step=0.5,
                                unit_of_measurement="°C",
                                mode=box,
                            )
                        ),
                        vol.Optional(
                            CONF_THERMAL_SHOCK_DELTA, default=DEFAULT_SHOCK_DELTA_K
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0.0,
                                max=12.0,
                                step=0.5,
                                unit_of_measurement="K",
                                mode=box,
                            )
                        ),
                        vol.Required(
                            CONF_OPERATIVE_INPUT, default=False
                        ): selector.BooleanSelector(),
                        # ADR-0052 §1: actuator dynamics profile (auto-detected).
                        vol.Optional(
                            CONF_DYNAMICS, default=DEFAULT_DYNAMICS
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=_DYNAMICS_OPTIONS,
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                translation_key="actuator_dynamics",
                            )
                        ),
                        # ADR-0046 §8: single-AC compressor guard. Blank timers fall
                        # back to the dynamics-profile default (fast_air 300 s).
                        vol.Optional(
                            CONF_COMPRESSOR_GUARD, default=COMPRESSOR_GUARD_AUTO
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[COMPRESSOR_GUARD_AUTO, COMPRESSOR_GUARD_OFF],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                translation_key="compressor_guard",
                            )
                        ),
                        vol.Optional(CONF_COMPRESSOR_MIN_OFF): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0,
                                max=1200,
                                step=30,
                                unit_of_measurement="s",
                                mode=box,
                            )
                        ),
                        vol.Optional(
                            CONF_COMPRESSOR_MODE_HOLD
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0,
                                max=1200,
                                step=30,
                                unit_of_measurement="s",
                                mode=box,
                            )
                        ),
                        # ADR-0011: opt-in field-trace recorder (one JSONL/tick).
                        vol.Optional(
                            CONF_TRACE_RECORDING, default=False
                        ): selector.BooleanSelector(),
                    }
                ),
                {"collapsed": True},
            ),
            vol.Required("energy"): section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_ANNUAL_KWH, default=DEFAULT_ANNUAL_KWH
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0, max=100000, step=100, mode=box
                            )
                        ),
                        vol.Optional(
                            CONF_PRICE_EUR_KWH, default=DEFAULT_PRICE_EUR_KWH
                        ): selector.NumberSelector(
                            selector.NumberSelectorConfig(
                                min=0, max=2, step=0.01, mode=box
                            )
                        ),
                    }
                ),
                {"collapsed": True},
            ),
        }
    )


def _heat_cool_only(hass: HomeAssistant, actuator: str) -> bool:
    """P2-4: True when the actuator can only condition via ``heat_cool`` (dual
    target_temp_high/low) and offers no single-target ``heat`` or ``cool`` mode.

    Poise writes one ``temperature`` per actuator, so such a device rejects the
    call and can't be driven. If ``hvac_modes`` is missing (the actuator is
    unavailable at validation time) return False so the flow isn't blocked.
    """
    state = hass.states.get(actuator)
    modes = state.attributes.get("hvac_modes") if state is not None else None
    if not modes:
        return False
    mode_set = set(modes)
    return HVACMode.HEAT_COOL in mode_set and not (
        {HVACMode.HEAT, HVACMode.COOL} & mode_set
    )


def _validate_boiler_actions(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Reject a boiler on/off action that doesn't parse (F11).

    The on/off actions are free-text service specs; a typo would silently leave the
    hub shadow-only. An empty action is allowed (diagnostic-only); a non-empty action
    that ``parse_service_action`` can't parse fails the form so the mistake surfaces.
    """
    for key in (CONF_BOILER_ON_ACTION, CONF_BOILER_OFF_ACTION):
        spec = user_input.get(key)
        if spec and parse_service_action(spec) is None:
            return {"base": "invalid_boiler_action"}
    return {}


class PoiseConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[misc, call-arg]
    """Guided per-room config flow with reconfigure support."""

    # V2 (ADR-0007): async_migrate_entry splits data->options and normalizes the
    # window/presence/occupancy pickers (now multiple=True) to lists.
    # MINOR_VERSION 2 (ADR-0059 §7): migration pins pre-0.162 zones to the "timer"
    # override policy so their fixed-2 h manual hold is preserved verbatim.
    VERSION = 2
    MINOR_VERSION = 2
    # F5: hub-existence captured when the reconfigure form was RENDERED, reused on
    # submit so the anlagen section shown and the reconcile's structural flag can
    # never disagree. The class-level default also gives mypy the type at the
    # submit read site (it is otherwise only assigned in the render branch).
    _reconf_structural_rendered: bool = False

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        # F9: the system hub has no hot-tunable room options — its options flow
        # aborts immediately (the hub is edited via Reconfigure). Rooms get the
        # real tuning flow.
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM:
            return PoiseHubOptionsFlow()
        return PoiseOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # P1-2: Poise's control path is Celsius-only — reject imperial/°F Home
        # Assistant installs up front rather than silently mis-controlling.
        if self.hass.config.units is US_CUSTOMARY_UNITS:
            return self.async_abort(reason="imperial_not_supported")
        # AR-30: offer the singleton system hub only once at least one room entry
        # exists — a hub with no zones to aggregate has nothing to do, so a fresh
        # install starts with just "room" (system appears on a later add).
        has_room = any(
            e.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_SYSTEM
            for e in self._async_current_entries()
        )
        menu = ["room", "system"] if has_room else ["room"]
        return self.async_show_menu(step_id="user", menu_options=menu)

    async def async_step_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = flatten_sections(user_input, ("accuracy",))
            act = data[CONF_ACTUATOR]
            reg = er.async_get(self.hass)
            # P2-4: reject a heat_cool-only actuator (dual setpoint) — Poise writes
            # a single ``temperature`` and can't drive it.
            if _heat_cool_only(self.hass, act):
                errors[CONF_ACTUATOR] = "heat_cool_only"
            # (b) the room sensor must be free-standing — not the actuator's own
            # built-in sensor (same device), or the model learns the wrong room.
            te = reg.async_get(data[CONF_TEMP_SENSOR])
            ae = reg.async_get(act)
            if te and ae and te.device_id and te.device_id == ae.device_id:
                errors[CONF_TEMP_SENSOR] = "sensor_on_actuator"
            # (c) one entry per actuator; name the zone that already owns it.
            for other in self._async_current_entries():
                if other.unique_id == act:
                    return self.async_abort(
                        reason="actuator_in_use",
                        description_placeholders={"zone": other.title},
                    )
            if not errors:
                if not data.get(CONF_NAME):
                    state = self.hass.states.get(act)
                    data[CONF_NAME] = (state.name if state else None) or act
                await self.async_set_unique_id(act)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_NAME], data=data)
        return self.async_show_form(
            step_id="room", data_schema=_setup_schema(self.hass), errors=errors
        )

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # singleton hub entry (ADR-0038)
        await self.async_set_unique_id("poise_system")
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_boiler_actions(user_input)  # F11
            if not errors:
                return self.async_create_entry(
                    title="Poise System",
                    data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, **user_input},
                )
        return self.async_show_form(
            step_id="system", data_schema=_system_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # P1-2: same Celsius-only gate on reconfigure — an entry can't be
        # reconfigured into an imperial/°F system either.
        if self.hass.config.units is US_CUSTOMARY_UNITS:
            return self.async_abort(reason="imperial_not_supported")
        entry = self._get_reconfigure_entry()
        is_system = entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM
        errors: dict[str, str] = {}
        if is_system:
            if user_input is not None:
                errors = _validate_boiler_actions(user_input)  # F11
                if not errors:
                    # V7: full replace (not merge); keep the ENTRY_TYPE tag.
                    return self.async_update_reload_and_abort(
                        entry, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, **user_input}
                    )
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(
                    _system_schema(), entry.data
                ),
                errors=errors,
            )
        # Room reconfigure owns only structural + sensor + installation fields; tuning
        # stays in the options flow. reconcile_reconfigure carries any tuning still in
        # data over to options so shrinking the form never drops a setting.
        tuning = {f for fields in _OPTIONS_SECTIONS.values() for f in fields}
        if user_input is not None:
            flat = flatten_sections(user_input, _RECONFIGURE_SECTIONS)
            # 1.1/1.2: the actuator is a zone's unique_id — re-validate so a changed
            # actuator can't silently collide with another zone's entry.
            await self.async_set_unique_id(flat[CONF_ACTUATOR])
            for other in self._async_current_entries():
                if (
                    other.entry_id != entry.entry_id
                    and other.unique_id == self.unique_id
                ):
                    return self.async_abort(reason="already_configured")
            # F3: the room sensor must be free-standing — not the actuator's own
            # built-in sensor (same device), mirroring async_step_room, or the
            # model learns the wrong room.
            reg = er.async_get(self.hass)
            te = reg.async_get(flat[CONF_TEMP_SENSOR])
            ae = reg.async_get(flat[CONF_ACTUATOR])
            if te and ae and te.device_id and te.device_id == ae.device_id:
                errors[CONF_TEMP_SENSOR] = "sensor_on_actuator"
            # P2-4: reject a heat_cool-only actuator (dual setpoint) — mirrors
            # async_step_room; Poise writes a single ``temperature``.
            if _heat_cool_only(self.hass, flat[CONF_ACTUATOR]):
                errors[CONF_ACTUATOR] = "heat_cool_only"
            if not errors:
                # F5: reuse the hub-existence captured when the form was RENDERED so
                # a hub added/removed between render and submit can't flip which
                # fields the reconcile treats as rendered.
                hub_exists = self._reconf_structural_rendered
                # AR-09: signal that the anlagen section was rendered (a hub is
                # present) so a structural field the user CLEARED there is dropped,
                # not reanimated from old_data.
                new_data, new_options = reconcile_reconfigure(
                    flat,
                    entry.data,
                    entry.options,
                    tuning,
                    structural_section_rendered=hub_exists,
                )
                # AR-12: a reconfigure onto a DIFFERENT actuator must release the OLD
                # one — park it and hand its TRV sensor source back to internal, or
                # the old device stays frozen against Poise's external feed on reload.
                old_actuator = entry.data.get(CONF_ACTUATOR)
                if (
                    isinstance(old_actuator, str)
                    and old_actuator
                    and old_actuator != new_data.get(CONF_ACTUATOR)
                ):
                    await self._park_replaced_actuator(entry, old_actuator)
                return self.async_update_reload_and_abort(
                    entry, unique_id=self.unique_id, data=new_data, options=new_options
                )
        current = {**entry.data, **entry.options}
        suggested = nest_by_section(current, _RECONFIGURE_SECTIONS)
        # the structural fields live at the top level (not in a section), so carry
        # them into the suggested values or they'd show empty on reconfigure.
        for key in (CONF_NAME, CONF_TEMP_SENSOR, CONF_ACTUATOR):
            if key in current:
                suggested[key] = current[key]
        # F5: capture hub-existence at RENDER and reuse it on submit, so the anlagen
        # section shown and the reconcile's structural flag can never disagree.
        hub_exists = any(
            e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM
            for e in self.hass.config_entries.async_entries(DOMAIN)
        )
        self._reconf_structural_rendered = hub_exists
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _reconfigure_schema(self.hass, hub_exists), suggested
            ),
            errors=errors,
        )

    async def _park_replaced_actuator(self, entry: ConfigEntry, actuator: str) -> None:
        """AR-12: release a room's PREVIOUS actuator when a reconfigure repoints the
        zone to a different one — park it in a capability-appropriate end state and
        flip a TRV sensor source back to internal, so the old device does not keep
        regulating against Poise's now-frozen external feed after the reload.

        Mirrors the delete-time park (``_remove_room_entry``). The live, Store-owned
        climate_mode wins over the (now option-free) config copy.
        """
        from . import _execute_park, _restore_trv_internal
        from .control.lifecycle import resolve_park_command

        cfg = {**entry.data, **entry.options}
        coordinator = getattr(entry, "runtime_data", None)
        mode = getattr(coordinator, "climate_mode", None) or str(
            cfg.get(CONF_CLIMATE_MODE, "auto")
        )
        st = self.hass.states.get(actuator)
        modes = (
            [str(m) for m in (st.attributes.get("hvac_modes") or [])]
            if st is not None
            else []
        )
        device_min = st.attributes.get("min_temp") if st is not None else None
        setback = float(cfg.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)) - float(
            cfg.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA)
        )
        plan = resolve_park_command(
            is_valve=actuator.startswith("number."),
            hvac_modes=modes,
            heats_for_zone="heat" in modes and mode != "cool_only",
            setback_setpoint=setback,
            floor=FROST_FLOOR_C,
            device_min=float(device_min) if device_min is not None else None,
        )
        await _execute_park(self.hass, actuator, plan)
        await _restore_trv_internal(self.hass, actuator)


class PoiseOptionsFlow(OptionsFlow):  # type: ignore[misc]
    """Edit volatile tuning in place — no reload, so learning is preserved (A10)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # Sections nest the submit one level; store it flat (config_sections)
            # so the coordinator/merge/reconfigure paths stay unchanged.
            flat = flatten_sections(user_input, _OPTIONS_SECTIONS)
            # (a) comfort window: both bounds or neither (one alone is ambiguous).
            if bool(flat.get(CONF_COMFORT_START)) != bool(flat.get(CONF_COMFORT_END)):
                errors["base"] = "comfort_window_pair"
            else:
                return self.async_create_entry(title="", data=flat)
            suggested = user_input
        else:
            # Pre-fill each section from the effective current config (data+options).
            current = {**self.config_entry.data, **self.config_entry.options}
            # legacy bool -> canonical mode so the tri-state dropdown pre-fills
            if CONF_ADAPTIVE_COOL in current:
                current[CONF_ADAPTIVE_COOL] = adaptive_cool_mode(
                    current[CONF_ADAPTIVE_COOL]
                )
            suggested = nest_by_section(current, _OPTIONS_SECTIONS)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(self.hass), suggested
            ),
            errors=errors,
        )


class PoiseHubOptionsFlow(OptionsFlow):  # type: ignore[misc]
    """The system hub has no hot-tunable options (F9).

    Its shared-plant settings are structural and are edited via Reconfigure, so the
    options flow aborts immediately rather than showing an empty form.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_abort(reason="hub_no_options")
