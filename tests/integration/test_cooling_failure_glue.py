"""Cooling-failure glue (review C.8): detector wiring in the failure-detect
stage, the ``cooling_failure`` telemetry key and the repair issue.

The detection arithmetic (window, latch, demand) is pure-tested in
``tests/test_heating_failure.py``; here the window is planted through the
detector's public ``update`` API and one real tick evaluates it — pinning
the stage inputs (real ``hvac_action``, the tick's write target, the room)
and the emission position.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
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
    CONF_WINDOW_SENSOR,
    DOMAIN,
)


def _room_data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_WINDOW_SENSOR: "binary_sensor.window",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: True,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        **extra,
    }


def _states(hass: HomeAssistant, *, room: float, sp: float) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "off"],
            "hvac_action": "cooling",
            "temperature": sp,
            "current_temperature": room,
            "target_temp_step": 0.5,
            "min_temp": 16.0,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, *, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_cooling_failure_defaults_false_and_is_exported(
    hass: HomeAssistant,
) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=29.0, sp=26.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.data["cooling_failure"] is False


async def test_flat_room_under_cooling_demand_flags_failure_and_issue(
    hass: HomeAssistant,
) -> None:
    """A hot room commanded well below its temperature, device reporting
    ``cooling``, no drop over the window -> ``cooling_failure`` True + the
    ``cooling_failure`` repair issue. The window is planted via the public
    detector API one hour in the past; the real tick evaluates it."""
    from homeassistant.helpers import issue_registry as ir

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=29.0, sp=26.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    now_h = coord.runtime.clock.monotonic() / 3600.0
    # Plant a demand window that began an hour ago at the SAME room temp:
    # the next real tick evaluates "no drop over the window".
    coord.runtime.safety.cooling_failure.update(
        now_h=now_h - 1.0, room=29.0, setpoint=24.0, running=True
    )
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.data["cooling_failure"] is True
    reg = ir.async_get(hass)
    issue_id = f"cooling_failure_{coord._entry_id}"
    assert reg.async_get_issue(DOMAIN, issue_id) is not None
    # The latch feeds the NEXT tick's learn gate (beta_c protection).
    assert coord.runtime.safety.prev_cooling_failed is True


async def test_notify_cooling_failure_is_a_translated_repair_issue(
    hass: HomeAssistant,
) -> None:
    """Mirror of the heating-failure P2-8 pin for the cooling channel."""
    from homeassistant.helpers import issue_registry as ir

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=29.0, sp=26.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    reg = ir.async_get(hass)
    issue_id = f"cooling_failure_{coord._entry_id}"

    coord._notify_cooling_failure(True)
    assert reg.async_get_issue(DOMAIN, issue_id) is not None
    coord._notify_cooling_failure(False)
    assert reg.async_get_issue(DOMAIN, issue_id) is None
