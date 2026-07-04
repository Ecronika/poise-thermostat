"""Silver test-coverage batch 4 (hub): the multi-zone hub coordinator glue.

Exercises the power-sensor reader, the compressor-group + load-shedding shadow,
the boiler actuation state machine (ON, OFF, and a failed service call keeping
the previous state), the zone-name lookup and the skip of a snapshot-less zone.

These drive the hub coordinator's methods directly with controlled monotonic
time — the deterministic way to reach the tick-crossing boiler state machine
(the pure ``step_*`` helpers are unit-tested separately, so the value here is the
HA glue around them: service dispatch, timeouts, and state reads).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips
the whole directory at collection time.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_BOILER_ACTIVATION_DELAY,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_CURRENT_POWER_SENSOR,
    CONF_ENTRY_TYPE,
    CONF_MAX_POWER_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from custom_components.poise.control.hub_aggregate import zone_request_from_data
from custom_components.poise.hub_coordinator import PoiseHubCoordinator

_ON = "switch.boiler/switch.turn_on"
_OFF = "switch.boiler/switch.turn_off"


async def _setup_hub(hass: HomeAssistant, **data_extra: Any) -> PoiseHubCoordinator:
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_COUNT_THRESHOLD: 1,
            **data_extra,
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()
    return hub.runtime_data


async def test_hub_power_reader_parses_sensor_states(hass: HomeAssistant) -> None:
    """``_power`` returns a float for a numeric sensor and None for a missing,
    unavailable or non-numeric one — a bad power reading never aborts the tick."""
    hub = await _setup_hub(hass)
    assert hub._power(None) is None
    assert hub._power("sensor.absent") is None
    hass.states.async_set("sensor.p", "unavailable")
    assert hub._power("sensor.p") is None
    hass.states.async_set("sensor.p", "1500.5")
    assert hub._power("sensor.p") == 1500.5
    hass.states.async_set("sensor.p", "not-a-number")
    assert hub._power("sensor.p") is None


async def test_hub_zone_name_resolves_entry_title(hass: HomeAssistant) -> None:
    """``_zone_name`` maps a zone entry_id to its title (frost-issue text),
    falling back to the id when the entry is gone."""
    zone = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.z1", data={}, title="Living Room"
    )
    zone.add_to_hass(hass)
    hub = await _setup_hub(hass)
    assert hub._zone_name(zone.entry_id) == "Living Room"
    assert hub._zone_name("does-not-exist") == "does-not-exist"


async def test_hub_actuates_boiler_on_then_off(hass: HomeAssistant) -> None:
    """With both actions configured the hub actuates: a demand switches the
    boiler on, and the demand clearing switches it off (min-cycle satisfied)."""
    turn_on = async_mock_service(hass, "switch", "turn_on")
    turn_off = async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.boiler", "off")
    hub = await _setup_hub(
        hass,
        **{
            CONF_BOILER_ON_ACTION: _ON,
            CONF_BOILER_OFF_ACTION: _OFF,
            CONF_BOILER_ACTIVATION_DELAY: 0,
        },
    )
    assert hub._actuation is True

    await hub._actuate(True, 1.0e9)  # reconcile + step -> ON call
    assert hub._boiler.on is True
    assert len(turn_on) >= 1

    await hub._actuate(False, 2.0e9)  # demand gone, min-on satisfied -> OFF call
    assert hub._boiler.on is False
    assert len(turn_off) >= 1


async def test_hub_failed_boiler_call_keeps_previous_state(hass: HomeAssistant) -> None:
    """A boiler service call that raises/times out counts as failure: the hub
    keeps the previous state (does not commit) so the next tick re-issues it."""

    async def _boom(call: ServiceCall) -> None:
        raise RuntimeError("boiler integration stuck")

    hass.services.async_register("switch", "turn_on", _boom)
    async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set("switch.boiler", "off")
    hub = await _setup_hub(
        hass,
        **{
            CONF_BOILER_ON_ACTION: _ON,
            CONF_BOILER_OFF_ACTION: _OFF,
            CONF_BOILER_ACTIVATION_DELAY: 0,
        },
    )
    await hub._actuate(True, 1.0e9)  # ON call raises -> _call False -> not committed
    assert hub._boiler.on is False


async def test_hub_shadow_computes_groups_and_shedding(hass: HomeAssistant) -> None:
    """The shared-resource shadow reads both power sensors (available head-room),
    resolves load shedding when overloaded, and runs the per-compressor-group
    min-cycle for a grouped, heating zone."""
    hub = await _setup_hub(
        hass,
        **{
            CONF_MAX_POWER_SENSOR: "sensor.maxp",
            CONF_CURRENT_POWER_SENSOR: "sensor.curp",
        },
    )
    hass.states.async_set("sensor.maxp", "3000")
    hass.states.async_set("sensor.curp", "3500")  # 500 W over budget
    req = zone_request_from_data(
        "zone.a",
        {
            "available": True,
            "heating": True,
            "current_temperature": 19.0,
            "heat_sp": 21.0,
        },
        controls_boiler=True,
        declared_power=1000.0,
        compressor_group="ac1",
        flow_temp_request=40.0,
        source_pref="heat_pump",
        mono_ts=1.0e9,
    )
    out = hub._shared_resource_shadow([req], 1.0e9)
    assert out["compressor_groups"].get("ac1") is True
    assert out["available_power"] == -500.0
    assert "shed_count" in out
    assert out["flow_target"] is not None


async def test_hub_collect_skips_snapshotless_zone(hass: HomeAssistant) -> None:
    """A zone entry present but not yet set up (no published snapshot) is skipped
    by ``_collect_requests`` rather than crashing the hub tick."""
    MockConfigEntry(
        domain=DOMAIN, unique_id="climate.z2", data={}, title="Z2"
    ).add_to_hass(hass)
    hub = await _setup_hub(hass)
    assert hub._collect_requests() == []
