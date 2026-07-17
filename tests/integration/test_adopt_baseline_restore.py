"""v0.174.0 — B5 (review v0.173.0-alpha §4.3): the adoption baseline survives a
restart, so the first device-side intervention after one is adopted instead of
classifying as ``no_baseline`` and being reverted by the next write (glue,
CI-only).

The pure reason-code matrix lives in ``test_adopt.py``; this pins the coordinator
wiring: what ``_save_payload`` persists, and that ``async_bootstrap`` restores it
in a way that is *safe* -- i.e. restoring ``prev_device_*`` alongside the command
so a device reporting a constant offset (or one that simply never moved while HA
was down) does NOT self-adopt a phantom hold on the very first tick (the F1/F2
regression class from the v0.171.0 RC review).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    SETPOINT_ADOPT_ECHO_WINDOW_S,
)
from custom_components.poise.storage import STORAGE_VERSION

ENTRY_ID = "b5restore"


def _base(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        **extra,
    }


def _set_trv(hass: HomeAssistant, *, setpoint: float, room: float = 20.0) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": setpoint,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


def _seed_store(hass_storage: dict[str, Any], **payload: Any) -> None:
    """Pre-seed the persisted payload the way a previous HA run left it."""
    hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}_{ENTRY_ID}_ekf",
        "data": {"enabled": True, **payload},
    }


async def _setup(hass: HomeAssistant, **extra: Any):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        entry_id=ENTRY_ID,
        data=_base(**extra),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_baseline_is_persisted(hass: HomeAssistant) -> None:
    """B5: the payload carries the command AND the device-reported values."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_trv(hass, setpoint=20.0)
    entry = await _setup(hass)
    coord = entry.runtime_data

    coord._last_written_sp = 20.0
    coord._prev_device_sp = 20.5
    coord._last_commanded_hvac = "heat"
    coord._prev_device_mode = "heat"

    payload = coord._save_payload()
    assert payload["last_written_sp"] == 20.0
    assert payload["prev_device_sp"] == 20.5
    assert payload["last_commanded_hvac"] == "heat"
    assert payload["prev_device_mode"] == "heat"


async def test_intervention_right_after_restart_is_adopted(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """B5 core: baseline restored -> a wheel turn is adopted on the very first
    tick after a restart, instead of classifying as ``no_baseline`` and being
    reverted.

    Asserted on the *outcome* (the hold), not on ``_last_written_sp``: setup runs
    a tick, and that tick legitimately re-stamps the baseline with whatever it
    ends up writing -- the restored 20.0 is an input to the tick, not a
    post-condition of it. The hold's value is not pinned either, because an
    adopted setpoint is norm-clamped to the comfort band on the way in.
    """
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    # previous run: Poise commanded 20.0 and the device reported 20.0 back
    _seed_store(hass_storage, last_written_sp=20.0, prev_device_sp=20.0)
    # ... and while HA was down (or right after start) the user set 23.0
    _set_trv(hass, setpoint=23.0)

    entry = await _setup(hass)
    coord = entry.runtime_data

    assert coord._override is not None
    assert coord._override_reason == "device_adopt_setpoint"


async def test_restored_baseline_does_not_phantom_adopt_offset_device(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """B5 safety: a device that reports a constant offset to our command (here
    +0.5, i.e. exactly what it reported before the restart too) must NOT be
    grabbed as a hold -- ``prev_device_sp`` is what makes this classify as
    ``stable_offset``. Without persisting it the same tick adopts 20.5 (F1/F2)."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    _seed_store(hass_storage, last_written_sp=20.0, prev_device_sp=20.5)
    _set_trv(hass, setpoint=20.5)  # unchanged since before the restart

    entry = await _setup(hass)
    coord = entry.runtime_data

    assert coord._override is None
    assert coord._override_reason is None


async def test_restore_stamps_an_expired_echo_window(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """B5: no echo can be in flight across a restart, so the restored stamp must
    read as long expired -- otherwise the post-restart change above would be
    eaten as ``echo_window`` instead of adopted. Asserted at bootstrap level (no
    tick), because a tick re-stamps the write time by design."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    _seed_store(hass_storage, last_written_sp=20.0, prev_device_sp=20.0)
    _set_trv(hass, setpoint=20.0)

    entry = await _setup(hass)
    coord = entry.runtime_data

    # Re-run just the restore on a clean slate: bootstrap reads the same store.
    coord._last_sp_write_ts = None
    coord._last_written_sp = None
    await coord.async_bootstrap()

    assert coord._last_written_sp == 20.0
    assert coord._last_sp_write_ts is not None
    age = coord._clock.monotonic() - coord._last_sp_write_ts
    assert age >= SETPOINT_ADOPT_ECHO_WINDOW_S


async def test_no_persisted_baseline_stays_conservative(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """B5 must not invent a baseline: a fresh install (nothing persisted) keeps
    the old, conservative ``no_baseline`` behaviour -- the device's 23.0 is not
    grabbed as a hold. Checked at bootstrap level too: no baseline, no stamp."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    _seed_store(hass_storage)  # no baseline keys at all
    _set_trv(hass, setpoint=23.0)

    entry = await _setup(hass)
    coord = entry.runtime_data

    assert coord._override is None

    coord._last_sp_write_ts = None
    coord._last_written_sp = None
    await coord.async_bootstrap()
    assert coord._last_written_sp is None
    assert coord._last_sp_write_ts is None
