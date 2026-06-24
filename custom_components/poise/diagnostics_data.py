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
) -> dict[str, Any]:
    """Assemble the diagnostics payload, redacting config + live entity ids."""
    return {
        "config": redact(dict(entry_data), redact_keys),
        "data": (
            redact(dict(coordinator_data), coordinator_redact_keys)
            if coordinator_data is not None
            else None
        ),
    }
