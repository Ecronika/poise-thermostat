"""Phase 0 — fault injection into the legacy SHADOW error domain (CI-only).

Refactoring plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md,
Befund 11a ("Legacy-Shadow-Domäne", try 3361–3497/3501) and Befunde 1–3.
These tests freeze TODAY's degradation semantics of the one shared ``try`` in
``coordinator.py`` around the diagnostics shadows:

* neutral shadow defaults 3342–3360 (``tpi_duty: None`` at 3353,
  ``multi_reason: "shadow_error"`` at 3347),
* peak forecast ``predict_peak_operative`` at 3363 — the EARLIEST shadow step,
* PI-integrator advance ``self._pi.acc = pi.next_acc`` at 3414–3415,
* compressor-lifecycle fold ``self._multi_lifecycle = _lifecycle.observe(...)``
  at 3443–3453,
* ``shadow_objs`` assembly 3468–3496 and the single broad ``except`` 3497–3501,
* downstream ``heat_demand`` via ``zone_heat_demand`` at 3811–3815, which falls
  back to the binary ``float(heating)`` whenever ``tpi_duty`` is None.

An injected failure in the earliest step therefore takes down the WHOLE domain
for that tick — ``tpi_duty`` degrades to None (and ``heat_demand`` to the
binary heating fallback), the lifecycle fold is skipped (the pre-tick object
survives by identity) and ``_pi.acc`` freezes — while the tick itself stays
successful and the next healthy tick fully recovers. In Phase 10 the fixes
F-TPI / F-LIFECYCLE / F-PIACC decouple these from diagnostics errors; these
tests then flip into their negative tests (degradation must STOP happening).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

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

# the earliest call inside the shared shadow try (coordinator.py:3363); patched
# in the coordinator's namespace so ONLY the coordinator's call site raises.
_INJECT_AT = "custom_components.poise.coordinator.predict_peak_operative"


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


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


def _room_and_actuator(hass: HomeAssistant, *, room: float = 18.5) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 17.0,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


def _make_identified(ekf: ThermalEKF) -> None:
    """Force the EKF past every maturity gate (pattern: test_identified_shadow)
    so the healthy reference tick runs the full predictive-shadow branch."""
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.n_cooling = 1000
    ekf._n_uc = 1000
    ekf._n_qocc = 1000
    ekf.p[0][0] = 0.01  # temperature_std = 0.1 K, well under the 0.5 K gate
    assert ekf.identified


async def _setup(hass: HomeAssistant) -> Any:
    """Set up an enabled zone, re-arm the service recorders AFTER setup, make
    the EKF identified and install a deterministic clock. Returns the coord."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_and_actuator(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data
    # re-arm after setup: platform forwarding re-registers the real climate
    # handlers, which would otherwise receive this test's tick writes.
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord._clock = _FakeClock(1000.0)
    _make_identified(coord._ekf)
    return coord


async def _tick(hass: HomeAssistant, coord: Any) -> dict[str, Any]:
    coord._clock.t += 60.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    return coord.data or {}


