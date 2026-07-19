"""Phase-1 contract tests for ``runtime.config`` (pure, no HA import).

Pins the ``ZoneStructure``/``ZoneTuning``/``ZoneConfig`` field contract from
the refactoring plan (section 2/3): exact field sets, frozen behaviour, the
rev.-3 correction that ``climate_mode`` is NOT tuning (store-owned user
intent), and the ``structures_equal`` seam for the phase-2
``structural_unchanged`` rewrite.
"""

from __future__ import annotations

import dataclasses

import pytest

from custom_components.poise.comfort.en16798 import Category
from custom_components.poise.comfort.presence import PresenceConfig
from custom_components.poise.comfort.schedule import ComfortSchedule, ComfortWindow
from custom_components.poise.control.dynamics import DeviceDynamics
from custom_components.poise.control.hdh_savings import HdhConfig
from custom_components.poise.control.mpc import MpcParams
from custom_components.poise.control.override import OverrideConfig
from custom_components.poise.control.window_auto import WindowAutoConfig
from custom_components.poise.runtime.config import (
    ZoneConfig,
    ZoneStructure,
    ZoneTuning,
    structures_equal,
)


def _structure(*, temperature_sensor: str = "sensor.living_temp") -> ZoneStructure:
    """A realistic living-room wiring (all optional slots exercised)."""
    return ZoneStructure(
        zone_name="Living room",
        temperature_sensor=temperature_sensor,
        actuator="climate.living_trv",
        trm="sensor.outdoor_running_mean",
        outdoor="sensor.outdoor_temp",
        humidity="sensor.living_rh",
        mrt=None,
        presence_home_entities=("person.alice", "person.bob"),
        occupancy_entities=("binary_sensor.living_occupancy",),
        windows=("binary_sensor.living_window", "binary_sensor.balcony_door"),
        weather="weather.home",
        irradiance=None,
        trv_ext_temp="number.living_trv_external_temp",
    )


def _tuning(*, comfort_base: float = 21.0) -> ZoneTuning:
    """A realistic tuning set mirroring today's ``__init__`` defaults."""
    return ZoneTuning(
        window_auto_cfg=WindowAutoConfig(),
        override_policy="schedule",
        override_cfg=OverrideConfig(),
        trace_enabled=False,
        presence_cfg=PresenceConfig(),
        category=Category.II,
        comfort_base=comfort_base,
        hdh_cfg=HdhConfig(annual_kwh=9000.0, price_eur_kwh=0.32),
        dynamics_override=None,
        mpc_params=MpcParams(),
        compressor_guard="auto",
        comp_min_off_opt=None,
        comp_mode_hold_opt=300.0,
        thermal_shock_delta=2.0,
        cool_hard_cap=30.0,
        adaptive_cool_cfg="auto",
        cool_min_outdoor=20.0,
        heat_max_outdoor=17.0,
        heat_lockout_enabled=True,
        cool_lockout_enabled=True,
        priority=0.5,
        schedule=ComfortSchedule.from_windows([ComfortWindow(6 * 60, 22 * 60)], 3.0),
        optimal_start=True,
        optimal_stop=True,
        adopt_external_setpoint=True,
        adopt_external_mode=False,
        operative_input=False,
    )


def _field_names(cls: type) -> tuple[str, ...]:
    return tuple(f.name for f in dataclasses.fields(cls))


# ---------------------------------------------------------------------------
# construction + field contract
# ---------------------------------------------------------------------------


def test_zone_config_construction_roundtrip() -> None:
    cfg = ZoneConfig(structure=_structure(), tuning=_tuning())
    assert cfg.structure.temperature_sensor == "sensor.living_temp"
    assert cfg.structure.actuator == "climate.living_trv"
    assert cfg.structure.mrt is None
    assert cfg.structure.windows == (
        "binary_sensor.living_window",
        "binary_sensor.balcony_door",
    )
    assert cfg.tuning.category is Category.II
    assert cfg.tuning.comfort_base == 21.0
    # The embedded schedule is live-usable, not just carried along.
    assert cfg.tuning.schedule.state_at(12 * 60).is_comfort
    assert not cfg.tuning.schedule.state_at(2 * 60).is_comfort


