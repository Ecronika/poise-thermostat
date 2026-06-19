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
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_ekf"
        )

    async def load(self) -> dict[str, Any] | None:
        data = await self._store.async_load()
        return data if isinstance(data, dict) else None

    async def save(self, data: dict[str, Any]) -> None:
        await self._store.async_save(data)
