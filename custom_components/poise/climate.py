"""Climate platform — one Poise thermostat per room (ADR-0016).

A thin view over the coordinator (which runs the pure pipeline). The comfort
attributes are the card contract; the entity performs no thermal arbitration —
it only routes user intent (enable, mode, preset, hold) into the coordinator.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MAX_C, DOMAIN, FROST_FLOOR_C
from .control.override import OverrideMode
from .coordinator import PoiseCoordinator
from .devices.hvac_modes import (
    available_hvac_modes,
    climate_mode_for_hvac,
    current_hvac_mode,
    resolve_hvac_action,
)
from .runtime.tick_inputs import ActuatorSnapshot

_ATTRS = (
    "operative_temperature",
    "t_rm",
    "t_rm_source",
    "t_rm_internal",
    "comfort_low",
    "comfort_high",
    "binding_lower_cause",
    "category",
    "source",
    "tau_hours",
    "confidence",
    "learning_phase",
    "window_open",
    "window_auto_detected",
    "window_auto_slope",
    "window_auto_threshold",
    "window_bypass",
    "cover_predicted_peak",
    "cover_would_shade",
    "cover_shade_position",
    "cover_shade_reason",
    "heating_failure",
    "cooling_failure",  # C.8 cooling pendant to heating_failure
    # C.8 write-convergence telemetry (diagnostic; 0 = converging normally)
    "sp_diverged_writes",
    "mode_diverged_nudges",
    "heat_sp",
    "cool_sp",
    "adaptive_cool",
    "adaptive_cool_mode",
    "mode_nudge_blocked",
    "tick_over_budget",
    "mould_floor",
    "dewpoint",
    "mode",
    "identified",
    "identification_progress",
    "schedule_state",
    "minutes_to_comfort",
    "preheating",
    "preheat_outdoor",
    "coasting",
    "minutes_to_setback",
    "q_solar",
    "q_solar_source",
    "q_solar_internal",
    "beta_s",
    "mrt",
    "mrt_source",
    "mrt_internal",
    "sensor_frozen",
    "norm_binding",
    "binding_precedence",
    "seasonless_phase",
    "seasonless_rate",
    "device_schedule_active",
    "device_alarm",
    "trv_input_mode",
    "sensor_placement_suspect",
    "pi_active",
    "pi_setpoint",
    "pi_offset",
    "valve_health",
    "valve_closing_steps",
    "valve_idle_steps",
    "tpi_active",
    "tpi_duty",
    "tpi_valve_percent",
    "mpc_active",
    "mpc_power",
    "mpc_weight",
    "mpc_setpoint",
    "mpc_regime",
    # ADR-0045: heating-degree-hour savings estimate (diagnostic only).
    "savings_kwh_month",
    "savings_eur_month",
    "savings_pct",
    # climate-band shadow diagnostics (observe-only; not a control input):
    # ADR-0051 cool raise, ADR-0050 humidity/dry, ADR-0023 free-running,
    # ADR-0053 fan circulation + ADR-0054/0068 fan cooling-effect.
    "cool_sp_eff",
    "cool_sp_active",
    "cool_raised",
    "cool_raise_reason",
    "en_cool_upper",
    "humidity_action",
    "dry_active",
    "humidity_reason",
    "abs_humidity_gkg",
    "rh_high_used",
    # ADR-0066 humidity axis (monitor/advice only, never a control input)
    "abs_humidity_gm3",
    "abs_humidity_out_gm3",
    "surface_rh",
    "surface_rh_mean",
    "mold_capped",
    "rh_max_safe",
    "abs_max_safe",
    "fabric_conflict",
    "vent_action",
    "vent_reason",
    "vent_level",
    "vent_delta_gm3",
    "compressor_gate_would_block",
    "compressor_mode_hold_remaining",
    "fr_active",
    "fr_heat_sp",
    "fr_cool_sp",
    "fr_adaptive_lower",
    "fr_adaptive_upper",
    "fan_circ_shadow",
    "fan_circ_reason",
    "fan_ce_k",
    "fan_cool_sp_shadow",
    "fan_velocity_ms",
    "pmv",
    "ppd",
    "pmv_category",
    "clo_used",
    "clo_source",
    "met_used",
    "pmv_valid",
    "clo_offset",
    # ADR-0069 E7 (Card): "Aktive Behaglichkeit" — toggle state, fan-first
    # phase, tier-2 latch states and the applied measures (display only).
    "active_comfort",
    "fan_first_phase",
    "tier2_fan_ce",
    "tier2_pmv_offset",
    # ADR-0069 N1: maturing progress ("reift · X/24 h" + paused hint).
    "tier2_fan_ce_dwell_min",
    "tier2_pmv_dwell_min",
    "tier2_dwell_target_min",
    "tier2_dwelling",
    "fan_ce_credit_k",
    "pmv_offset_k",
    "ca_deviation_k",
    "ca_time_in_band",
    "ca_cycles_per_h",
    "ca_minutes",
    "override_clamped",
    # ADR-0059 manual-hold + timed-Boost lifecycle (card contract).
    "override_active",
    "mode_override",  # the held device mode (off/dry/fan_only/…) or None
    "override_reason",  # hold origin (ui_setpoint / device_adopt_* / frost…)
    # Why THIS tick did / did not adopt a manual device change ("" when
    # nothing seen; e.g. own_echo / safety_window / stable_offset / hold_resumed).
    "mode_adopt_reason",
    "sp_adopt_reason",
    "override_expires_at",
    "override_policy",
    "override_requested",
    "boost_expires_at",
    "preset",
    "ref_offset",
    "ref_offset_dev",
    "ref_offset_trusted",
    "ref_offset_conditioning",
    "tau_confidence",
    "tau_settled",
    "cool_sp_compensated",
    # This zone's boiler heat-demand fraction (0..1) -- the value the
    # multi-zone hub aggregates for the shared boiler (diagnostic, observe-only).
    "heat_demand",
)

# The recorder diet (ISO-review E1). The ~150 attributes above change nearly
# every 60 s tick, so the recorder can never deduplicate the attribute blob —
# multi-KB database rows per zone per minute. Only THIS headline set keeps
# history: the card's 24 h chart reads ``operative_temperature`` (plus the
# built-in ``temperature``) from recorded attributes, and the rest are the
# slow-moving episode/band series users chart (comfort band, safety verdicts,
# hold lifecycle, mould floor). Everything else stays a LIVE state attribute —
# the card and templates read the state machine, not the database — and the
# long-term series that matter for the shadow→live evidence have their own
# opt-in statistics sensors (see ``sensor.py``).
_RECORDED_ATTRS: frozenset[str] = frozenset(
    {
        "operative_temperature",
        "comfort_low",
        "comfort_high",
        "heat_sp",
        "cool_sp",
        "pmv",
        "ppd",
        "window_open",
        "sensor_frozen",
        "heating_failure",
        "cooling_failure",
        "override_active",
        "override_expires_at",
        "mould_floor",
    }
)


# Coordinator-driven: entities read shared data and writes go through the
# single actuator choke-point, so updates need no per-entity throttling.
PARALLEL_UPDATES = 0

# The step published while the actuator reports none of its own -- the value
# this entity has always published, and a granularity every heating device can
# honour. Deliberately NOT the write path's 0.1 fallback (phase_actuate): that
# one snaps an already-computed setpoint and must not coarsen it, while this is
# the granularity offered to a human on a slider.
_FALLBACK_STEP_C = 0.5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoiseCoordinator = entry.runtime_data
    async_add_entities([PoiseClimate(coordinator, entry)])


class PoiseClimate(CoordinatorEntity[PoiseCoordinator], ClimateEntity):  # type: ignore[misc]
    """The room thermostat.

    Exposes a SINGLE target temperature — a set writes a manual hold
    (ADR-0059) — plus HA preset modes. The dual-setpoint band itself
    (``heat_sp``/``cool_sp``, ``comfort_low``/``comfort_high``) travels as
    read-only attributes, deliberately NOT as ``TARGET_TEMPERATURE_RANGE``:
    the band is arbitrated by the coordinator, not set by the user
    (ADR-0016/0023).
    """

    _attr_has_entity_name = True
    _attr_name = None
    # Recorder diet: every extra attribute is either in ``_RECORDED_ATTRS``
    # (keeps history) or excluded here — the set difference makes the
    # partition total, so a new ``_ATTRS`` key defaults to unrecorded and
    # must OPT IN to writing database history (pinned by
    # ``tests/integration/test_entity_defaults.py``).
    _unrecorded_attributes = frozenset(_ATTRS) - _RECORDED_ATTRS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_preset_modes = [m.value for m in OverrideMode]

    def __init__(self, coordinator: PoiseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.zone_name,
            manufacturer="Poise",
            model="Setpoint Thermostat",
            entry_type=DeviceEntryType.SERVICE,
            via_device=coordinator.via_device_id,
        )

    async def async_added_to_hass(self) -> None:
        # ADR-0059 §4: hand the resolved entity_id to the coordinator so the
        # poise_override_ended event can name this climate entity.
        await super().async_added_to_hass()
        self.coordinator.set_climate_entity_id(self.entity_id)

    @property
    def _d(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self._d.get("available"))

    @property
    def current_temperature(self) -> float | None:
        return self._d.get("current_temperature")

    @property
    def current_humidity(self) -> float | None:
        # ADR-0049: publish the room humidity so the card's humidity lamp (and
        # the native HA thermostat card) can read it. None when no RH sensor.
        return self._d.get("current_humidity")

    @property
    def target_temperature(self) -> float | None:
        return self._d.get("target_temperature")

    # ---- published setpoint envelope (dynamic, not constants) --------------
    #
    # The write side has always known the actuator's real limits; the entity
    # used to publish ``[FROST_FLOOR_C, DEVICE_MAX_C]`` and a fixed 0.5 step,
    # so the UI offered values the device cannot reach and hid values it can.
    #
    # What the published pair MEANS is fixed by HA: ``climate.set_temperature``
    # is validated against exactly ``min_temp``/``max_temp`` and raises
    # ``ServiceValidationError`` ("temp_out_of_range") outside them. Everything
    # that passes lands in ``async_set_temperature`` -> ``set_override``, which
    # sanitises the hold into ``[FROST_FLOOR_C, DEVICE_MAX_C]``. So the honest
    # envelope is the INTERSECTION of Poise's accepted range and the device's
    # physical one: every accepted value is kept unchanged, every value that
    # would be silently clamped is refused up front with the limit named.
    #
    # NOT part of the envelope: the arbitrated comfort band (``heat_sp`` /
    # ``cool_sp``, which also caps a hold -- see ``override_clamped``) and the
    # dynamic mould floor. Both move every tick and are control decisions, not
    # input validation; publishing them would make the slider jump under the
    # user's finger (and the band is read-only by design, see the class
    # docstring).

    @property
    def _actuator(self) -> ActuatorSnapshot:
        """The actuator's own limits, freshly read.

        A display-time read outside the tick, taken through the single
        reading adapter ``ha/input_reader`` (the phase-4 read boundary) --
        the same route the ``capability`` / ``hvac_modes`` pair already uses,
        and one ``states.get`` for the whole snapshot. Deliberately NOT
        ``coordinator.data``: the limits must be right before the first tick
        has ever run and while the zone reports unavailable, neither of which
        carries pipeline output.
        """
        # Named local: CoordinatorEntity is untyped to mypy (HA stubs are
        # ignored), so ``self.coordinator`` arrives as Any.
        coordinator: PoiseCoordinator = self.coordinator
        return coordinator.input_reader.read_actuator()

    @property
    def max_temp(self) -> float:
        """The device ceiling, never above Poise's own ``DEVICE_MAX_C``.

        A device reporting more (an AC at 35 °C) would otherwise advertise a
        setpoint ``sanitize_override`` silently pulls back to 30 °C. Absent or
        non-numeric (no actuator state yet, device offline): the constant --
        ``None`` or a raise here would break the entity, the card and the HA
        thermostat card at once, so the fallback is exactly today's value.
        """
        device_max = self._actuator.max_temp
        return DEVICE_MAX_C if device_max is None else min(device_max, DEVICE_MAX_C)

    @property
    def min_temp(self) -> float:
        """The device floor, raised to the frost floor, kept below the ceiling.

        Both directions are real. ``FROST_FLOOR_C`` is a safety floor Poise
        never goes below (``sanitize_override`` clamps a hold up to it,
        ``resolve_write_target`` re-applies it as a HEALTH floor), so passing a
        lower device minimum straight through -- Zigbee TRVs commonly report
        5 °C -- would advertise setpoints the zone discards. The other way round
        matters just as much: a 16 °C-minimum AC must not advertise 7 °C, which
        is the improvement over the old constant.

        The closing ``min(..., self.max_temp)`` keeps the pair ordered even for
        a device whose whole range sits above ``DEVICE_MAX_C``; an inverted
        envelope makes the HA slider unusable and every set call fail.
        """
        device_min = self._actuator.min_temp
        floor = FROST_FLOOR_C if device_min is None else max(device_min, FROST_FLOOR_C)
        return min(floor, self.max_temp)

    @property
    def target_temperature_step(self) -> float:
        """The device's own step, else ``_FALLBACK_STEP_C``.

        HA serialises ``ClimateEntity.target_temperature_step`` under the wire
        key ``target_temp_step``, not under the property name (review A.4); the
        snapshot reads it under that key, so this property inherits the one
        spelling the rest of the code uses. A non-positive step is treated as
        absent: 0 makes HA's stepping arithmetic degenerate.
        """
        step = self._actuator.target_temperature_step
        return step if step is not None and step > 0.0 else _FALLBACK_STEP_C

    @property
    def hvac_modes(self) -> list[HVACMode]:
        can_heat, can_cool = self.coordinator.capability
        return [HVACMode(m) for m in available_hvac_modes(can_heat, can_cool)]

    @property
    def hvac_mode(self) -> HVACMode:
        can_heat, can_cool = self.coordinator.capability
        return HVACMode(
            current_hvac_mode(
                self.coordinator.enabled,
                self.coordinator.climate_mode,
                can_heat,
                can_cool,
            )
        )

    @property
    def hvac_action(self) -> HVACAction:
        # Display contract: report what the zone is *doing now*. Prefer the
        # actuator's own reported action; fall back to the arbitrated
        # direction (final_mode) -- never the raw "manual" override tag,
        # which is an origin, not a direction.
        value = resolve_hvac_action(
            enabled=self.coordinator.enabled,
            final_mode=self._d.get("final_mode") or "idle",
            actuator_action=self._d.get("actuator_hvac_action"),
            idle_park_mode=self._d.get("idle_park_mode"),
        )
        try:
            return HVACAction(value)
        except ValueError:  # a device-passthrough action older HA cores may lack
            return HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        return str(self.coordinator.preset.value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {key: self._d.get(key) for key in _ATTRS}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self.coordinator.set_override(float(temp))
            await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self.coordinator.set_preset(OverrideMode(preset_mode))
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            self.coordinator.set_enabled(False)
        else:
            self.coordinator.set_enabled(True)
            self.coordinator.set_climate_mode(climate_mode_for_hvac(hvac_mode.value))
        # ADR-0059 §5: selecting an ACTIVE mode returns to automatic control and
        # clears any manual hold; OFF must NOT clear it (enables "off + resume").
        if hvac_mode != HVACMode.OFF:
            self.coordinator.set_override(None, reason="mode_change")
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        self.coordinator.set_enabled(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        self.coordinator.set_enabled(False)
        await self.coordinator.async_request_refresh()
