"""Persistence skeleton (ADR-0007).

Two independent version axes:
  * the config-entry ``VERSION`` (migrated by ``async_migrate_entry``), and
  * this learning-store ``STORAGE_VERSION`` with its own migrator,
plus per-unit embedded versions (e.g. ``ekf_version``) from Phase 2.

Bootstrap rule: everything is restored *before* the first control tick; the
coordinator gates on it (ADR-0007). Saves are debounced and flushed on stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}_learning"


class PoiseStore:
    """Thin wrapper around HA ``Store`` with schema-tolerant loading."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def load(self) -> dict[str, Any]:
        data = await self._store.async_load()
        if not isinstance(data, dict):  # corruption / first run -> start fresh
            return {}
        return data

    async def save(self, data: dict[str, Any]) -> None:
        await self._store.async_save(data)
