"""Phase 0 — contract tests for BOTH forms of ``coordinator.data`` (Befund 4).

Pins the data contract named in
``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md`` (Phase 0,
"Contract-Tests für BEIDE Datenformen") against today's behaviour, BEFORE the
coordinator refactor may touch the payload assembly:

* Available form — built in ``_run_once`` at ``coordinator.py`` 3682–3808
  (``_tick_data``), with ``heat_demand`` appended at 3811 and the timing
  diagnostics ``tick_ms``/``tick_ms_ewma``/``tick_ms_max``/``tick_over_budget``
  attached ONLY to this form by the wrapper at 1842–1849. ``tpi_duty`` defaults
  to ``None`` at 3353 (shadow-error fallback) and is filled at 3489 — the KEY
  must always exist, the value may be ``None``.
* Unavailable form — the early return at 1996–2040: a fresh sensor loss yields
  EXACTLY ``{"available": False}`` (2040); once the loss exceeds
  ``UNAVAILABLE_SAFE_AFTER_S`` the safe state is written
  (``_write_unavailable_safe_state`` 1929–1986) and the payload is EXACTLY
  ``{"available": False, "unavailable_safe": True}`` (2039). No ``tick_ms*``
  keys on either unavailable payload — the entity availability gate relies on
  that pristine minimal contract.

The full-key snapshot (``EXPECTED_AVAILABLE_KEYS``) was generated once from the
Ist-Zustand of this fixed room config; any diff means a DELIBERATE API change
and must be reviewed as such, then re-frozen here.
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
    DOMAIN,
    UNAVAILABLE_SAFE_AFTER_S,
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: False,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}

# The hub-critical subset (system hub / boiler aggregation / entity gate).
HUB_CRITICAL_KEYS = (
    "available",
    "mono_ts",
    "heating",
    "sensor_frozen",
    "current_temperature",
    "heat_sp",
    "tpi_duty",
    "heat_demand",
)

TIMING_KEYS = ("tick_ms", "tick_ms_ewma", "tick_ms_max", "tick_over_budget")

# Frozen once from the Ist-Zustand (this exact ROOM_DATA, one normal tick,
# 156 keys). A mismatch = deliberate coordinator.data API change -> review,
# then re-freeze. NOTE: 'compressor_gate_would_block' and
# 'compressor_mode_hold_remaining' exist only when the shadow try
# (coordinator.py 3361-3496) succeeds — their absence would also reveal a
# silently failing shadow block.
EXPECTED_AVAILABLE_KEYS: list[str] = [
    "abs_humidity_gkg",
    "actuator_hvac_action",
    "adaptive_cool",
    "adaptive_cool_mode",
    "available",
    "beta_s",
    "binding_lower_cause",
    "binding_precedence",
    "boost_expires_at",
    "ca_cycles_per_h",
    "ca_deviation_k",
    "ca_minutes",
    "ca_time_in_band",
    "category",
    "coasting",
    "comfort_high",
    "comfort_low",
    "compressor_gate_would_block",
    "compressor_mode_hold_remaining",
    "confidence",
    "cool_raise_reason",
    "cool_raised",
    "cool_sp",
    "cool_sp_active",
    "cool_sp_compensated",
    "cool_sp_eff",
    "cooling",
    "cover_predicted_peak",
    "cover_shade_position",
    "cover_shade_reason",
    "cover_would_shade",
    "current_humidity",
    "current_temperature",
    "device_alarm",
    "device_hvac_mode",
    "device_schedule_active",
    "dewpoint",
    "dry_active",
    "dynamics_profile",
    "en_cool_upper",
    "fan_ce_k",
    "fan_circ_reason",
    "fan_circ_shadow",
    "fan_cool_sp_shadow",
    "fan_velocity_ms",
    "final_mode",
    "fr_active",
    "fr_adaptive_lower",
    "fr_adaptive_upper",
    "fr_cool_sp",
    "fr_heat_sp",
    "heat_demand",
    "heat_sp",
    "heating",
    "heating_failure",
    "home_present",
    "humidity_action",
    "humidity_reason",
    "hvac_action",
    "identification_progress",
    "identified",
    "idle_park_mode",
    "learning_phase",
    "minutes_to_comfort",
    "minutes_to_setback",
    "mode",
    "mode_adopt_reason",
    "mode_nudge_blocked",
    "mode_override",
    "mold_capped",
    "mono_ts",
    "mould_floor",
    "mpc_active",
    "mpc_power",
    "mpc_regime",
    "mpc_setpoint",
    "mpc_weight",
    "mrt",
    "mrt_internal",
    "mrt_source",
    "multi_active_source",
    "multi_blocked",
    "multi_device_health",
    "multi_min_off_remaining",
    "multi_reason",
    "multi_severity",
    "norm_binding",
    "occupied",
    "operative_temperature",
    "outcome_last_score",
    "outcome_n",
    "outcome_obs_avg",
    "outcome_ts_avg",
    "override_active",
    "override_clamped",
    "override_expires_at",
    "override_policy",
    "override_reason",
    "override_requested",
    "override_stats",
    "pi_active",
    "pi_integral_time_h",
    "pi_offset",
    "pi_setpoint",
    "pmv",
    "pmv_category",
    "ppd",
    "preheat_outdoor",
    "preheating",
    "presence_level",
    "preset",
    "q_solar",
    "q_solar_internal",
    "q_solar_source",
    "ref_offset",
    "ref_offset_conditioning",
    "ref_offset_dev",
    "ref_offset_trusted",
    "reg_period_s",
    "rh_high_used",
    "room_absent_min",
    "savings_eur_month",
    "savings_kwh_month",
    "savings_pct",
    "schedule_state",
    "seasonless_phase",
    "seasonless_rate",
    "sensor_frozen",
    "sensor_placement_suspect",
    "source",
    "sp_adopt_reason",
    "t_rm",
    "t_rm_internal",
    "t_rm_source",
    "target_temperature",
    "tau_confidence",
    "tau_hours",
    "tau_settle_minutes",
    "tau_settled",
    "tick_ms",
    "tick_ms_ewma",
    "tick_ms_max",
    "tick_over_budget",
    "tpi_active",
    "tpi_duty",
    "tpi_valve_entity",
    "tpi_valve_percent",
    "trv_input_mode",
    "valve_closing_steps",
    "valve_health",
    "valve_idle_steps",
    "window_auto_detected",
    "window_auto_slope",
    "window_auto_threshold",
    "window_bypass",
    "window_open",
]


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _set_room(
    hass: HomeAssistant, *, room: float | str = 18.0, sp: float = 20.0
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": sp,
            "current_temperature": room if isinstance(room, float) else None,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _normal_tick(hass: HomeAssistant) -> Any:
    """Set up the room, then drive exactly one deterministic available tick."""
    _set_room(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    # re-arm the recorders AFTER setup (platform forwarding re-registers the
    # real climate handlers, clobbering any pre-setup mock).
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord._clock = _FakeClock(1000.0)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True
    return coord


async def test_available_form_pins_hub_critical_keys(hass: HomeAssistant) -> None:
    """(a) One normal tick -> every hub-critical key exists with its pinned
    shape: available is True, tpi_duty EXISTS (None allowed, coordinator.py
    3353/3489), and the four tick-timing diagnostics are attached (1842–1849)."""
    coord = await _normal_tick(hass)
    data = coord.data

    missing = [k for k in (*HUB_CRITICAL_KEYS, *TIMING_KEYS) if k not in data]
    assert not missing, f"hub-critical keys missing from coordinator.data: {missing}"

    assert data["available"] is True
    assert isinstance(data["mono_ts"], float)
    assert data["mono_ts"] == 1000.0  # the FakeClock tick stamp (H3/ADR-0038)
    assert isinstance(data["heating"], bool)
    assert isinstance(data["sensor_frozen"], bool)
    assert data["current_temperature"] == 18.0
    assert isinstance(data["heat_sp"], float)
    # tpi_duty: the KEY is the contract; without a valve entity today's value
    # is None (evaluate_tpi_shadow inactive) — both None and float are legal.
    assert data["tpi_duty"] is None or isinstance(data["tpi_duty"], float)
    assert isinstance(data["heat_demand"], (int, float))
    assert 0.0 <= float(data["heat_demand"]) <= 1.0
    assert isinstance(data["tick_ms"], float)
    assert isinstance(data["tick_ms_ewma"], float)
    assert isinstance(data["tick_ms_max"], float)
    assert isinstance(data["tick_over_budget"], bool)


async def test_available_form_key_snapshot(hass: HomeAssistant) -> None:
    """(a) Snapshot: the EXACT sorted key set of the available payload for this
    fixed room config. Any diff is a deliberate coordinator.data API change."""
    coord = await _normal_tick(hass)
    actual = sorted(coord.data.keys())
    assert actual == EXPECTED_AVAILABLE_KEYS, (
        "coordinator.data key set changed (deliberate API change? then review "
        f"and re-freeze EXPECTED_AVAILABLE_KEYS).\nACTUAL = {actual!r}"
    )


async def test_unavailable_form_is_exactly_minimal(hass: HomeAssistant) -> None:
    """(b) Room sensor unavailable -> the payload is EXACTLY
    {"available": False} (coordinator.py 2040): no tick_ms* (1845 gates the
    timing attach on the available form), no other keys."""
    coord = await _normal_tick(hass)
    assert coord.data.get("available") is True  # precondition: was healthy

    hass.states.async_set("sensor.room_temp", "unavailable", {})
    coord._clock.t = 1100.0  # fresh loss, far below UNAVAILABLE_SAFE_AFTER_S
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.last_update_success is True
    assert coord.data == {"available": False}


async def test_unavailable_safe_form_is_exactly_minimal(hass: HomeAssistant) -> None:
    """(b) Sustained loss past UNAVAILABLE_SAFE_AFTER_S -> the safe state is
    written and the payload is EXACTLY {"available": False,
    "unavailable_safe": True} (coordinator.py 2035–2039) — still no tick_ms*."""
    coord = await _normal_tick(hass)

    # tick 1 of the outage stamps _unavailable_since = 1100.0 (2021–2022)
    hass.states.async_set("sensor.room_temp", "unavailable", {})
    coord._clock.t = 1100.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.data == {"available": False}

    # tick 2 — past the timeout: safe state engages
    coord._clock.t = 1100.0 + UNAVAILABLE_SAFE_AFTER_S + 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.last_update_success is True
    assert coord.data == {"available": False, "unavailable_safe": True}
