"""Pure diagnostics assembly + redaction (ADR-0012/0022, HA-free for tests).

Entity ids are not secrets, but we redact them so shared diagnostics do not leak
a user's naming / setup. Kept HA-free so the redaction is unit-tested directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "**REDACTED**"

REDACT_KEYS = frozenset(
    {
        "temp_sensor",
        "actuator",
        "trm_sensor",
        "outdoor_sensor",
        "humidity_sensor",
        "mrt_sensor",
        "window_sensor",
        "weather_entity",
        "irradiance_sensor",
        "trv_external_temp_input",
        # Presence/occupancy inputs (R2, 2026-07 competitor code audit): these carry
        # person./device_tracker./group ids and motion/occupancy binary_sensor ids.
        # Unredacted they are the ONE place Poise reproduced the RoomMind #… "person
        # ids in the dump" class the opinion survey criticises — ADR-0022 makes id
        # redaction mandatory. They reach the dump via the entry.options merge below.
        "presence_home",
        "occupancy_sensor",
        # system-entry config: action specs + power-sensor ids + group label
        # (review P4/1.3-1.4 — hygiene, not secrets, but should not leak setup)
        "boiler_on_action",
        "boiler_off_action",
        "max_power_sensor",
        "current_power_sensor",
        "compressor_group",
    }
)

# Entity-id-bearing keys that surface in the live coordinator_data attributes
# (the room name is deliberately kept — see module docstring).
COORDINATOR_REDACT_KEYS = frozenset({"tpi_valve_entity"})


def redact(data: Mapping[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    """Replace the values of ``keys`` with a redaction sentinel; copy the rest."""
    return {k: (REDACTED if k in keys else v) for k, v in data.items()}


def build_diagnostics(
    entry_data: Mapping[str, Any],
    coordinator_data: Mapping[str, Any] | None,
    redact_keys: frozenset[str] = REDACT_KEYS,
    coordinator_redact_keys: frozenset[str] = COORDINATOR_REDACT_KEYS,
    entry_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the diagnostics payload, redacting config + live entity ids.

    Config is ``entry.data`` merged with ``entry.options`` (options win), so the
    hot-applyable tuning the V2 migration moved out of ``data`` still shows up in
    the dump instead of silently vanishing (review F19, mirrors the migration).
    """
    config = {**dict(entry_data), **(dict(entry_options) if entry_options else {})}
    tick = dict(coordinator_data) if coordinator_data is not None else None
    # ADR-0059 §5: surface the persisted L1 override nudge log at the top level.
    # It carries only ts/direction/delta/phase/presence_level (no entity ids ->
    # no redaction); lift it out of the tick so it is not also dumped under data.
    override_stats = tick.pop("override_stats", []) if tick is not None else []
    return {
        "config": redact(config, redact_keys),
        "data": (redact(tick, coordinator_redact_keys) if tick is not None else None),
        "override_stats": override_stats,
    }
