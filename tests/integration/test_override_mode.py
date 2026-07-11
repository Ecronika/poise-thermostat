"""ADR-0059 control-loop fix: an ACTIVE manual override drives the hvac mode.

A cool-capable zone whose room sits inside the comfort dead-band (the
un-overridden decision is ``idle``) must, once a manual setpoint override BELOW
the room is set, be nudged into ``cool`` toward the manual value -- not left
idling in its last mode (the reversible-AC-stuck-in-heat bug). Symmetrically an
override ABOVE the room drives ``heat``. The written setpoint stays the (clamped)
override; only the commanded mode changes.

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
    CONF_OUTDOOR_SENSOR,
    CONF_OVERRIDE_POLICY,
    CONF_OVERRIDE_TIMER_H,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
    OVERRIDE_POLICY_TIMER,
)

# Room 22.5 sits inside the Cat II comfort band (heat_sp ~19, cool_sp >= 24) so
# the un-overridden decision is idle; outdoor 18 clears both outdoor lockouts
# (>= 16 to cool, <= 22 to heat) so the override direction is never gated out.
_ROOM = 22.5
_OUTDOOR = 18.0


def _data() -> dict[str, Any]:
    return {
        CONF_NAME: "Zone",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: True,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
    }


def _sensors(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(_ROOM), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "sensor.outdoor", str(_OUTDOOR), {"device_class": "temperature"}
    )
    hass.states.async_set("sensor.trm", "20", {"device_class": "temperature"})


def _reversible_ac(hass: HomeAssistant, *, state: str) -> None:
    """A reversible AC (heat+cool) currently sitting in ``state``."""
    hass.states.async_set(
        "climate.ac",
        state,
        {
            "hvac_modes": ["cool", "heat", "off"],
            "temperature": 24.0,
            "current_temperature": _ROOM,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_data(),
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 4.0,
        },
        title="Zone",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_override_below_band_drives_cool(hass: HomeAssistant) -> None:
    """Reversible AC in heat + room in the dead-band + override below the room ->
    the tick nudges it into cool and writes the override value (ADR-0059)."""
    _sensors(hass)
    _reversible_ac(hass, state="heat")  # the bug: stuck in heat, never cooling
    entry = await _setup(hass)

    # Re-arm the recorders AFTER setup (fresh, empty lists). Forwarding the CLIMATE
    # platform registers HA's real climate entity services, which shadow the
    # pre-setup mocks and reject the bare-state actuator ("Referenced entities
    # climate.ac are missing or not currently available"). Re-registering makes
    # THIS override tick's set_hvac_mode / set_temperature reach the recorder and
    # isolates it from the setup/idle-park tick.
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    entry.runtime_data.set_override(21.0)  # below the room -> should cool
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    cool = [c for c in set_mode if c.data.get("hvac_mode") == "cool"]
    heat = [c for c in set_mode if c.data.get("hvac_mode") == "heat"]
    assert cool, "an override below the room must drive a cool nudge"
    assert not heat, "must not stay/flip into heat while cooling toward the override"
    assert set_temp, "expected a setpoint write for the override"
    assert abs(set_temp[-1].data["temperature"] - 21.0) < 0.05


async def test_override_above_band_drives_heat(hass: HomeAssistant) -> None:
    """Symmetric: an override ABOVE the room drives heat (not the last cool mode),
    still writing the override value."""
    _sensors(hass)
    _reversible_ac(hass, state="cool")
    entry = await _setup(hass)

    # Re-arm the recorders AFTER setup so the post-setup override tick's calls are
    # captured, not swallowed by the real climate entity service (see the cool
    # test for the full rationale).
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    entry.runtime_data.set_override(23.5)  # above the room -> should heat
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    heat = [c for c in set_mode if c.data.get("hvac_mode") == "heat"]
    cool = [c for c in set_mode if c.data.get("hvac_mode") == "cool"]
    assert heat, "an override above the room must drive a heat nudge"
    assert not cool, "must not stay in cool while heating toward the override"
    assert set_temp, "expected a setpoint write for the override"
    assert abs(set_temp[-1].data["temperature"] - 23.5) < 0.05
