"""Config-entry store migration (ADR-0007): data->options split + multi-entity.

V1 wrote every configured field into ``entry.data``. V2 keeps only the
structural inputs (sensors / actuator / system wiring) in ``data`` and moves the
hot-applyable tuning to ``options``, so the reconfigure step (a full data
replace) can shrink to structural fields without silently dropping tuning that
still lived in ``data``. The multi-entity pickers (window / presence /
occupancy) also migrate from a single entity id to a one-element list.
"""

from __future__ import annotations

from .const import (
    CONF_ACTUATOR,
    CONF_COMPRESSOR_GROUP,
    CONF_CONTROLS_BOILER,
    CONF_DECLARED_POWER,
    CONF_ENTRY_TYPE,
    CONF_FLOW_TEMP,
    CONF_HUMIDITY_SENSOR,
    CONF_IRRADIANCE,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_OUTDOOR_SENSOR,
    CONF_PRESENCE_HOME,
    CONF_SOURCE_POLICY,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
)

# Structural inputs stay in entry.data (need a reload; not hot-applyable).
STRUCTURAL_KEYS: frozenset[str] = frozenset(
    {
        CONF_NAME,
        CONF_TEMP_SENSOR,
        CONF_ACTUATOR,
        CONF_OUTDOOR_SENSOR,
        CONF_HUMIDITY_SENSOR,
        CONF_WINDOW_SENSOR,
        CONF_WEATHER,
        CONF_TRM_SENSOR,
        CONF_MRT_SENSOR,
        CONF_IRRADIANCE,
        CONF_TRV_EXTERNAL_TEMP,
        CONF_CONTROLS_BOILER,
        CONF_COMPRESSOR_GROUP,
        CONF_DECLARED_POWER,
        CONF_FLOW_TEMP,
        CONF_SOURCE_POLICY,
    }
)

# Multi-entity pickers: a single entity id migrates to a one-element list.
MULTI_ENTITY_KEYS: frozenset[str] = frozenset(
    {CONF_WINDOW_SENSOR, CONF_PRESENCE_HOME, CONF_OCCUPANCY_SENSOR}
)


def _as_list(value: object) -> object:
    """A single entity id becomes a one-element list; a list passes through."""
    if isinstance(value, str):
        return [value] if value else []
    return value


def migrate_room_entry(
    data: dict[str, object], options: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Return the V2 ``(data, options)`` split for a room entry.

    System/hub entries pass through unchanged. On a key present in both, the
    options value wins (it holds the newer, hot-tuned value).
    """
    if data.get(CONF_ENTRY_TYPE) is not None:
        return dict(data), dict(options)  # hub entry: untouched
    merged: dict[str, object] = {**data, **options}
    new_data = {k: v for k, v in merged.items() if k in STRUCTURAL_KEYS}
    new_options = {k: v for k, v in merged.items() if k not in STRUCTURAL_KEYS}
    for key in MULTI_ENTITY_KEYS:
        if key in new_data:
            new_data[key] = _as_list(new_data[key])
        if key in new_options:
            new_options[key] = _as_list(new_options[key])
    return new_data, new_options
