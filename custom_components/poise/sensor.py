"""Diagnostic sensors over the coordinator data (ADR-0016).

Thin views so the internal estimators — EKF model (tau, confidence, beta_s,
identification), running-mean T_rm, solar q_solar, virtual MRT, operative
temperature — get long-term statistics and can be charted. All entities are
DIAGNOSTIC; the control logic stays in the coordinator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoiseCoordinator


@dataclass(frozen=True, kw_only=True)
class PoiseSensorDescription(SensorEntityDescription):  # type: ignore[misc]
    """Sensor description with a pull function over the coordinator data."""

    value_fn: Callable[[dict[str, Any]], float | str | datetime | None]


def _scaled(
    key: str, factor: float = 1.0, digits: int = 2
) -> Callable[[dict[str, Any]], float | None]:
    def fn(data: dict[str, Any]) -> float | None:
        v = data.get(key)
        return round(float(v) * factor, digits) if isinstance(v, (int, float)) else None

    return fn


def _timestamp(key: str) -> Callable[[dict[str, Any]], datetime | None]:
    """Read a wall-clock epoch float from the data and hand it to a TIMESTAMP
    sensor as an aware datetime (``None`` when there is no active expiry)."""

    def fn(data: dict[str, Any]) -> datetime | None:
        v = data.get(key)
        return dt_util.utc_from_timestamp(float(v)) if isinstance(v, (int, float)) else None

    return fn


_TEMP = SensorDeviceClass.TEMPERATURE
_MEAS = SensorStateClass.MEASUREMENT
_DIAG = EntityCategory.DIAGNOSTIC

SENSORS: tuple[PoiseSensorDescription, ...] = (
    PoiseSensorDescription(
        key="t_rm",
        translation_key="t_rm",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=_TEMP,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=1,
        value_fn=_scaled("t_rm", digits=1),
    ),
    PoiseSensorDescription(
        key="mrt",
        translation_key="mrt",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=_TEMP,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=1,
        value_fn=_scaled("mrt", digits=1),
    ),
    PoiseSensorDescription(
        key="operative_temperature",
        translation_key="operative_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=_TEMP,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=1,
        value_fn=_scaled("operative_temperature", digits=1),
    ),
    PoiseSensorDescription(
        key="q_solar",
        translation_key="q_solar",
        entity_registry_enabled_default=False,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=2,
        value_fn=_scaled("q_solar"),
    ),
    PoiseSensorDescription(
        key="beta_s",
        translation_key="beta_s",
        entity_registry_enabled_default=False,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=2,
        value_fn=_scaled("beta_s"),
    ),
    PoiseSensorDescription(
        key="tau_hours",
        translation_key="tau_hours",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=1,
        value_fn=_scaled("tau_hours", digits=1),
    ),
    PoiseSensorDescription(
        key="confidence",
        translation_key="confidence",
        native_unit_of_measurement=PERCENTAGE,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=0,
        value_fn=_scaled("confidence", 100.0, 0),
    ),
    PoiseSensorDescription(
        key="identification_progress",
        translation_key="identification_progress",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=0,
        value_fn=_scaled("identification_progress", 100.0, 0),
    ),
    PoiseSensorDescription(
        key="learning_phase",
        translation_key="learning_phase",
        device_class=SensorDeviceClass.ENUM,
        entity_category=_DIAG,
        options=["cold", "early", "learning", "identified"],
        value_fn=lambda d: d.get("learning_phase"),
    ),
    # Phase-4 shadow MPC (ADR-0033): diagnostic only, dormant until identified.
    PoiseSensorDescription(
        key="mpc_power",
        translation_key="mpc_power",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=0,
        value_fn=_scaled("mpc_power", 100.0, 0),
    ),
    PoiseSensorDescription(
        key="mpc_weight",
        translation_key="mpc_weight",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=0,
        value_fn=_scaled("mpc_weight", 100.0, 0),
    ),
    # ADR-0055 M1 (Phase-3 baseline): the EN-15500-1 control-accuracy signals as
    # measurement sensors so long-term statistics capture the pre-flip distribution
    # the winter threshold calibration (Phase 4) needs — the climate attributes
    # alone only live in the recorder's short-term history (~10 days).
    PoiseSensorDescription(
        key="ca_deviation_k",
        translation_key="ca_deviation_k",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTemperature.KELVIN,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=2,
        value_fn=_scaled("ca_deviation_k", digits=2),
    ),
    PoiseSensorDescription(
        key="ca_cycles_per_h",
        translation_key="ca_cycles_per_h",
        entity_registry_enabled_default=False,
        native_unit_of_measurement="/h",
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=2,
        value_fn=_scaled("ca_cycles_per_h", digits=2),
    ),
    PoiseSensorDescription(
        key="ca_time_in_band",
        translation_key="ca_time_in_band",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=0,
        value_fn=_scaled("ca_time_in_band", digits=0),
    ),
    # ADR-0046 §8: the live compressor-guard suppression as 0/1 so its LTS mean is
    # the block fraction — watch it stays near zero (a rising fraction is a finding).
    PoiseSensorDescription(
        key="compressor_guard_blocked",
        translation_key="compressor_guard_blocked",
        entity_registry_enabled_default=False,
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=0,
        value_fn=lambda d: 1.0 if d.get("mode_nudge_blocked") else 0.0,
    ),
    # ADR-0020: per-zone tick wall-time (smoothed) — the performance-budget signal.
    PoiseSensorDescription(
        key="tick_duration_ms",
        translation_key="tick_duration_ms",
        entity_registry_enabled_default=False,
        native_unit_of_measurement="ms",
        state_class=_MEAS,
        entity_category=_DIAG,
        suggested_display_precision=1,
        value_fn=_scaled("tick_ms_ewma", digits=1),
    ),
    # P1-4b: the manual-hold expiry as a first-class TIMESTAMP entity, so the
    # override end-time is visible (and lands in history) without the Poise card.
    # Enabled by default -- unlike the estimator diagnostics, this is user-facing.
    PoiseSensorDescription(
        key="override_expires_at",
        translation_key="override_expires_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=_DIAG,
        value_fn=_timestamp("override_expires_at"),
    ),
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
    async_add_entities(PoiseSensor(coordinator, entry, d) for d in SENSORS)


class PoiseSensor(CoordinatorEntity[PoiseCoordinator], SensorEntity):  # type: ignore[misc]
    _attr_has_entity_name = True
    entity_description: PoiseSensorDescription

    def __init__(
        self,
        coordinator: PoiseCoordinator,
        entry: ConfigEntry,
        description: PoiseSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.zone_name,
            manufacturer="Poise",
            model="Setpoint Thermostat",
            entry_type=DeviceEntryType.SERVICE,
            via_device=coordinator.via_device_id,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(
            (self.coordinator.data or {}).get("available")
        )

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self.coordinator.data or {})
