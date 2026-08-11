"""Phase 10 — fault injection into the finalize shadow segments (CI-only).

Refactoring plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md,
Befund 11a and Befunde 1–3; ADR-0062 (F-TPI / F-LIFECYCLE / F-PIACC).

Until phase 10 the whole chain — peak forecast → MPC → TPI → PI(+acc) →
lifecycle fold → thermal arbitration → ``shadow_objs`` — shared ONE ``try``,
so a failure in the EARLIEST step took the whole domain down for that tick:
``tpi_duty`` degraded to None (and ``heat_demand`` to the binary
``float(heating)`` fallback), the compressor-lifecycle fold was skipped and
``_pi.acc`` froze. These tests were the phase-0 pins of exactly that.

They are now the NEGATIVE tests of the three fixes: the same injected fault at
the same earliest step (``predict_peak_operative``) must leave

* ``tpi_duty``/``heat_demand`` intact — F-TPI,
* the lifecycle fold running (a NEW object every tick) — F-LIFECYCLE,
* ``_pi.acc`` advancing — F-PIACC,

while only the failing segment's own keys degrade (the cover shadow's) and the
tick itself stays successful. The MPC/arbitration segments are unaffected too;
what remains coupled is one real DATA dependency: the arbitration consumes the
folded lifecycle runtime, so it degrades when the FOLD fails — never when a
diagnostic before it does.
"""

from __future__ import annotations

import time
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

# the earliest shadow step (the cover segment's peak forecast); patched in the
# coordinator's namespace so ONLY the coordinator's call site raises.
_INJECT_AT = "custom_components.poise.coordinator.predict_peak_operative"
# the cover segment's own log line — the ONE segment the injection degrades
_COVER_FAILED = "shadow evaluation failed (cover)"


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
            "target_temp_step": 0.5,
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
    # Seed the fake clock CONTINUOUS with the real monotonic clock: the setup
    # tick anchored the EKF learn anchor (_last_mono) with the real clock, so
    # a fixed literal seed makes the next tick's learn dt depend on the host's
    # monotonic base (uptime). On a long-running host that dt is negative
    # (learn skipped, EKF stays identified); on a freshly booted CI runner it
    # is hundreds of seconds, the covariance predict step inflates and the
    # EKF DE-IDENTIFIES mid-tick. Continuity makes dt a deterministic ~60 s
    # per _tick on every platform.
    coord.runtime.clock = _FakeClock(time.monotonic())
    _make_identified(coord.runtime.learning.ekf)
    return coord


async def _tick(hass: HomeAssistant, coord: Any) -> dict[str, Any]:
    coord.runtime.clock.t += 60.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    return coord.data or {}


async def test_f_tpi_duty_and_heat_demand_survive_a_cover_fault(
    hass: HomeAssistant, caplog: Any
) -> None:
    """F-TPI: a failure in the EARLIEST shadow step (the cover segment's peak
    forecast) must no longer touch ``tpi_duty`` — and therefore no longer drop
    ``heat_demand`` to the binary ``float(heating)`` fallback. Only the cover
    segment degrades, and it says so on its own log line."""
    coord = await _setup(hass)
    # give the zone a writable valve so the TPI shadow is active and the
    # reference tick carries a real duty (evaluate_tpi_shadow gates on it;
    # only the shadow block + diagnostics read _valve_entity).
    coord.input_reader.valve_entity = "number.trv_valve_opening_degree"

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

    # the tick did not fail — control reporting stays online ...
    assert d["available"] is True
    # ... and the TPI segment kept its own boundary (F-TPI)
    assert d["tpi_active"] is True
    assert isinstance(d["tpi_duty"], float)
    assert d["tpi_duty"] == ref["tpi_duty"]
    # the segments after the failing one are untouched as well
    assert d["mpc_active"] is ref["mpc_active"]
    assert d["multi_reason"] == ref["multi_reason"]
    # heat_demand stays tied to the live duty instead of falling back to the
    # binary heating signal. (Value-wise the two coincide in this fixture — the
    # 18.5 °C room against a ~21 °C setpoint drives full duty — so the proof is
    # the pair above: the fallback path publishes tpi_active False/duty None.)
    assert d["heating"] is True
    assert d["heat_demand"] == d["tpi_duty"]
    # exactly ONE segment reported a failure, and it names itself
    assert _COVER_FAILED in caplog.text
    assert caplog.text.count("shadow evaluation failed") == 1

    # next healthy tick is indistinguishable (degradation is strictly per-tick)
    rec = await _tick(hass, coord)
    assert isinstance(rec["tpi_duty"], float)
    assert rec["multi_reason"] != "shadow_error"


