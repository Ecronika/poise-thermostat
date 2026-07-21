"""Config-entry diagnostics with redaction (ADR-0012/0022).

The assembly + redaction live in the HA-free ``diagnostics_data`` module so they
are unit-tested directly; this thin wrapper only pulls the runtime objects.

Phase 8 (S1): moved verbatim from the former top-level ``diagnostics.py`` —
the ``diagnostics`` package shadows that module name, so the platform hook
lives here and is re-exported by the package ``__init__`` (which is what HA
imports as the ``diagnostics`` platform).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..diagnostics_data import build_diagnostics

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    # runtime_data is a PoiseCoordinator for a room entry and a
    # PoiseHubCoordinator for the system entry; both expose ``.data``, so keep
    # the binding duck-typed and let the hub entry's dump go through too (F19).
    coordinator: Any = entry.runtime_data
    return build_diagnostics(entry.data, coordinator.data, entry_options=entry.options)