def test_structure_field_contract_is_exactly_the_plan_table() -> None:
    # Plan section 3, ZoneStructure row: 13 fields, in wiring order.
    assert _field_names(ZoneStructure) == (
        "zone_name",
        "temperature_sensor",
        "actuator",
        "trm",
        "outdoor",
        "humidity",
        "mrt",
        "presence_home_entities",
        "occupancy_entities",
        "windows",
        "weather",
        "irradiance",
        "trv_ext_temp",
    )


def test_tuning_field_contract_is_exactly_the_plan_table() -> None:
    # Plan section 3, ZoneTuning row: 27 fields (climate_mode removed, rev. 3).
    assert _field_names(ZoneTuning) == (
        "window_auto_cfg",
        "override_policy",
        "override_cfg",
        "trace_enabled",
        "presence_cfg",
        "category",
        "comfort_base",
        "hdh_cfg",
        "dynamics_override",
        "mpc_params",
        "compressor_guard",
        "comp_min_off_opt",
        "comp_mode_hold_opt",
        "thermal_shock_delta",
        "cool_hard_cap",
        "adaptive_cool_cfg",
        "cool_min_outdoor",
        "heat_max_outdoor",
        "heat_lockout_enabled",
        "cool_lockout_enabled",
        "priority",
        "schedule",
        "optimal_start",
        "optimal_stop",
        "adopt_external_setpoint",
        "adopt_external_mode",
        "operative_input",
    )
    assert len(dataclasses.fields(ZoneTuning)) == 27


def test_tuning_has_no_climate_mode_field() -> None:
    # Rev.-3 correction: climate_mode is store-owned user intent
    # (UserControlState), never config — assert it can NEVER sneak back in.
    assert "climate_mode" not in {f.name for f in dataclasses.fields(ZoneTuning)}


def test_zone_config_field_contract() -> None:
    assert _field_names(ZoneConfig) == ("structure", "tuning")


def test_dynamics_override_accepts_enum_and_none() -> None:
    # None = auto-classify (today's "auto"/unknown string); an explicit
    # DeviceDynamics pins the ADR-0052 profile.
    assert _tuning().dynamics_override is None
    forced = dataclasses.replace(_tuning(), dynamics_override=DeviceDynamics.VERY_SLOW)
    assert forced.dynamics_override is DeviceDynamics.VERY_SLOW


# ---------------------------------------------------------------------------
# frozen behaviour
# ---------------------------------------------------------------------------


def test_structure_is_frozen() -> None:
    structure = _structure()
    with pytest.raises(dataclasses.FrozenInstanceError):
        structure.actuator = "climate.other"  # type: ignore[misc]


def test_tuning_is_frozen() -> None:
    tuning = _tuning()
    with pytest.raises(dataclasses.FrozenInstanceError):
        tuning.comfort_base = 22.0  # type: ignore[misc]


def test_zone_config_is_frozen() -> None:
    cfg = ZoneConfig(structure=_structure(), tuning=_tuning())
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.tuning = _tuning()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# structures_equal (phase-2 structural_unchanged seam)
# ---------------------------------------------------------------------------


def test_structures_equal_for_identical_wiring() -> None:
    assert structures_equal(_structure(), _structure())


def test_structures_equal_detects_any_field_change() -> None:
    base = _structure()
    assert not structures_equal(base, _structure(temperature_sensor="sensor.other"))
    assert not structures_equal(
        base, dataclasses.replace(base, windows=("binary_sensor.living_window",))
    )
    assert not structures_equal(base, dataclasses.replace(base, mrt="sensor.mrt"))


def test_structures_equal_ignores_tuning() -> None:
    # Only the wiring decides reload-vs-hot-apply: two entries that differ in
    # tuning alone are still the same structure.
    a = ZoneConfig(structure=_structure(), tuning=_tuning(comfort_base=20.0))
    b = ZoneConfig(structure=_structure(), tuning=_tuning(comfort_base=23.0))
    assert a != b
    assert structures_equal(a.structure, b.structure)
