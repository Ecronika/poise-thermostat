"""P2.3 (review P2.3b Important-2): an unrecognised ``comfort_days(_N)``
token must surface as a repair issue, and clear once the options are fixed.

Config-derived, not tick-derived: ``schedule_days_invalid_{entry_id}`` is
raised inside ``PoiseCoordinator._apply_hot_tuning`` — the single write path
shared by ``__init__`` (setup) and ``async_apply_options`` (options submit,
routed here through ``hass.config_entries.async_update_entry`` +
``_async_options_updated``, the single reload/hot-apply authority in
``__init__.py``) — mirroring the existing config-derived-issue precedent
(``external_temp_implausible``, also raised at setup) and the transition-only
``issue()``/``ir.async_get_issue`` pattern already exercised by
``test_tick_failing_issue.py``.
"""

from __future__ import annotations

from typing import Any

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
    CONF_COMFORT_DAYS,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
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


async def _setup(hass: HomeAssistant, options: dict[str, Any]) -> MockConfigEntry:
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
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_DATA,
        options=options,
        title="Test Room",
    )
    entry.add_to_hass(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_invalid_comfort_days_raises_issue_at_setup_and_clears_on_fix(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(
        hass,
        {
            CONF_COMFORT_START: "06:00:00",
            CONF_COMFORT_END: "22:00:00",
            CONF_COMFORT_DAYS: ["xyz"],
        },
    )
    issue_id = f"schedule_days_invalid_{entry.entry_id}"

    # Raised at setup (__init__ -> _apply_hot_tuning), not waiting for a tick.
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # A structural-unchanged options update routes through
    # _async_options_updated -> coordinator.async_apply_options ->
    # _apply_hot_tuning again, re-evaluating (and here clearing) the issue.
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_COMFORT_START: "06:00:00",
            CONF_COMFORT_END: "22:00:00",
            CONF_COMFORT_DAYS: ["mon", "tue"],
        },
    )
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_valid_comfort_days_never_raises_the_issue(
    hass: HomeAssistant,
) -> None:
    """Control: a clean setup (no comfort_days configured at all -> ALL_DAYS,
    unchanged legacy behaviour) never creates the issue in the first place."""
    entry = await _setup(
        hass, {CONF_COMFORT_START: "06:00:00", CONF_COMFORT_END: "22:00:00"}
    )
    issue_id = f"schedule_days_invalid_{entry.entry_id}"

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
