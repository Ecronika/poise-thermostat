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
    CONF_OVERRIDE_POLICY,
    CONF_PRESENCE_HOME,
    CONF_SOURCE_POLICY,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    ENTRY_TYPE_SYSTEM,
    OVERRIDE_POLICY_TIMER,
)

# Structural inputs stay in entry.data (need a reload; not hot-applyable).
STRUCTURAL_KEYS: frozenset[str] = frozenset(
    {
        CONF_ENTRY_TYPE,
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
    options value wins (it holds the newer, hot-tuned value) — except for the
    structural keys, which are data-owned (they need a reload and are never
    hot-tuned), so a stale options copy must not shadow them on the merge.
    """
    if data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM:
        return dict(data), dict(options)  # hub entry: untouched
    merged: dict[str, object] = {**data, **options}
    for key in STRUCTURAL_KEYS:  # structural is data-owned; options must not win
        if key in data:
            merged[key] = data[key]
    new_data = {k: v for k, v in merged.items() if k in STRUCTURAL_KEYS}
    new_options = {k: v for k, v in merged.items() if k not in STRUCTURAL_KEYS}
    for key in MULTI_ENTITY_KEYS:
        if key in new_data:
            new_data[key] = _as_list(new_data[key])
        if key in new_options:
            new_options[key] = _as_list(new_options[key])
    return new_data, new_options


def apply_override_policy_default(
    data: dict[str, object],
    options: dict[str, object],
    *,
    stored_minor_version: int,
) -> dict[str, object]:
    """ADR-0059 §7: pin a pre-0.162 room zone to the fixed-timer manual-hold policy.

    Zones stored below minor_version 2 predate the configurable override policy and
    kept a fixed 2 h manual hold, so set ``override_policy = timer`` to preserve that
    behaviour verbatim across the upgrade. A zone already carrying an explicit policy
    (in ``data`` or ``options``) is left untouched, and a freshly created zone
    (``stored_minor_version >= 2``) leaves the key unset so the coordinator falls back
    to ``schedule``. Returns the (possibly new) options mapping; never mutates input.
    """
    if stored_minor_version >= 2:
        return options
    if CONF_OVERRIDE_POLICY in data or CONF_OVERRIDE_POLICY in options:
        return options
    new_options = dict(options)
    new_options[CONF_OVERRIDE_POLICY] = OVERRIDE_POLICY_TIMER
    return new_options


def as_entity_list(value: object) -> list[str]:
    """Normalize a stored config value to a list of entity ids (coordinator side).

    A single id becomes a one-element list; a list/tuple is filtered to truthy
    strings; anything else (``None``/missing) becomes an empty list. Mirrors the
    V2 store shape so the coordinator reads window/presence/occupancy uniformly
    whether the entry was freshly created, migrated, or (defensively) still holds
    a bare string.
    """
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    return []
