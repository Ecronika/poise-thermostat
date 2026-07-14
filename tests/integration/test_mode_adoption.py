"""K2: a device-side hvac_mode change (the IR remote on a split AC) is adopted as a
manual mode-hold instead of being nudged straight back (glue, CI-only). The pure
detection is in ``test_adopt_mode.py``; this pins the coordinator wiring: adopt ->
_mode_override + pinned desired (no re-nudge), off -> disabled/frost-rescue route,
with the opt-out and the Context echo-check honoured."""

from __future__ import annotations

from typing import Any

from homeassistant.core import Context, HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_ADOPT_EXTERNAL_MODE,
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
        CONF_ACTUATOR: "climate.ac",
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


def _set_ac(
    hass: HomeAssistant, *, mode: str, room: float = 20.0, context: Any = None
) -> None:
    """A heat+cool-capable split AC reporting ``mode`` as its state."""
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.ac",
        mode,
        {
            "hvac_modes": ["off", "heat", "cool", "dry", "fan_only"],
            "temperature": 21.0,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 30,
        },
        context=context,
    )


async def _setup(hass: HomeAssistant, **extra: Any):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=_base(**extra), title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_device_mode_change_is_adopted_as_hold(hass: HomeAssistant) -> None:
    """The user switches the AC from heat to fan_only via the remote -> adopted as a
    mode-hold, and Poise does not nudge it back to its computed mode."""
    nudges = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    _set_ac(hass, mode="heat")
    entry = await _setup(hass)
    coord = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_commanded_hvac = "heat"  # Poise last commanded heat ...
    coord._last_hvac_cmd_ts = 1000.0
    coord._prev_device_mode = "heat"
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0  # past the mode echo window
    _set_ac(hass, mode="fan_only")  # ... the user turned it to fan_only
    nudges.clear()

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._mode_override == "fan_only"  # adopted
    ac_nudges = [c for c in nudges if c.data.get("entity_id") == "climate.ac"]
    assert ac_nudges == []  # not nudged back


async def test_user_off_is_held_and_not_restarted(hass: HomeAssistant) -> None:
    """The user switches the AC off via the remote -> held ``off``; Poise does not
    re-nudge it on (subsumes the compressor-restart concern of C5) -- an off zone is
    routed through the disabled/frost-rescue branch, where frost + mould stay active."""
    nudges = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    _set_ac(hass, mode="cool", room=25.0)  # was cooling
    entry = await _setup(hass)
    coord = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_commanded_hvac = "cool"
    coord._last_hvac_cmd_ts = 1000.0
    coord._prev_device_mode = "cool"
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0
    _set_ac(hass, mode="off", room=25.0)  # user turned it off
    nudges.clear()

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._mode_override == "off"

    # a second tick: still off, still not re-nudged on (routed to the disabled branch)
    clock.t += 60.0
    _set_ac(hass, mode="off", room=25.0)
    await coord.async_refresh()
    await hass.async_block_till_done()
    on_nudges = [
        c
        for c in nudges
        if c.data.get("entity_id") == "climate.ac"
        and c.data.get("hvac_mode") in ("cool", "heat", "dry", "fan_only")
    ]
    assert on_nudges == []  # never commanded back on while held off


async def test_opt_out_disables_mode_adoption(hass: HomeAssistant) -> None:
    """With ``adopt_external_mode=False`` a device-side mode change is not adopted."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    _set_ac(hass, mode="heat")
    entry = await _setup(hass, **{CONF_ADOPT_EXTERNAL_MODE: False})
    coord = entry.runtime_data
    assert coord._adopt_external_mode is False

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_commanded_hvac = "heat"
    coord._last_hvac_cmd_ts = 1000.0
    coord._prev_device_mode = "heat"
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0
    _set_ac(hass, mode="fan_only")

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._mode_override is None


async def test_own_mode_nudge_echo_is_not_adopted(hass: HomeAssistant) -> None:
    """A mode change carrying a Context Poise created (its own nudge echo, even under
    a device that applies it late) is never adopted as a user mode-hold (V2)."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    _set_ac(hass, mode="heat")
    entry = await _setup(hass)
    coord = entry.runtime_data

    clock = _FakeClock(1000.0)
    coord._clock = clock
    coord._last_commanded_hvac = "heat"
    coord._last_hvac_cmd_ts = 1000.0
    coord._prev_device_mode = "heat"
    clock.t = 1000.0 + SETPOINT_ADOPT_ECHO_WINDOW_S + 1.0
    own = Context()
    coord._own_write_ctx_ids.append(own.id)
    _set_ac(hass, mode="cool", context=own)  # our own nudge echo, not a user change

    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._mode_override is None
