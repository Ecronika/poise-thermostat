"""Climate platform — one Poise thermostat per room (ADR-0016).

A thin view over the coordinator (which runs the pure pipeline). The comfort
attributes are the card contract; the entity never contains control logic.
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
)

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
    "heat_sp",
    "cool_sp",
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
    # climate-band shadow diagnostics (observe-only; not a control input):
    # ADR-0051 cool raise, ADR-0050 humidity/dry, ADR-0023 free-running,
    # ADR-0053 fan circulation + roadmap M3 fan cooling-effect.
    "cool_sp_eff",
    "cool_sp_active",
    "cool_raised",
    "cool_raise_reason",
    "en_cool_upper",
    "humidity_action",
    "dry_active",
    "humidity_reason",
    "fr_active",
    "fr_heat_sp",
    "fr_cool_sp",
    "fr_adaptive_lower",
    "fr_adaptive_upper",
    "fan_circ_shadow",
    "fan_circ_reason",
    "fan_ce_k",
    "fan_cool_sp_shadow",
    "pmv",
    "ppd",
    "pmv_category",
    "ca_deviation_k",
    "ca_time_in_band",
    "ca_cycles_per_h",
    "ca_minutes",
)


# Coordinator-driven: entities read shared data and writes go through the
# single actuator choke-point, so updates need no per-entity throttling.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoiseCoordinator = entry.runtime_data
    async_add_entities([PoiseClimate(coordinator, entry)])


class PoiseClimate(CoordinatorEntity[PoiseCoordinator], ClimateEntity):  # type: ignore[misc]
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_preset_modes = [m.value for m in OverrideMode]
    _attr_min_temp = FROST_FLOOR_C
    _attr_max_temp = DEVICE_MAX_C
    _attr_target_temperature_step = 0.5

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
        if not self.coordinator.enabled:
            return HVACAction.OFF
        if self._d.get("heating"):
            return HVACAction.HEATING
        if self._d.get("mode") == "cool":
            return HVACAction.COOLING
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
        # selecting a mode returns to automatic control: clear any manual hold (M2)
        self.coordinator.set_override(None)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        self.coordinator.set_enabled(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        self.coordinator.set_enabled(False)
        await self.coordinator.async_request_refresh()
