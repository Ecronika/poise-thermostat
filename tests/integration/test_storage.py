"""Storage glue: the entry-removal cleanup path (review F15).

``PoiseStore.async_remove`` deletes the underlying HA Store so a removed room
leaves no orphaned EKF state behind. CI-only (needs a real HA Store); the
sandbox HA skips this directory at collection time (see conftest).
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.poise.storage import PoiseStore


async def test_async_remove_deletes_persisted_state(hass: HomeAssistant) -> None:
    store = PoiseStore(hass, "entry-under-test")
    await store.save({"ekf_version": 1, "n_heating": 5})
    assert await store.load() == {"ekf_version": 1, "n_heating": 5}

    await store.async_remove()
    assert await store.load() is None  # cleanup left nothing behind
