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
    """HA Store wrapper for one room's persisted state (ADR-0007).

    The payload is built by ``PoiseCoordinator._save_payload`` and restored in
    ``async_bootstrap``; every key is optional-on-read (a missing key falls back
    to a default) so the schema can grow without a version bump. Besides the
    learned model (``ekf``/``trm``/``seasonless``/…) and the user intent
    (``enabled``/``preset``/``override``/``climate_mode``), it carries the
    ADR-0059 manual-hold + timed-Boost lifecycle on a wall-clock basis, so a hold
    survives a restart and still expires on real elapsed time (review C5):
    ``override_set_wall``/``override_requested``/``override_policy``/
    ``override_expires_at`` and ``boost_expires_at``/``boost_prev_preset``, plus
    the observe-only ``override_stats`` (§5 L1) and the hold's origin
    (``override_reason``, K3).

    B5 (v0.174.0): it also carries the *adoption baseline* --
    ``last_written_sp``/``last_commanded_hvac`` (what Poise last commanded) and
    ``prev_device_sp``/``prev_device_mode`` (what the device last reported back).
    Both halves are needed: without the command there is no baseline and the
    first device-side intervention after a restart is silently reverted; without
    the reported values a device with a constant offset would self-adopt a
    phantom hold on the first tick. The matching echo-window stamps are
    deliberately *not* persisted -- they are monotonic and process-local, and no
    echo can be in flight across a restart, so the restore stamps them as long
    expired instead.
    """

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


class PoiseHubStore:
    """Thin wrapper around HA Store for the singleton hub's boiler state (AR-08).

    Persists the tick-crossing ``BoilerState`` (on + wall-clock switch time) plus
    the ``has_actuated`` dead-man flag so a restart can rebuild the min-cycle dwell
    and the entry-removal path can tell whether Poise ever commanded the boiler.
    A single, entry-id-independent key (the hub is a singleton, ADR-0038/0039).
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._key = f"{DOMAIN}_system_hub"
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, self._key)

    async def load(self) -> dict[str, Any] | None:
        data = await self._store.async_load()
        return data if isinstance(data, dict) else None

    async def save(self, data: dict[str, Any]) -> None:
        await self._store.async_save(data)

    async def async_remove(self) -> None:
        """Delete the underlying store file (hub-removal cleanup).

        HA's ``Store`` keeps its in-memory cache after ``async_remove``, so swap in
        a fresh ``Store`` — a subsequent ``load`` then re-reads the (now deleted)
        file and yields ``None`` instead of the stale cache (mirrors
        :meth:`PoiseStore.async_remove`).
        """
        await self._store.async_remove()
        self._store = Store(self._hass, STORAGE_VERSION, self._key)
