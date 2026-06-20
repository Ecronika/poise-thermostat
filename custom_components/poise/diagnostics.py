"""Config-entry diagnostics with redaction (ADR-0012/0022)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import PoiseCoordinator

# Entity ids are not secrets, but redact them so shared diagnostics do not leak
# a user's naming / setup details.
_REDACT = {
    "temp_sensor",
    "actuator",
    "trm_sensor",
    "outdoor_sensor",
    "humidity_sensor",
    "mrt_sensor",
    "window_sensor",
    "weather_entity",
    "irradiance_sensor",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: PoiseCoordinator = entry.runtime_data
    return {
        "config": async_redact_data(dict(entry.data), _REDACT),
        "data": coordinator.data,
    }
