"""Phase-6b S1 — live wiring of the ZoneRuntime state relocation (glue).

The pure gate (``tests/test_phase6b_state_move.py``) pins the proxy SHAPE by
AST; this module pins the live behaviour on a real coordinator:

* every relocated ``self._*`` name routes through its property proxy into
  the ``ZoneRuntime`` group (no shadowing instance attribute, reads and
  writes visible in BOTH directions);
* the ``coord._clock = FakeClock(...)`` test idiom still reaches EVERY
  clock reader — the runtime's clock reference, the coordinator's own
  property reads and the live ``_ReaderClock`` forwarders handed to the
  ``InputReader`` and the ``ForecastProvider`` (phase-4/5A contract);
* the adapter-owned attributes deliberately did NOT move (they stay real
  instance attributes, plan section 3 "HA-Adapter"/Health/Persistenz-Meta
  groups).

Exercising every getter+setter here also keeps the proxy block inside the
glue coverage gate (coordinator.py is measured by coverage_glue.ini).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.clock import ManualClock
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_NAME,
    CONF_TEMP_SENSOR,
    DOMAIN,
)
from tests.test_phase6b_state_move import GROUP_CLASSES, PROXY_MAP

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
}

# Adapter-owned state that must NOT have moved into the runtime (plan
# section 3: HA-Adapter, HealthReporterState, Persistenz-Meta, config
# attributes and the reader/executor/provider references).  ``_dirty`` is
# the documented S2 K1 exception: the moved pure bodies (commit/teardown/
# mark_actuated/observe) mutate it, so the flag lives on the runtime and
# ``coord._dirty`` became a property proxy — pinned separately below.
ADAPTER_OWNED = (
    "_lock",
    "_entry_id",
    "_data_snapshot",
    "_store",
    "_climate_entity_id",
    "_tick_budget",
    "_active_issues",
    "_save_failures",
    "_tick_failures",
    "_unavailable_logged",
    "_save_counter",
    "_input_reader",
    "_actuator_executor",
    "_forecast_provider",
    "_mpc_params",
    "_window_auto_cfg",
)


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
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
        domain=DOMAIN,
        unique_id="climate.trv",
        data=dict(ROOM_DATA),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_every_proxy_routes_into_the_zone_runtime(
    hass: HomeAssistant,
) -> None:
    """Get/set roundtrip through every proxy; nothing shadows in __dict__."""
    entry = await _setup(hass)
    coord = entry.runtime_data
    runtime = coord._zone_runtime
    for name, (group_attr, field) in PROXY_MAP.items():
        group = getattr(runtime, group_attr)
        # Read path: the proxy returns exactly the group field.
        value = getattr(coord, name)
        assert value is getattr(group, field), name
        # Write path: the proxy setter lands on the group field (write the
        # value back unchanged so the coordinator state is undisturbed).
        setattr(coord, name, value)
        assert getattr(group, field) is value, name
        # The property must actually route: a shadowing instance attribute
        # in ``__dict__`` would bypass the runtime silently.
        assert name not in vars(coord), f"{name} shadowed by an instance attr"


async def test_proxy_writes_are_bidirectionally_visible(
    hass: HomeAssistant,
) -> None:
    """A proxy write shows on the group; a group write shows on the proxy."""
    entry = await _setup(hass)
    coord = entry.runtime_data
    runtime = coord._zone_runtime
    coord._override = 21.5  # proxy -> group
    assert runtime.user.override == 21.5
    runtime.user.override = None  # group -> proxy
    assert coord._override is None
    coord._prev_heating_failed = True  # SafetyRuntime moved per option A
    assert runtime.safety.prev_heating_failed is True


async def test_clock_swap_reaches_every_reader(hass: HomeAssistant) -> None:
    """``coord._clock = fake`` must govern runtime, reader and provider."""
    entry = await _setup(hass)
    coord = entry.runtime_data
    fake = ManualClock(1234.5)
    coord._clock = fake
    # The property setter replaced the runtime's clock reference ...
    assert coord._zone_runtime.clock is fake
    # ... the coordinator's own reads follow ...
    assert coord._clock.monotonic() == 1234.5
    # ... and the live forwarders handed to the reader and the forecast
    # provider follow the SAME swap (phase-4/5A live-clock contract).
    assert coord._input_reader._clock.monotonic() == 1234.5
    assert coord._forecast_provider._clock.monotonic() == 1234.5
    fake.advance(10.0)
    assert coord._input_reader._clock.monotonic() == 1244.5
    assert coord._forecast_provider._clock.monotonic() == 1244.5


async def test_adapter_owned_attributes_did_not_move(
    hass: HomeAssistant,
) -> None:
    """The adapter groups stay REAL instance attributes on the coordinator."""
    entry = await _setup(hass)
    coord = entry.runtime_data
    for name in ADAPTER_OWNED:
        assert name in vars(coord), f"{name} should be a real instance attribute"
    # And the runtime carries exactly the eleven groups + clock + the K1
    # dirty flag (slots; phase 6b S2).
    assert set(GROUP_CLASSES) | {"clock", "dirty"} == set(
        type(coord._zone_runtime).__slots__
    )
    # K1 pin (S2): ``_dirty`` routes through its property proxy onto
    # ``ZoneRuntime.dirty`` — no shadowing instance attribute, both
    # directions visible, seeded False by the runtime.
    assert "_dirty" not in vars(coord)
    assert coord._dirty is False
    coord._dirty = True
    assert coord._zone_runtime.dirty is True
    coord._zone_runtime.dirty = False
    assert coord._dirty is False
