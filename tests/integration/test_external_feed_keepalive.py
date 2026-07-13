"""v0.167 Block 2 — P2-2 external-temperature feed keep-alive (glue, CI-only).

The coordinator feeds the real room temperature to a TRV's external-temperature
number input (ADR-0029). Previously it only re-pushed on a >=0.1 K change, so a
perfectly stable room let the value go stale — and some TRVs time out an external
input and silently fall back to their own sensor. P2-2 adds a monotonic keep-alive
(``EXTERNAL_FEED_KEEPALIVE_S``) so a stable feed is re-asserted periodically.

Drives a fake monotonic clock across the keep-alive interval to prove the re-push
fires on time but not before. CI-only: needs a modern HA runtime (see conftest).
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
    CONF_TRV_EXTERNAL_TEMP,
    DOMAIN,
    EXTERNAL_FEED_KEEPALIVE_S,
)

EXT = "number.trv_external_temperature"


class _FakeClock:
    """A monotonic clock whose value the test advances by hand."""

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


def _room_states(hass: HomeAssistant, *, room: float = 20.0) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    # a plausible external-temperature number (device_class temperature) so the
    # F2 validation keeps the configured feed.
    hass.states.async_set(EXT, "21", {"device_class": "temperature"})


async def _setup_feed_zone(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=_base(**{CONF_TRV_EXTERNAL_TEMP: EXT}),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _feed_writes(calls: list[Any]) -> list[Any]:
    return [c for c in calls if c.data.get("entity_id") == EXT]


async def test_feed_repushes_after_keepalive(hass: HomeAssistant) -> None:
    """A stable room is re-fed once the keep-alive interval elapses, but not before."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_states(hass, room=20.0)
    entry = await _setup_feed_zone(hass)
    coord = entry.runtime_data
    assert coord._trv_ext_temp == EXT  # feed kept by F2 validation

    # take over the clock and reset the feed bookkeeping so the interval math
    # starts from our fake t0 rather than the real monotonic value setup used.
    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_fed = None
    coord._last_fed_ts = 0.0
    # re-arm the recorder AFTER setup (the platform forward shadows a pre-setup mock)
    set_value = async_mock_service(hass, "number", "set_value")

    # t0: first tick establishes the feed (no prior value)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert len(_feed_writes(set_value)) == 1
    assert _feed_writes(set_value)[-1].data["value"] == 20.0

    # +100 s (< keep-alive), room unchanged -> no re-push
    clock.t = 1000.0 + 100.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert len(_feed_writes(set_value)) == 1

    # cross the keep-alive since the last push -> exactly one re-push
    clock.t = 1000.0 + EXTERNAL_FEED_KEEPALIVE_S + 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert len(_feed_writes(set_value)) == 2
    assert _feed_writes(set_value)[-1].data["value"] == 20.0


async def test_feed_pushes_immediately_on_change(hass: HomeAssistant) -> None:
    """A >=0.1 K move re-feeds on the same tick, regardless of the keep-alive timer."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_states(hass, room=20.0)
    entry = await _setup_feed_zone(hass)
    coord = entry.runtime_data

    clock = _FakeClock(5000.0)
    coord._clock = clock
    coord._last_fed = 20.0
    coord._last_fed_ts = 5000.0  # just fed -> keep-alive nowhere near due
    set_value = async_mock_service(hass, "number", "set_value")

    # room jumps; the feed must follow this tick even though no time has passed
    hass.states.async_set("sensor.room_temp", "21.5", {"device_class": "temperature"})
    await coord.async_refresh()
    await hass.async_block_till_done()
    writes = _feed_writes(set_value)
    assert len(writes) == 1
    assert writes[-1].data["value"] == 21.5
