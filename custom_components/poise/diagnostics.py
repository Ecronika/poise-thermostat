"""Config-entry diagnostics with redaction (ADR-0012/0022).

The assembly + redaction live in the HA-free ``diagnostics_data`` module so they
are unit-tested directly; this thin wrapper only pulls the runtime objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .diagnostics_data import build_diagnostics

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import PoiseCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: PoiseCoordinator = entry.runtime_data
    return build_diagnostics(entry.data, coordinator.data)
