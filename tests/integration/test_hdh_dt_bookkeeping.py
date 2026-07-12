"""Review F9: the HDH savings estimate and the outcome-session heating-time
integral must accumulate REAL elapsed time, not a flat ``TICK_INTERVAL_S``
per tick.

Previously the coordinator fed ``dt_min=_tick_min`` (a hardcoded 1.0 minute)
into both ``self._hdh.observe(...)`` and ``observe_session(...)`` regardless
of how much wall/monotonic time had actually passed since the last tick --
exactly the bug the neighbouring ``_ca_dt``/``_ref_dt`` real-elapsed-dt
bookkeeping (a few lines below) was already built to avoid. An event-driven
refresh (state change, service call, or -- as here -- several immediate
``async_refresh()`` calls in a row) books < 60 s of real time but the old
code silently credited a full simulated minute of savings/heating time for
each one, over-crediting the monthly savings estimate on any zone that
refreshes faster than once a minute.
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
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)


def _data() -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_SETBACK_DELTA: 3.0,
    }


def _states(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "18.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("sensor.outdoor", "2.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 19.0,
            "current_temperature": 18.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def test_rapid_ticks_do_not_flatly_credit_a_minute_each(
    hass: HomeAssistant,
) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_data(), title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord: Any = entry.runtime_data

    # setup already ran the first tick (fallback: 1 real tick's worth). Three
    # more immediate refreshes follow with essentially no real time elapsed.
    for _ in range(3):
        await coord.async_refresh()
        await hass.async_block_till_done()

    # 4 ticks total. The old flat-tick bug would book ~4.0 eligible minutes
    # (1.0 per tick regardless of real elapsed time); real elapsed dt keeps
    # this well under 2.0 (first tick's 1-minute fallback + a few near-zero
    # real-time increments).
    assert coord._hdh.eligible_min < 2.0, (
        f"eligible_min={coord._hdh.eligible_min!r} looks like a flat "
        "1-minute-per-tick credit, not real elapsed time"
    )
