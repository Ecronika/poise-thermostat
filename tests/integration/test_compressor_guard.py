"""ADR-0046 §8 — single-AC compressor guard, wired LIVE into the write path.

Proves the coordinator evaluates the guard each tick against the real per-device
lifecycle and: (a) surfaces the block reason (``compressor_gate_would_block``),
(b) holds back the cool/dry mode nudge while min-off is active, and (c) the kill
switch (``compressor_guard = off``) removes the gate so the nudge is free to fire.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips the
whole directory at collection time.
"""

from __future__ import annotations

from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    COMPRESSOR_GUARD_OFF,
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)
from custom_components.poise.multi.lifecycle import DeviceLifecycle


def _data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "AC Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        **extra,
    }


def _hot_cool_ac(hass: HomeAssistant) -> None:
    """A cool-capable AC currently OFF in a hot room -> Poise wants to start cool."""
    hass.states.async_set("sensor.room_temp", "28.0", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "30.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.ac",
        "off",
        {
            "hvac_modes": ["heat", "cool", "off"],
            "temperature": 24.0,
            "current_temperature": 28.0,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=data, title="AC Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _recently_stopped(coord: Any) -> None:
    """Seed the lifecycle as if the compressor stopped this instant -> min-off runs."""
    coord._multi_lifecycle = DeviceLifecycle(
        is_on=False, last_off_wall=dt_util.utcnow().timestamp()
    )


async def test_guard_holds_a_cool_start_within_min_off(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _hot_cool_ac(hass)
    coord = (await _setup(hass, _data())).runtime_data

    _recently_stopped(coord)
    await coord.async_refresh()
    await hass.async_block_till_done()

    d = coord.data
    # The guard is evaluated live against the seeded lifecycle: the verdict shows
    # the running min-off, and — because the hot room genuinely wants a cool start
    # (off -> cool) — that nudge is actually held. ``mode_nudge_blocked`` is set
    # ONLY when a real nudge was suppressed, so it is the live-suppression proof.
    assert str(d["compressor_gate_would_block"]).startswith("min-off")
    assert str(d["mode_nudge_blocked"]).startswith("min-off")


async def test_kill_switch_removes_the_gate(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _hot_cool_ac(hass)
    coord = (await _setup(hass, _data())).runtime_data

    coord._compressor_guard = COMPRESSOR_GUARD_OFF  # kill switch
    _recently_stopped(coord)
    await coord.async_refresh()
    await hass.async_block_till_done()

    d = coord.data
    # With the kill switch off there is no policy at all: no verdict is surfaced
    # and the same cool start is no longer suppressed (free to fire).
    assert d["compressor_gate_would_block"] == ""
    assert d["mode_nudge_blocked"] == ""
