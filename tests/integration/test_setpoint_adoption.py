"""v0.168 — P1-4a: a device-side setpoint change (TRV wheel / vendor app) is
adopted as a manual hold instead of being overwritten on the next tick (glue,
CI-only). The pure detection is in ``test_adopt.py``; this pins the coordinator
wiring: adopt -> set_override (norm-clamped) + skip this tick's overwrite, with
the echo window and the opt-out honoured."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_ADOPT_EXTERNAL_SETPOINT,
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


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


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


async def _setup(hass: HomeAssistant, **extra: Any):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_base(**extra), title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_device_side_change_is_adopted_as_hold(hass: HomeAssistant) -> None:
    """A wheel turn (device reports a setpoint Poise never wrote) becomes a hold,
    and Poise does not overwrite it back to the schedule this tick."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_trv(hass, setpoint=20.0)
    entry = await _setup(hass)
    coord = entry.runtime_data

    # establish Poise control, then jump past the echo window
    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_written_sp = 20.0
    coord._last_sp_write_ts = 1000.0
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0
    # the user turns the wheel to 23.0; re-arm the write recorder after setup
    _set_trv(hass, setpoint=23.0)
    setpoints = async_mock_service(hass, "climate", "set_temperature")

    await coord.async_refresh()
    await hass.async_block_till_done()

    # adopted as a hold (23.0 is inside the norm envelope, so kept verbatim);
    # ``_override`` is the source of truth (the value surfaces on the climate
    # entity's attributes, not in the coordinator's tick-data dict).
    assert coord._override == 23.0
    # ... and this tick did NOT push the schedule value back onto the device
    trv_writes = [c for c in setpoints if c.data.get("entity_id") == "climate.trv"]
    assert trv_writes == []


async def test_change_within_echo_window_is_not_adopted(hass: HomeAssistant) -> None:
    """A different reading right after Poise's own write is the device echoing/lag,
    not a user change -> no hold."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_trv(hass, setpoint=20.0)
    entry = await _setup(hass)
    coord = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_written_sp = 20.0
    coord._last_sp_write_ts = 1000.0
    clock.t = 1000.0 + 30.0  # still inside the echo window
    _set_trv(hass, setpoint=23.0)

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._override is None


async def test_adopted_hold_is_stable_across_ticks(hass: HomeAssistant) -> None:
    """Regression for the v0.168.0 B1 bug: once a device-side setpoint is adopted,
    the echo baseline is stamped so the *same* reading is not re-adopted every
    subsequent tick. Guards three symptoms of the missing stamp:

    * the announced expiry stays put between tick 1 and tick 2 (a re-adopt would
      recompute it from now() forever, so the hold could never end);
    * the L1 observation log does not grow tick over tick (store-save per tick);
    * after ``resume_schedule`` the hold stays cleared and is not re-adopted.
    """
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_trv(hass, setpoint=20.0)
    entry = await _setup(hass)
    coord = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_written_sp = 20.0
    coord._last_sp_write_ts = 1000.0
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0

    # tick 1 — the wheel turns to 23.0 and is adopted as a hold
    _set_trv(hass, setpoint=23.0)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._override == 23.0
    expiry_1 = coord._override_expires_at
    stats_1 = len(coord._override_stats)

    # tick 2 — the device still reports 23.0 (nothing changed). Without the
    # baseline stamp this re-adopts: expiry jumps and the log grows.
    clock.t += 300.0  # well past the echo window again
    _set_trv(hass, setpoint=23.0)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._override == 23.0
    assert coord._override_expires_at == expiry_1  # expiry unchanged
    assert len(coord._override_stats) == stats_1  # log did not grow

    # resume — clear the hold, then one more tick with the device still at 23.0
    coord.set_override(None, reason="user_resume")
    clock.t += 300.0
    _set_trv(hass, setpoint=23.0)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._override is None  # resume sticks; 23.0 is not re-adopted


async def test_opt_out_disables_adoption(hass: HomeAssistant) -> None:
    """With the feature off, a device-side change is not adopted (legacy overwrite)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_trv(hass, setpoint=20.0)
    entry = await _setup(hass, **{CONF_ADOPT_EXTERNAL_SETPOINT: False})
    coord = entry.runtime_data
    assert coord._adopt_external_setpoint is False

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_written_sp = 20.0
    coord._last_sp_write_ts = 1000.0
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0
    _set_trv(hass, setpoint=23.0)

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._override is None


async def test_stable_device_offset_is_not_re_adopted(hass: HomeAssistant) -> None:
    """Regression for the live 'ending a hold via the card X springs straight back
    to manual' bug: the device settled Poise's write at a fixed offset (its own
    re-quantise / min-max clamp) and reports that value UNCHANGED tick over tick.
    It must NOT be re-adopted once the echo window lapses -- only a value the device
    actually *moved* to (a fresh user action) is a genuine external change."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_trv(hass, setpoint=23.0)  # device is stuck at 23.0 (its settled value)
    entry = await _setup(hass)
    coord = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_written_sp = 20.0  # Poise commanded 20.0 ...
    coord._last_sp_write_ts = 1000.0
    coord._prev_device_sp = 23.0  # ... but the device settled at 23.0 and holds it
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0  # echo window has lapsed
    _set_trv(hass, setpoint=23.0)  # still 23.0 -- unchanged

    await coord.async_refresh()
    await hass.async_block_till_done()
    # stable offset (device_sp == prev_device_sp) -> not a fresh move -> no adoption
    assert coord._override is None
