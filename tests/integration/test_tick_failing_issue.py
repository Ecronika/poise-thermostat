"""Review F12: a tick that repeatedly raises out of ``_run_once`` must surface
a Poise-specific repair issue, not just DataUpdateCoordinator's generic
(silent-to-the-user) "update failed" log entry.

Mirrors the existing ``persistence_failed`` (F24) escalate-after-N-in-a-row
pattern: a single transient failure is not surfaced, but N consecutive ones
raise ``tick_failing_{entry_id}``, and a subsequent success clears it. The
underlying exception is still re-raised unchanged in every case -- this must
not change ``last_update_success``/entity-availability behaviour, only add a
diagnostic signal.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
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
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set(
        "sensor.room_temp",
        "18.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
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
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_repeated_tick_failures_raise_issue_and_clear_on_recovery(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data
    issue_id = f"tick_failing_{entry.entry_id}"

    async def _boom() -> dict[str, Any]:
        raise RuntimeError("simulated tick failure")

    with patch.object(coord, "_run_once", side_effect=_boom):
        for _ in range(2):
            # DataUpdateCoordinator.async_refresh swallows the exception into
            # last_update_success=False; it must still propagate through our
            # try/except (re-raised) rather than being silently absorbed.
            await coord.async_refresh()
            await hass.async_block_till_done()
        assert coord.last_update_success is False
        # 2 failures: below the N=3 escalation threshold.
        assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

        await coord.async_refresh()
        await hass.async_block_till_done()
        # 3rd consecutive failure: escalates.
        assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # the patch is lifted -- the next tick succeeds and clears the issue.
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
