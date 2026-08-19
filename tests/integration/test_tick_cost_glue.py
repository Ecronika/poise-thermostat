"""S.4b: what one tick costs — measured, not timed (glue, CI-only).

A wall-clock benchmark on a shared CI runner measures the neighbours. What
actually makes a Poise tick expensive is countable and deterministic: how
often it asks Home Assistant for a state, and how often it writes to the
device. Both are pinned here against a documented number for one fixed zone.

A change to either number is a BEHAVIOUR change — the same rule the O-phase
position contracts follow. Fold a read away and the number drops; add a second
read of the actuator and it rises. Either way the diff says so out loud
instead of hiding in a 3 % drift of a timing chart.

Only reads made by ``ha/input_reader.py`` count: the entity platforms read
states too, and mixing those in would make the number depend on how many
sensors happen to update in the same event-loop turn. That the reader is the
tick chain's ONLY door to ``hass.states`` is the static half of this gate
(``tests/test_structure_ports.py``).

``TickBudget`` (50 ms, EWMA, maximum, over-budget counter) stays the field
instrument for wall-clock; it is a diagnostic, not a gate, and this test does
not try to replace it.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_HUMIDITY_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)

# The read budget of ONE steady-state tick for the zone below. Measured, then
# pinned, and the breakdown is part of the record because it is the point:
#
#     climate.trv      9    <- the actuator, NINE times
#     sensor.room_temp 3
#     sun.sun          1
#     sensor.outdoor   1
#     sensor.rh        1
#     sensor.trm       1
#
# The nine is a finding, not a target. ``phase_prepare`` documents ONE
# positioned actuator read whose State object every later attribute access
# shares - and that holds for the phase bodies. The other eight come from
# InputReader methods that each fetch the actuator again for their own
# question (capability, device_min, guard discovery, ...). Folding them onto
# one read per tick is a real, separate change with its own proof obligation;
# this gate exists so that change SHOWS UP as a number instead of being
# invisible. Until then the number stands as measured.
_EXPECTED_READS = 16
# Writes: a steady-state tick that has nothing new to say writes nothing. The
# first tick after setup does (it adopts the device), which is why this test
# measures the SECOND one.
_EXPECTED_WRITES = 0

_SENSORS = {
    "sensor.room_temp": ("21.5", {"device_class": "temperature"}),
    "sensor.rh": ("45", {"device_class": "humidity"}),
    "sensor.outdoor": ("12", {"device_class": "temperature"}),
    "sensor.trm": ("18", {"device_class": "temperature"}),
}


def _data() -> dict[str, Any]:
    return {
        CONF_NAME: "Zone",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_HUMIDITY_SENSOR: "sensor.rh",
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


async def test_one_steady_tick_stays_inside_its_read_and_write_budget(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    for eid, (state, attrs) in _SENSORS.items():
        hass.states.async_set(eid, state, attrs)
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 21.5,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_data(), title="Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Count ONLY what the reader asks for. The caller's module is the filter:
    # a proxy object around ``hass`` would have to survive being handed to HA
    # helpers that expect the real thing, and this does not.
    # ``StateMachine.get`` is read-only per instance, so the patch goes on
    # the class and monkeypatch takes it back off afterwards.
    reads = {"n": 0}
    real_get = type(hass.states).get

    def counting_get(self: Any, entity_id: str) -> Any:
        caller = sys._getframe(1).f_globals.get("__name__", "")
        if caller.endswith("ha.input_reader"):
            reads["n"] += 1
        return real_get(self, entity_id)

    monkeypatch.setattr(type(hass.states), "get", counting_get)

    writes_before = len(set_temp) + len(set_mode)
    reads["n"] = 0
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    measured_reads = reads["n"]
    measured_writes = len(set_temp) + len(set_mode) - writes_before

    assert measured_reads == _EXPECTED_READS, (
        f"one tick made {measured_reads} state reads, budget is "
        f"{_EXPECTED_READS}. That is a behaviour change: fewer means a read "
        f"was folded away (good - lower the number here and say so), more "
        f"means a new per-tick read crept in (1440 extra calls a day per "
        f"zone). Never adjust this number without naming the read."
    )
    assert measured_writes == _EXPECTED_WRITES, (
        f"a steady-state tick performed {measured_writes} device writes, "
        f"expected {_EXPECTED_WRITES}. Writes are the expensive half - a "
        f"tick that rewrites an unchanged setpoint is the write-storm "
        f"class of bug (ADR-0020)."
    )

    # Anti-vacuum: the counter is real and attributable, not a stuck zero.
    before = reads["n"]
    entry.runtime_data._input_reader.read("sensor.room_temp")
    assert reads["n"] == before + 1, (
        "the read counter did not move for a read made THROUGH the "
        "reader - the caller filter no longer matches and the budget "
        "above would be vacuously green."
    )
