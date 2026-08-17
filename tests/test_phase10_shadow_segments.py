"""Phase 10 — F-TPI/F-LIFECYCLE/F-PIACC: one boundary per shadow segment.

Refactoring plan ``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md``
Befunde 1-3/11a; ADR-0065 (Fehlergrenzen; bis 2026-07-26 als ADR-0062 nummeriert).

test_phase0_fault_shadow_domain injects into the FIRST segment (the cover
shadow) and proves the three fixes. This module walks the remaining segments
and pins the general property the split buys: whichever segment fails, only
ITS keys degrade and every other segment still publishes — including the one
real dependency (the thermal arbitration consumes the folded lifecycle
runtime, so a failing FOLD takes the arbitration with it, and nothing else
does).
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest
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
)
from custom_components.poise.estimation.thermal_ekf import ThermalEKF

# Patch where the name is BOUND, not where it is defined. Plan O.5 split the
# tick: the four shadow kernels are from-imported by the shadow phase module
# (a from-import binds at IMPORT time, so patching their defining modules would
# inject nothing), while ``build_tick_record`` belongs to the trace function
# and stayed with the sequencer.
_SHADOW = "custom_components.poise.ha.phase_shadow"
_ORCH = "custom_components.poise.ha.tick_orchestrator"

# Each segment's own published keys, and the log tag it reports under.
_MPC_KEYS = ("mpc_active", "mpc_power", "mpc_weight", "mpc_setpoint", "mpc_regime")
_TPI_KEYS = ("tpi_active", "tpi_duty", "tpi_valve_percent")
_PI_KEYS = ("pi_active", "pi_setpoint", "pi_offset")
_LIFECYCLE_KEYS = (
    "multi_min_off_remaining",
    "multi_device_health",
    "compressor_gate_would_block",
    "compressor_mode_hold_remaining",
)
_ARBITRATION_KEYS = (
    "multi_active_source",
    "multi_reason",
    "multi_severity",
    "multi_blocked",
)

_ROOM_DATA: dict[str, Any] = {
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


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _make_identified(ekf: ThermalEKF) -> None:
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.n_cooling = 1000
    ekf._n_uc = 1000
    ekf._n_qocc = 1000
    ekf.p[0][0] = 0.01
    assert ekf.identified


async def _setup(hass: HomeAssistant) -> Any:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "18.5", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 17.0,
            "current_temperature": 18.5,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    # continuity with the real-clock setup tick — see the sibling module
    coord.runtime.clock = _FakeClock(time.monotonic())
    _make_identified(coord.runtime.learning.ekf)
    # a writable valve makes the TPI segment active and the PI one inactive;
    # both still publish their keys either way
    coord.input_reader.valve_entity = "number.trv_valve_opening_degree"
    return coord


async def _tick(hass: HomeAssistant, coord: Any) -> dict[str, Any]:
    coord.runtime.clock.t += 60.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    return coord.data or {}


@pytest.mark.parametrize(
    ("target", "tag", "own_keys", "also_lost"),
    [
        (f"{_SHADOW}.evaluate_shadow", "mpc", _MPC_KEYS, ()),
        (f"{_SHADOW}.evaluate_tpi_shadow", "tpi", _TPI_KEYS, ()),
        (f"{_SHADOW}.evaluate_pi_shadow", "pi", _PI_KEYS, ()),
        (f"{_SHADOW}.evaluate_multi_shadow", "arbitration", _ARBITRATION_KEYS, ()),
        # the ONE real dependency: the arbitration consumes the folded runtime
        (
            "custom_components.poise.multi.lifecycle.observe",
            "lifecycle",
            _LIFECYCLE_KEYS,
            _ARBITRATION_KEYS,
        ),
    ],
)
async def test_only_the_failing_segment_degrades(
    hass: HomeAssistant,
    caplog: Any,
    target: str,
    tag: str,
    own_keys: tuple[str, ...],
    also_lost: tuple[str, ...],
) -> None:
    """Every segment owns its boundary: a failure costs its own keys (they fall
    back to the neutral seed, or vanish for the two ``compressor_gate_*`` the
    seed does not carry) and leaves every other segment intact."""
    coord = await _setup(hass)
    ref = await _tick(hass, coord)
    degraded = set(own_keys) | set(also_lost)
    survivors = [
        key
        for key in _MPC_KEYS
        + _TPI_KEYS
        + _PI_KEYS
        + _LIFECYCLE_KEYS
        + _ARBITRATION_KEYS
        if key not in degraded
    ]

    with patch(target, side_effect=RuntimeError(f"injected {tag} fault")):
        d = await _tick(hass, coord)

    # the tick survives and reports the failing segment by name, exactly once —
    # a skipped segment (the arbitration after a failed fold) does not log
    assert d["available"] is True
    assert f"shadow evaluation failed ({tag})" in caplog.text
    assert caplog.text.count("shadow evaluation failed") == 1

    # every OTHER segment published exactly what a healthy tick published
    for key in survivors:
        assert key in d, f"{key} must survive a {tag} failure"
        assert d[key] == ref[key], f"{key} changed on a {tag} failure"

    # the failing segment fell back: either to the neutral seed value or, for
    # the two compressor_gate_* keys, out of the payload entirely
    for key in degraded:
        if key in ("compressor_gate_would_block", "compressor_mode_hold_remaining"):
            assert key not in d
        else:
            assert key in d
    if tag == "lifecycle":
        assert d["multi_reason"] == "shadow_error"  # neutral seed
        assert ref["multi_reason"] != "shadow_error"


async def test_trace_flush_swallows_a_failing_recorder(hass: HomeAssistant) -> None:
    """ADR-0026 at the unload checkpoint: a flush failure is swallowed, so a
    broken trace file can never fail an unload."""
    coord = await _setup(hass)
    coord._trace_enabled = True
    await _tick(hass, coord)
    assert coord._tick._trace_recorder is not None

    with patch.object(
        type(coord._tick._trace_recorder),
        "flush_on_unload",
        side_effect=RuntimeError("boom"),
    ):
        await coord.async_persist_and_cleanup()  # must not raise


async def test_trace_capture_swallows_a_failing_build(hass: HomeAssistant) -> None:
    """Same contract on the tick side: a record-build failure is swallowed
    inside the boundary and the tick still publishes its payload."""
    coord = await _setup(hass)
    coord._trace_enabled = True

    with patch(f"{_ORCH}.build_tick_record", side_effect=RuntimeError("boom")):
        d = await _tick(hass, coord)

    assert d["available"] is True