async def test_f_lifecycle_fold_runs_through_a_cover_fault(
    hass: HomeAssistant,
) -> None:
    """F-LIFECYCLE: the compressor-lifecycle fold is LIVE state — it feeds the
    next tick's compressor guard — and must run on every tick regardless of a
    diagnostic shadow failing before it. ``multi_lifecycle`` is a frozen
    dataclass replaced by a NEW object on every successful fold, so object
    identity is the observable."""
    coord = await _setup(hass)

    life_before = coord.runtime.compressor.multi_lifecycle
    await _tick(hass, coord)
    life_ref = coord.runtime.compressor.multi_lifecycle
    # non-vacuousness: a healthy fold always builds a NEW DeviceLifecycle
    assert life_ref is not life_before

    with patch(_INJECT_AT, side_effect=RuntimeError("injected shadow fault")):
        d = await _tick(hass, coord)

    assert d["available"] is True
    # the fold ran anyway — a fresh object, not the pre-fault one
    assert coord.runtime.compressor.multi_lifecycle is not life_ref
    life_after = coord.runtime.compressor.multi_lifecycle
    assert d["multi_device_health"] == life_after.health
    # and with the fold, its two exclusive keys stay published
    assert "compressor_gate_would_block" in d
    assert "compressor_mode_hold_remaining" in d

    # the next healthy tick keeps folding
    await _tick(hass, coord)
    assert coord.runtime.compressor.multi_lifecycle is not life_after


async def test_f_piacc_integrator_advances_through_a_cover_fault(
    hass: HomeAssistant,
) -> None:
    """F-PIACC: the PI integrator advance is the PI segment's own side effect
    and no longer hangs off an unrelated shadow's boundary. No valve entity
    here, so the PI shadow applies and the room error (18.5 °C vs. the ~21 °C
    heat setpoint) accrues on every tick — including the faulted one."""
    coord = await _setup(hass)
    assert (
        coord.input_reader.valve_entity is None
    )  # setpoint-only device: PI shadow applies

    acc_setup = coord.runtime.learning.pi.acc
    await _tick(hass, coord)
    acc_ref = coord.runtime.learning.pi.acc
    # non-vacuousness: a healthy tick DOES advance the integrator
    assert acc_ref != acc_setup

    with patch(_INJECT_AT, side_effect=RuntimeError("injected shadow fault")):
        d = await _tick(hass, coord)

    assert d["available"] is True
    assert coord.runtime.learning.pi.acc != acc_ref  # kept integrating
    assert d["pi_active"] is True  # the PI segment published its own keys

    # and it keeps going on the next healthy tick
    acc_faulted = coord.runtime.learning.pi.acc
    await _tick(hass, coord)
    assert coord.runtime.learning.pi.acc != acc_faulted


async def test_only_the_failing_segment_degrades(
    hass: HomeAssistant, caplog: Any
) -> None:
    """The complement of the three fixes: the cover segment's OWN keys are the
    only casualty. ``cover_shade_position``/``cover_shade_reason`` fall back to
    the neutral seed while every other shadow key matches a healthy tick."""
    coord = await _setup(hass)
    ref = await _tick(hass, coord)

    with patch(_INJECT_AT, side_effect=RuntimeError("injected shadow fault")):
        d = await _tick(hass, coord)

    assert d["available"] is True
    # the cover segment degraded to the neutral seed (0.0 / "")
    assert d["cover_shade_position"] == 0.0
    assert d["cover_would_shade"] is False
    assert d["cover_shade_reason"] == ""
    # non-vacuousness: the healthy tick produced a real shading reason
    assert ref["cover_shade_reason"] != ""
    # every OTHER shadow key survived
    for key in (
        "tpi_active",
        "tpi_duty",
        "mpc_active",
        "mpc_regime",
        "pi_active",
        "multi_reason",
        "multi_severity",
        "multi_device_health",
        "compressor_gate_would_block",
    ):
        assert key in d, f"{key} must survive an unrelated segment failure"
    assert _COVER_FAILED in caplog.text