async def test_shadow_fault_degrades_tpi_duty_and_heat_demand(
    hass: HomeAssistant, caplog: Any
) -> None:
    """(a)+(d)+(e): a failure in the EARLIEST shadow step (peak forecast,
    coordinator.py:3363) degrades ``tpi_duty`` to the neutral None default
    (3353) — and with it ``heat_demand`` to the binary ``float(heating)``
    fallback (3811–3815 / zone_heat_demand) — while the tick itself succeeds.
    Phase 10 F-TPI flips this test: tpi_duty must then survive the fault."""
    coord = await _setup(hass)
    # give the zone a writable valve so the TPI shadow is active and the
    # reference tick carries a real duty (evaluate_tpi_shadow gates on it;
    # only the shadow block + diagnostics read _valve_entity).
    coord._valve_entity = "number.trv_valve_opening_degree"

    ref = await _tick(hass, coord)
    assert ref["available"] is True
    assert ref["identified"] is True
    assert ref["heating"] is True
    assert ref["tpi_active"] is True
    assert isinstance(ref["tpi_duty"], float)
    # R13 tie: the published heat_demand IS the live duty while it exists
    assert ref["heat_demand"] == ref["tpi_duty"]
    assert ref["multi_reason"] != "shadow_error"

    with patch(_INJECT_AT, side_effect=RuntimeError("injected shadow fault")):
        d = await _tick(hass, coord)

    # (d) the tick did not fail — control reporting stays online ...
    assert d["available"] is True
    # ... but the whole shadow domain degraded to its neutral defaults:
    assert d["tpi_duty"] is None  # (a) default at 3353
    assert d["tpi_active"] is False
    assert d["mpc_active"] is False  # MPC shadow shares the domain
    assert d["multi_reason"] == "shadow_error"
    assert "shadow evaluation failed" in caplog.text
    # (e) heat_demand falls back to binary heating (zone_heat_demand)
    assert d["heating"] is True
    assert d["heat_demand"] == 1.0

    # next healthy tick fully recovers (degradation is strictly per-tick)
    rec = await _tick(hass, coord)
    assert isinstance(rec["tpi_duty"], float)
    assert rec["multi_reason"] != "shadow_error"


async def test_shadow_fault_skips_lifecycle_fold(hass: HomeAssistant) -> None:
    """(b): the compressor-lifecycle fold (coordinator.py:3443–3453) sits in the
    SAME try as the shadows, so an earlier shadow fault skips ``observe()`` for
    that tick: ``coord._multi_lifecycle`` stays the IDENTICAL (frozen-dataclass)
    object, while every healthy tick replaces it with a new instance. Phase 10
    F-LIFECYCLE flips this: the fold must then always run."""
    coord = await _setup(hass)

    life_before = coord._multi_lifecycle
    await _tick(hass, coord)
    life_ref = coord._multi_lifecycle
    # non-vacuousness: a healthy fold always builds a NEW DeviceLifecycle
    assert life_ref is not life_before

    with patch(_INJECT_AT, side_effect=RuntimeError("injected shadow fault")):
        d = await _tick(hass, coord)

    assert d["available"] is True
    # the fold was skipped — the pre-fault object survives by identity
    assert coord._multi_lifecycle is life_ref
    # the published health diagnostic falls back to the pre-fault state too
    assert d["multi_device_health"] == life_ref.health

    # a healthy tick resumes folding
    await _tick(hass, coord)
    assert coord._multi_lifecycle is not life_ref


async def test_shadow_fault_freezes_pi_acc(hass: HomeAssistant) -> None:
    """(c): the persisted PI integrator only advances inside the shadow try
    (coordinator.py:3414–3415, via the pure ``evaluate_pi_shadow``); an earlier
    shadow fault silently freezes ``coord._pi.acc`` for that tick (plan
    Befund 3). No valve entity here, so the PI shadow applies and the room
    error (18.5 °C vs. the ~21 °C heat setpoint) accrues every healthy tick.
    Phase 10 F-PIACC flips this: the integrator must then keep advancing."""
    coord = await _setup(hass)
    assert coord._valve_entity is None  # setpoint-only device: PI shadow applies

    acc_setup = coord._pi.acc
    await _tick(hass, coord)
    acc_ref = coord._pi.acc
    # non-vacuousness: a healthy tick DOES advance the integrator
    assert acc_ref != acc_setup

    with patch(_INJECT_AT, side_effect=RuntimeError("injected shadow fault")):
        d = await _tick(hass, coord)

    assert d["available"] is True
    assert coord._pi.acc == acc_ref  # frozen, bit-exact
    assert d["pi_active"] is False  # PI shadow degraded to its neutral default

    # a healthy tick resumes integrating
    await _tick(hass, coord)
    assert coord._pi.acc != acc_ref
