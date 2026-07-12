"""Review F7 + F13: two bugs in ``async_bootstrap``'s override-lifecycle restore.

F7: a hold persisted before ADR-0059 (or one that otherwise lost its
``override_expires_at``) restores with ``_override_expires_at is None`` --
not because it is a legitimate "permanent" hold, but because the key was
simply never computed/saved. Left as ``None`` the hold silently runs forever
after a restart, instead of expiring on real elapsed time like a freshly-set
hold would (ADR-0059 §1/§4).

F13: ``override_policy`` is documented in ADR-0059 as "hot-apply-fähig" (a
live config-entry OPTION), already correctly read from options/data by
``_read_override_options`` in ``__init__`` -- but ``async_bootstrap`` used to
unconditionally overwrite it again from the persisted store, so a stale
on-disk value silently reverted a user's option-flow change on the very next
restart.

Both tests use an unload + direct store/options mutation + fresh setup
sequence (not a plain ``async_reload``): a reload's options-update listener
hot-applies and can re-persist the corrected value on its own, masking
exactly the bug under test. Unloading first detaches that listener (it is
wired via ``entry.async_on_unload``), so the post-unload store/option edits
are the only input the following fresh ``async_setup`` sees -- a clean stand-in
for "the persisted store predates today's options / today's ADR-0059 schema".
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
    CONF_NAME,
    CONF_OVERRIDE_POLICY,
    CONF_OVERRIDE_TIMER_H,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    OVERRIDE_POLICY_PERMANENT,
    OVERRIDE_POLICY_TIMER,
)


def _room_data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_SETBACK_DELTA: 3.0,
        **extra,
    }


def _states(hass: HomeAssistant, *, room: float = 19.0, sp: float = 15.0) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup_zone(
    hass: HomeAssistant, *, options: dict[str, Any] | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=_room_data(),
        options=options or {},
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_pre_adr0059_hold_recomputes_missing_expiry_on_restore(
    hass: HomeAssistant,
) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(
        hass,
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 4.0,
        },
    )
    coord = entry.runtime_data

    coord.set_override(23.5)
    # simulate a pre-ADR-0059 build: the hold + its set-time exist, but this
    # in-memory instance never computed an announced expiry at all -- the
    # unload below flushes exactly this (corrupted) state to the store.
    coord._override_expires_at = None

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    restored = entry.runtime_data
    assert restored is not coord
    assert restored._override == 23.5
    # F7: recomputed from the restored set-time/policy, not left at None
    # (which would mean "runs forever").
    assert restored._override_expires_at is not None


async def test_override_policy_option_change_survives_restart(
    hass: HomeAssistant,
) -> None:
    """F13: ``override_policy`` is a hot-apply option -- a stale persisted value
    must never revert a user's later option-flow change on the next restart."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(
        hass, options={CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER}
    )
    coord = entry.runtime_data
    coord.set_override(23.5)
    assert coord._override_policy == OVERRIDE_POLICY_TIMER

    # unload first: flushes the live ("timer") state to the store AND detaches
    # the options-update listener, so the option edit below cannot hot-apply
    # and re-persist "permanent" on its own (which would mask the bug).
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # the user changes the option (e.g. via the UI) while the entry -- and
    # thus Poise's own persisted store -- is not loaded.
    hass.config_entries.async_update_entry(
        entry, options={CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_PERMANENT}
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    restored = entry.runtime_data
    assert restored is not coord
    # F13: the live option wins, not the stale persisted value.
    assert restored._override_policy == OVERRIDE_POLICY_PERMANENT
