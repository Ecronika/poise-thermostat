"""Schema/rendering layer of the Poise config flow (review 2026-08-19 P2).

Everything that DESCRIBES a form lives here — the selector helpers, the
voluptuous schema builders (`_setup_schema` / `_system_schema` /
`_reconfigure_schema` / `_options_schema`), the section maps that drive
flatten/nest (``config_sections``) and the pre-fill mapping. Flow control,
submit handling and validation stay in ``config_flow.py``; the split is a
plain module separation, deliberately NOT a builder/DSL abstraction.

Moved verbatim out of ``config_flow.py`` (which had grown to ~65 KB of
schemas + flows + validation + teardown); the import block is the shared
copy, trimmed per file.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .comfort.pmv import ROOM_PROFILES
from .comfort.thermal_shock import DEFAULT_HARD_CAP_C, DEFAULT_SHOCK_DELTA_K
from .const import (
    COMFORT_DAY_KEYS,
    COMFORT_WINDOWS_UI_MAX,
    COMPRESSOR_GUARD_AUTO,
    COMPRESSOR_GUARD_OFF,
    CONF_ABSENCE_AFTER_MIN,
    CONF_ACTIVE_COMFORT,
    CONF_ACTUATOR,
    CONF_ADAPTIVE_COOL,
    CONF_ADOPT_EXTERNAL_MODE,
    CONF_ADOPT_EXTERNAL_SETPOINT,
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
    CONF_COMFORT_BASE,
    CONF_COMFORT_DAYS,
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
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_OUTDOOR_SENSOR,
    CONF_OVERRIDE_END_ON_PRESENCE,
    CONF_OVERRIDE_MAX_H,
    CONF_OVERRIDE_POLICY,
    CONF_OVERRIDE_SUGGESTIONS,
    CONF_OVERRIDE_TIMER_H,
    CONF_PRESENCE_HOME,
    CONF_PRICE_EUR_KWH,
    CONF_ROOM_PROFILE,
    CONF_SETBACK_DELTA,
    CONF_SOURCE_POLICY,
    CONF_TEMP_SENSOR,
    CONF_THERMAL_SHOCK_DELTA,
    CONF_TRACE_RECORDING,
    CONF_TRM_SENSOR,
    CONF_TRV_CALIBRATION,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_VENT_NOTIFY,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    DEFAULT_ABSENCE_AFTER_MIN,
    DEFAULT_ACTIVE_COMFORT,
    DEFAULT_ADAPTIVE_COOL,
    DEFAULT_ADOPT_EXTERNAL_MODE,
    DEFAULT_ADOPT_EXTERNAL_SETPOINT,
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
    DEFAULT_OVERRIDE_SUGGESTIONS,
    DEFAULT_OVERRIDE_TIMER_H,
    DEFAULT_PRICE_EUR_KWH,
    DEFAULT_ROOM_PROFILE,
    DEFAULT_SETBACK_DELTA,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from .control.hub_aggregate import service_action_fields

_DYNAMICS_OPTIONS = ["auto", "fast_air", "slow_hydronic", "very_slow"]

# Services a boiler/heat generator is realistically switched with. Offered as a
# combobox WITH a free-text escape (``custom_value``) because HA has no "pick a
# service" selector at all: the selector registry knows ``entity``/``target``
# but no service type, and the one widget that does offer a service picker
# (``action``) yields a whole script SEQUENCE — a different execution model than
# the hub's single, blocking, timeout-bounded service call (see _boiler_action).
_BOILER_SERVICES = [
    "switch.turn_on",
    "switch.turn_off",
    "input_boolean.turn_on",
    "input_boolean.turn_off",
    "homeassistant.turn_on",
    "homeassistant.turn_off",
    "climate.set_hvac_mode",
    "water_heater.set_operation_mode",
    "valve.open_valve",
    "valve.close_valve",
    "script.turn_on",
    "button.press",
]

# Options-flow section groups (ADR-0008): the single source of truth for which
# tuning field lives in which collapsible section. Drives both the schema and the
# flatten (submit) / nest (display) of the sectioned values (config_sections).
_OPTIONS_SECTIONS: dict[str, tuple[str, ...]] = {
    "comfort": (
        CONF_COMFORT_BASE,
        CONF_CATEGORY,
        CONF_COMFORT_WEIGHT,
        CONF_ROOM_PROFILE,
        CONF_ACTIVE_COMFORT,
    ),
    # NOTE: the schedule section is extended dynamically with numbered extra
    # window pairs (ADR-0070 n+1 pattern) — use ``_options_sections(current)``
    # wherever the section map must match the rendered form.
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
        CONF_ADOPT_EXTERNAL_SETPOINT,
        CONF_ADOPT_EXTERNAL_MODE,
        CONF_BOOST_DURATION_MIN,
        CONF_OVERRIDE_SUGGESTIONS,  # ADR-0060 L2
    ),
    "advanced": (
        CONF_COOL_HARD_CAP,
        CONF_THERMAL_SHOCK_DELTA,
        CONF_OPERATIVE_INPUT,
        CONF_DYNAMICS,
        CONF_COMPRESSOR_GUARD,
        CONF_COMPRESSOR_MIN_OFF,
        CONF_COMPRESSOR_MODE_HOLD,
        CONF_TRV_CALIBRATION,
        CONF_TRACE_RECORDING,
        CONF_VENT_NOTIFY,
    ),
    "energy": (CONF_ANNUAL_KWH, CONF_PRICE_EUR_KWH),
}


def _extra_window_ns(current: Mapping[str, Any]) -> list[int]:
    """Indices N >= 2 of configured extra comfort windows (either bound set)."""
    ns = {
        int(m.group(2))
        for key, value in current.items()
        if value
        and (
            m := re.fullmatch(
                rf"({CONF_COMFORT_START}|{CONF_COMFORT_END})_(\d+)", str(key)
            )
        )
    }
    return sorted(n for n in ns if n >= 2)


def _schedule_window_fields(current: Mapping[str, Any]) -> tuple[str, ...]:
    """ADR-0070 n+1 pattern: the base pair, every CONFIGURED numbered pair,
    plus exactly ONE empty pair (next free index) up to the UI cap — the form
    never offers more than one unconfigured window at a time.

    P2.3: each triple additionally carries its ``comfort_days(_N)`` weekday
    selector, sibling of the start/end pair — ``_extra_window_ns`` (which
    this still drives the numbering off) stays START/END-only (F30): a
    day-only key must never conjure up a UI window on its own."""
    fields: list[str] = [CONF_COMFORT_START, CONF_COMFORT_END, CONF_COMFORT_DAYS]
    ns = _extra_window_ns(current)
    for n in ns:
        fields += [
            f"{CONF_COMFORT_START}_{n}",
            f"{CONF_COMFORT_END}_{n}",
            f"{CONF_COMFORT_DAYS}_{n}",
        ]
    nxt = (max(ns) + 1) if ns else 2
    if nxt <= COMFORT_WINDOWS_UI_MAX:
        fields += [
            f"{CONF_COMFORT_START}_{nxt}",
            f"{CONF_COMFORT_END}_{nxt}",
            f"{CONF_COMFORT_DAYS}_{nxt}",
        ]
    return tuple(fields)


def _options_sections(current: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """The section map matching the RENDERED options form (dynamic schedule)."""
    sections = dict(_OPTIONS_SECTIONS)
    sections["schedule"] = _schedule_window_fields(current) + (
        CONF_SETBACK_DELTA,
        CONF_OPTIMAL_START,
    )
    return sections


_RECONFIGURE_SECTIONS: dict[str, tuple[str, ...]] = {
    "sensors": (
        CONF_TRM_SENSOR,
        CONF_OUTDOOR_SENSOR,
        CONF_HUMIDITY_SENSOR,
        CONF_OUTDOOR_HUMIDITY_SENSOR,
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


def _window_selector(field: str) -> selector.Selector:
    """The per-field selector for one dynamic schedule-window field (P2.3).

    ``field == CONF_COMFORT_DAYS`` covers the base pair's weekday selector;
    ``field.startswith(CONF_COMFORT_DAYS + "_")`` covers every numbered
    ``comfort_days_N``. The explicit ``+ "_"`` guards against a hypothetical
    future field name merely sharing the ``comfort_days`` PREFIX (a bare
    ``.startswith(CONF_COMFORT_DAYS)`` would also match e.g. a
    ``comfort_days_of_week`` typo-key) — there is no such collision today,
    but the exact-or-numbered check costs nothing and stays correct if one is
    ever added. Every other window field (start/end, base or numbered) keeps
    the plain time selector.
    """
    if field == CONF_COMFORT_DAYS or field.startswith(f"{CONF_COMFORT_DAYS}_"):
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(COMFORT_DAY_KEYS),
                multiple=True,
                translation_key="comfort_days",
                mode=selector.SelectSelectorMode.LIST,
            )
        )
    return selector.TimeSelector()


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
                    # ADR-0066 B.3: outdoor-RH ladder stage 1 (dedicated
                    # sensor beats the weather entity's humidity attribute).
                    vol.Optional(CONF_OUTDOOR_HUMIDITY_SENSOR): selector.EntitySelector(
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
    inputs behind a collapsed section. Beyond comfort base + category, tuning
    has good defaults and is edited later in the options flow."""
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
                        # ADR-0066 B.3: outdoor-RH ladder stage 1.
                        vol.Optional(
                            CONF_OUTDOOR_HUMIDITY_SENSOR
                        ): selector.EntitySelector(
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


def _boiler_action() -> selector.ObjectSelector:
    """Structured field editor for one boiler action (entity + service + data).

    WHY THIS SELECTOR. The value is a single service call, and the hub executes
    it as one — one blocking, timeout-bounded dispatch of ``domain`` + ``service``
    + data, with the target entity id read back out of that data for the unload
    hand-over comparison (AR-01). Of the three HA-native candidates only this one
    matches that execution model:

    * ``ActionSelector`` renders the familiar automation action editor (the only
      HA widget with a real service picker) but its value is a SCRIPT SEQUENCE —
      steps, delays, conditions, templates. Running it needs the ``Script``
      helper, and "which entity does the OFF action target?" stops being a
      question a sequence can answer, which is exactly what the hand-over and
      removal safety paths ask. That is a hub change, not a form change.
    * A flat set of ``EntitySelector`` + ``SelectSelector`` keys renders inline
      and validates server-side, but it multiplies the two stored keys into six
      and forces every reader (hub coordinator, unload, removal, diagnostics
      redaction) onto a new key layout.
    * ``ObjectSelector`` with declared ``fields`` keeps ONE key per action and
      renders real sub-selectors (an entity picker among them), so the stored
      value stays a single self-contained action.

    How much the selector VALIDATES depends on the HA version: from 2026 it
    checks the declared fields (required present, each sub-selector applied,
    no unknown key), while on the supported minimum (2025.10) it hands the
    submitted value through untouched. ``_validate_boiler_actions`` therefore
    stays the load-bearing check — on the minimum it is the only one, and on
    2026 it still catches what a field selector cannot judge (a service that is
    not ``domain.service``; the combobox has a free-text escape by necessity).

    The entity picker is deliberately UNFILTERED: the free-text form it replaces
    accepted any domain, and a boiler is switched through a switch, an
    input_boolean, a climate entity, a valve, a script or a button depending on
    the plant. A domain filter would silently make existing setups unpickable.
    """
    fields: dict[str, Any] = {
        "entity_id": {"selector": {"entity": {}}, "required": True},
        "action": {
            "selector": {
                "select": {
                    "options": _BOILER_SERVICES,
                    "custom_value": True,
                    "mode": "dropdown",
                    "sort": False,
                }
            },
            "required": True,
        },
        "data": {"selector": {"object": {}}, "required": False},
    }
    return selector.ObjectSelector(
        selector.ObjectSelectorConfig(
            fields=fields,
            multiple=False,
            label_field="entity_id",
            description_field="action",
            translation_key="boiler_action",
        )
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
            vol.Optional(CONF_BOILER_ON_ACTION): _boiler_action(),
            vol.Optional(CONF_BOILER_OFF_ACTION): _boiler_action(),
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


def _options_schema(hass: HomeAssistant, current: Mapping[str, Any]) -> vol.Schema:
    """Volatile tuning, hot-applied without a reload (A10), grouped into
    collapsible sections (ADR-0008). Only fields the coordinator can update in
    place live here; structural inputs stay in the reconfigure step. The sectioned
    submit is flattened before storage (config_sections). The schedule section is
    built per-open from ``current`` (ADR-0070 n+1 window pattern)."""
    box = selector.NumberSelectorMode.BOX
    reg = er.async_get(hass)
    own = [e.entity_id for e in reg.entities.values() if e.platform == DOMAIN]
    window_fields: dict[Any, Any] = {
        vol.Optional(field): _window_selector(field)
        for field in _schedule_window_fields(current)
    }
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
                        # ADR-0054 V2: met/clo room profile for the PMV shadow.
                        vol.Optional(
                            CONF_ROOM_PROFILE, default=DEFAULT_ROOM_PROFILE
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=list(ROOM_PROFILES),
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                translation_key="room_profile",
                            )
                        ),
                        # ADR-0069: the "Aktive Behaglichkeit" mechanism
                        # toggle — permits the comfort actuation blocks; the
                        # ADR-0055-N1 tier gates release them piecewise.
                        vol.Optional(
                            CONF_ACTIVE_COMFORT, default=DEFAULT_ACTIVE_COMFORT
                        ): selector.BooleanSelector(),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("schedule"): section(
                vol.Schema(
                    {
                        **window_fields,
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
                        # P1-4a: adopt a device-side setpoint change (TRV wheel /
                        # vendor app) as a manual hold instead of overwriting it.
                        vol.Required(
                            CONF_ADOPT_EXTERNAL_SETPOINT,
                            default=DEFAULT_ADOPT_EXTERNAL_SETPOINT,
                        ): selector.BooleanSelector(),
                        # K2: adopt a device-side hvac_mode change (IR remote) as a
                        # manual mode-hold instead of nudging it straight back.
                        vol.Required(
                            CONF_ADOPT_EXTERNAL_MODE,
                            default=DEFAULT_ADOPT_EXTERNAL_MODE,
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
                        # ADR-0060 L2: suggestion emission, default ON since
                        # the §3 tuning round closed (2026-08-07) — the toggle
                        # is the opt-out; detection and diagnostics always run.
                        vol.Optional(
                            CONF_OVERRIDE_SUGGESTIONS,
                            default=DEFAULT_OVERRIDE_SUGGESTIONS,
                        ): selector.BooleanSelector(),
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
                        # ADR-0015 / P1.5 D1: opt-in TRV local-offset
                        # calibration (default OFF; tuning, hot-applied — no
                        # reconfigure field). An external-temperature input
                        # always takes precedence (D6).
                        vol.Optional(
                            CONF_TRV_CALIBRATION, default=False
                        ): selector.BooleanSelector(),
                        # ADR-0011: opt-in field-trace recorder (one JSONL/tick).
                        vol.Optional(
                            CONF_TRACE_RECORDING, default=False
                        ): selector.BooleanSelector(),
                        # ADR-0066 B.5: opt-in self-clearing ventilation-advice
                        # notification (the bus event always fires).
                        vol.Optional(
                            CONF_VENT_NOTIFY, default=False
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


def _system_suggested(data: Mapping[str, Any]) -> dict[str, Any]:
    """Hub reconfigure pre-fill: show every stored boiler action in FIELD form.

    An entry created before the structured editor stores the free-text spec; the
    object selector expects a mapping, so decompose it (losslessly — the same
    entity / ``domain.service`` / extra data) before it reaches the form. The
    submit then writes the structured form back, so a legacy entry normalizes on
    its first reconfigure without a store migration.

    A stored value that does not parse is dropped from the pre-fill: it is
    already inert (the hub stays shadow-only on it), and a field editor can only
    render it as an empty row, so that action is started from scratch instead.
    """
    suggested = dict(data)
    for key in (CONF_BOILER_ON_ACTION, CONF_BOILER_OFF_ACTION):
        if key not in suggested:
            continue
        fields = service_action_fields(suggested[key])
        if fields is None:
            del suggested[key]
        else:
            suggested[key] = fields
    return suggested
