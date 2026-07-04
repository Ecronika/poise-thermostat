"""Silver test-coverage (the last open Silver rule): drive a coordinator tick
with an *identified* EKF so the predictive-shadow branches — MPC, optimal-start,
cover-shading, outcome-scoring, CA metric and reference-offset, all gated behind
``if self._ekf.identified:`` and therefore never reached by a fresh test model —
actually execute. This is the highest-leverage coverage lift for coordinator.py.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips
the whole directory at collection time.
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
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)
from custom_components.poise.estimation.thermal_ekf import ThermalEKF


def _base(**extra: Any) -> dict[str, Any]:
    return {
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
        **extra,
    }


def _room_and_actuator(
    hass: HomeAssistant,
    *,
    room: float,
    sp: float,
    modes: list[str],
    state: str,
) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": modes,
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


def _make_identified(ekf: ThermalEKF) -> None:
    """Force the EKF past every maturity gate so the coordinator trusts the
    model and runs its predictive-shadow branches on the next tick.

    Gates (ADR-0024): ``n_idle >= 60`` and ``n_heating`` (or ``n_cooling``)
    ``>= 20`` and ``temperature_std < 0.5``. The private ``_n_uc`` / ``_n_qocc``
    counters additionally unlock ``cooling_identified`` / ``occupancy_identified``
    so the cooling-season shadow paths are exercised too.
    """
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.n_cooling = 1000
    ekf._n_uc = 1000
    ekf._n_qocc = 1000
    ekf.p[0][0] = 0.01  # temperature_std = 0.1 K, well under the 0.5 K gate
    assert ekf.identified


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_identified_model_runs_mpc_shadow(hass: HomeAssistant) -> None:
    """An identified model activates the MPC shadow and the confident
    cover-shading / outcome / CA / reference-offset diagnostics all run."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_and_actuator(hass, room=18.5, sp=17.0, modes=["heat", "off"], state="heat")
    entry = await _setup(hass, _base())
    coord = entry.runtime_data

    _make_identified(coord._ekf)
    await coord.async_refresh()
    await hass.async_block_till_done()

    d = coord.data
    assert d["available"] is True
    assert d["identified"] is True
    assert d["confidence"] > 0.5
    # the `if identified` predictive-shadow branch ran (dormant on a fresh model):
    assert d["mpc_active"] is True
    assert isinstance(d["mpc_setpoint"], float)
    # confident cover-shading peak + the outcome / CA / reference diagnostics:
    assert isinstance(d["cover_predicted_peak"], float)
    assert "outcome_last_score" in d
    assert "ca_deviation_k" in d
    assert "ref_offset" in d


async def test_identified_cooling_model_tick(hass: HomeAssistant) -> None:
    """A cool-capable, identified model runs the cooling-season shadow path
    (cool_drive_signal / cooling MPC) without error."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.outdoor", "29.0", {"device_class": "temperature"})
    _room_and_actuator(
        hass, room=27.0, sp=24.0, modes=["heat", "cool", "off"], state="cool"
    )
    entry = await _setup(hass, _base(**{CONF_OUTDOOR_SENSOR: "sensor.outdoor"}))
    coord = entry.runtime_data

    _make_identified(coord._ekf)
    await coord.async_refresh()
    await hass.async_block_till_done()

    d = coord.data
    assert d["available"] is True
    assert d["identified"] is True
    assert d["mpc_active"] is True
    assert isinstance(d["mpc_setpoint"], float)


async def test_identified_boiler_zone_calls_for_heat(hass: HomeAssistant) -> None:
    """A boiler-controlling, identified zone below comfort calls for heat —
    exercising the controls-boiler branch together with the identified path."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_and_actuator(hass, room=18.0, sp=16.0, modes=["heat", "off"], state="heat")
    entry = await _setup(hass, _base(**{CONF_CONTROLS_BOILER: True}))
    coord = entry.runtime_data

    _make_identified(coord._ekf)
    await coord.async_refresh()
    await hass.async_block_till_done()

    d = coord.data
    assert d["available"] is True
    assert d["identified"] is True
    # below comfort with a trusted model -> the heat setpoint sits above the room
    assert d["heat_sp"] > d["current_temperature"]
