"""Review persistence glue: the periodic EKF save cadence + dirty-flag flush
(P2-6) and a reload restoring preset, climate_mode AND enabled together (P2-7).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

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
    EKF_SAVE_EVERY_TICKS,
)
from custom_components.poise.control.override import OverrideMode

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


def _states(hass: HomeAssistant, *, room: float = 19.0, sp: float = 18.0) -> None:
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


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_p2_6_periodic_save_cadence_and_dirty_flush(
    hass: HomeAssistant,
) -> None:
    """P2-6: exactly one periodic store.save per EKF_SAVE_EVERY_TICKS ticks, and
    setting the dirty flag forces a save on the very next tick."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    with patch.object(coord._store, "save", AsyncMock()) as saver:
        # start from a clean, non-dirty cadence so setup's own saves don't count.
        coord._save_counter = 0
        coord._dirty = False
        for _ in range(EKF_SAVE_EVERY_TICKS):
            await coord.async_refresh()
            await hass.async_block_till_done()
        assert saver.call_count == 1, (
            f"expected exactly one periodic save in {EKF_SAVE_EVERY_TICKS} ticks"
        )

        # a dirty flag (e.g. an override/enabled/mode change) saves next tick.
        coord._dirty = True
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert saver.call_count == 2, "the dirty flag must flush on the next tick"


async def test_p2_7_reload_restores_preset_mode_and_enabled(
    hass: HomeAssistant,
) -> None:
    """P2-7: a reload rebuilds the coordinator; preset, climate_mode AND enabled
    all survive together (existing tests only covered the override)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # change all three away from their defaults (each marks the store dirty).
    coord.set_preset(OverrideMode.ECO)
    coord.set_climate_mode("heat")
    coord.set_enabled(False)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    restored: Any = entry.runtime_data
    assert restored is not coord, "a genuine reload built a fresh coordinator"
    assert restored.preset is OverrideMode.ECO
    assert restored.climate_mode == "heat"
    assert restored.enabled is False
