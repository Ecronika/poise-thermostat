"""Per-room EKF persistence (ADR-0007).

A dedicated HA Store keyed per config entry holds the learned filter so the
building model survives restarts. Schema-tolerant load (corrupt -> fresh).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_VERSION: Final = 1


class PoiseStore:
    """Thin wrapper around HA Store for one room's learned state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._key = f"{DOMAIN}_{entry_id}_ekf"
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, self._key)

    async def load(self) -> dict[str, Any] | None:
        data = await self._store.async_load()
        return data if isinstance(data, dict) else None

    async def save(self, data: dict[str, Any]) -> None:
        await self._store.async_save(data)

    async def async_remove(self) -> None:
        """Delete the underlying store file (entry-removal cleanup, ADR-0007).

        Called from the config-entry remove path so a deleted room leaves no
        orphaned EKF state behind; a fresh entry reusing the id starts clean.
        HA's ``Store`` keeps its in-memory cache after ``async_remove``, so swap in
        a fresh ``Store`` — a subsequent ``load`` then re-reads the (now deleted)
        file and yields ``None`` instead of the stale cache.
        """
        await self._store.async_remove()
        self._store = Store(self._hass, STORAGE_VERSION, self._key)
