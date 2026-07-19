"""Phase-2 tests for the single config parser in ``runtime.config`` (pure).

Pins ``ZoneConfig.from_entry`` / ``from_mappings`` (+ ``HoldTuning``) to
today's coordinator read semantics, field by field against the phase-2
analysis (2026-07-19): merged-dict precedence (options over data, also for
structural keys — Befund 4), every default and coercion of ``__init__``
Z. 440-572 / ``_read_override_options`` Z. 672-688 / ``async_apply_options``
Z. 1101-1178 (drift-free per Befund 7), the AR-34 category fallback, the
``"auto"``-to-``None`` dynamics mapping (Befund 6) and the AR-34 required-
field failure. No Home Assistant import anywhere (pure suite, py310).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

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
    ConfigEntryLike,
    HoldTuning,
    HotApplyConfig,
    MissingStructuralFieldError,
    ZoneConfig,
    ZoneStructure,
    ZoneTuning,
)


@dataclasses.dataclass(frozen=True)
class _FakeEntry:
    """Pure stand-in that satisfies ``ConfigEntryLike`` structurally.

    Mirrors the real ``ConfigEntry`` shape: ``data``/``options`` are
    read-only mappings (``MappingProxyType``), never plain mutable dicts.
    """

    data: Mapping[str, Any]
    options: Mapping[str, Any]


def _entry(data: dict[str, Any], options: dict[str, Any]) -> _FakeEntry:
    return _FakeEntry(MappingProxyType(data), MappingProxyType(options))


def _data() -> dict[str, Any]:
    """A realistic v2.2 room ``entry.data``: structural + installation keys.

    Deliberately includes the data-owned installation keys (``migration.py``
    STRUCTURAL_KEYS) that ride along in ``entry.data`` — the parser reads
    ``source_policy`` out of the merged mapping for the HDH price fallback.
    """
    return {
        "name": "Wohnzimmer",
        "temp_sensor": "sensor.wohnzimmer_temperatur",
        "actuator": "climate.wohnzimmer_trv",
        "trm_sensor": "sensor.aussen_running_mean",
        "outdoor_sensor": "sensor.aussen_temperatur",
        "humidity_sensor": "sensor.wohnzimmer_feuchte",
        "window_sensor": [
            "binary_sensor.wohnzimmer_fenster",
            "binary_sensor.balkontuer",
        ],
        "weather_entity": "weather.home",
        "irradiance_sensor": "sensor.solar_irradiance",
        "trv_external_temp_input": "number.wohnzimmer_trv_ext_temp",
        # installation keys (data-owned, never options):
        "controls_boiler": True,
        "source_policy": "radiator",
        "design_flow_temp": 55,
        "declared_power": 1200,
    }


def _options() -> dict[str, Any]:
    """A realistic, fully populated ``entry.options`` tuning set."""
    return {
        "override_policy": "timer",
        "override_timer_h": 3,
        "override_max_h": 12,
        "override_end_on_presence_change": False,
        "boost_duration_min": 45,
        "trace_recording": True,
        "presence_home": ["person.alice", "person.bob"],
        "occupancy_sensor": "binary_sensor.wohnzimmer_bewegung",  # legacy str
        "absence_after_min": 45,
        "category": "III",
        "comfort_base": 21.5,
        "annual_heating_kwh": 9000,
        "actuator_dynamics": "fast_air",
        "compressor_guard": "off",
        "compressor_min_off_s": "240",  # stored as str: float() coerces
        "compressor_mode_hold_s": 600,
        "thermal_shock_delta_k": 6,
        "cool_hard_cap_c": 27.5,
        "adaptive_cool": "on",
        "cool_min_outdoor": 18,
        "heat_max_outdoor": 20,
        "heat_lockout_enabled": False,
        "cool_lockout_enabled": True,
        "comfort_weight": 55,
        "setback_delta": 2.5,
        "comfort_start": "06:30",
        "comfort_end": "22:00",
        "optimal_start": False,
        "adopt_external_setpoint": False,
        "adopt_external_mode": False,
        "operative_input": True,
        # Store-owned user intent (AR-04): must be ignored by the parser.
        "climate_mode": "heat",
    }


def _minimal_data() -> dict[str, Any]:
    """Only the three AR-34 required structural fields."""
    return {
        "name": "Bad",
        "temp_sensor": "sensor.bad_temperatur",
        "actuator": "climate.bad_trv",
    }


# ---------------------------------------------------------------------------
# from_entry vs from_mappings (the phase-2 "identical config object" test)
# ---------------------------------------------------------------------------


def test_from_entry_equals_from_mappings() -> None:
    entry = _entry(_data(), _options())
    # Static check: the fake entry satisfies ConfigEntryLike structurally.
    typed: ConfigEntryLike = entry
    assert ZoneConfig.from_entry(typed) == ZoneConfig.from_mappings(
        entry.data, entry.options
    )
    assert HoldTuning.from_entry(typed) == HoldTuning.from_mappings(
        entry.data, entry.options
    )


def test_from_entry_equals_from_mappings_on_minimal_entry() -> None:
    entry = _entry(_minimal_data(), {})
    assert ZoneConfig.from_entry(entry) == ZoneConfig.from_mappings(
        entry.data, entry.options
    )
    assert HoldTuning.from_entry(entry) == HoldTuning.from_mappings(
        entry.data, entry.options
    )


# ---------------------------------------------------------------------------
# realistic full parse
# ---------------------------------------------------------------------------


def test_realistic_structure_parse() -> None:
    structure = ZoneConfig.from_mappings(_data(), _options()).structure
    assert structure == ZoneStructure(
        zone_name="Wohnzimmer",
        temperature_sensor="sensor.wohnzimmer_temperatur",
        actuator="climate.wohnzimmer_trv",
        trm="sensor.aussen_running_mean",
        outdoor="sensor.aussen_temperatur",
        humidity="sensor.wohnzimmer_feuchte",
        mrt=None,  # not configured -> None
        presence_home_entities=("person.alice", "person.bob"),
        # legacy bare string normalises to a one-element tuple:
        occupancy_entities=("binary_sensor.wohnzimmer_bewegung",),
        windows=("binary_sensor.wohnzimmer_fenster", "binary_sensor.balkontuer"),
        weather="weather.home",
        irradiance="sensor.solar_irradiance",
        trv_ext_temp="number.wohnzimmer_trv_ext_temp",
    )


def test_realistic_tuning_parse() -> None:
    tuning = ZoneConfig.from_mappings(_data(), _options()).tuning
    assert tuning.window_auto_cfg == WindowAutoConfig()  # constant, not read
    assert tuning.override_policy == "timer"
    assert tuning.override_cfg == OverrideConfig()  # constant, not read
    assert tuning.trace_enabled is True
    assert tuning.presence_cfg == PresenceConfig(absence_after_min=45.0, eco_delta=2.0)
    assert tuning.category is Category.III
    assert tuning.comfort_base == 21.5
    # explicit price absent + source_policy "radiator" (from DATA, merged
    # read) -> gas fallback 0.11
    assert tuning.hdh_cfg == HdhConfig(annual_kwh=9000.0, price_eur_kwh=0.11)
    assert tuning.dynamics_override is DeviceDynamics.FAST_AIR
    assert tuning.mpc_params == MpcParams()  # per-tick derived, never parsed
    assert tuning.compressor_guard == "off"
    assert tuning.comp_min_off_opt == 240.0  # str "240" -> float
    assert tuning.comp_mode_hold_opt == 600.0
    assert tuning.thermal_shock_delta == 6.0
    assert tuning.cool_hard_cap == 27.5
    assert tuning.adaptive_cool_cfg == "on"  # raw, no coercion
    assert tuning.cool_min_outdoor == 18.0
    assert tuning.heat_max_outdoor == 20.0
    assert tuning.heat_lockout_enabled is False
    assert tuning.cool_lockout_enabled is True
    assert tuning.priority == 0.55  # comfort_weight 55 / 100
    assert tuning.schedule == ComfortSchedule.from_windows(
        [ComfortWindow(6 * 60 + 30, 22 * 60)], 2.5
    )
    assert tuning.optimal_start is False
    assert tuning.optimal_stop is False  # coupled to optimal_start
    assert tuning.adopt_external_setpoint is False
    assert tuning.adopt_external_mode is False
    assert tuning.operative_input is True


def test_realistic_hold_parse() -> None:
    hold = HoldTuning.from_mappings(_data(), _options())
    assert hold == HoldTuning(
        override_timer_h=3.0,
        override_max_h=12.0,
        override_end_on_presence=False,
        boost_duration_min=45.0,
    )


# ---------------------------------------------------------------------------
# defaults (minimal entry: required fields only)
# ---------------------------------------------------------------------------


def test_structure_defaults_on_minimal_entry() -> None:
    structure = ZoneConfig.from_mappings(_minimal_data(), {}).structure
    assert structure == ZoneStructure(
        zone_name="Bad",
        temperature_sensor="sensor.bad_temperatur",
        actuator="climate.bad_trv",
        trm=None,
        outdoor=None,
        humidity=None,
        mrt=None,
        presence_home_entities=(),
        occupancy_entities=(),
        windows=(),
        weather=None,
        irradiance=None,
        trv_ext_temp=None,
    )


def test_tuning_defaults_on_minimal_entry() -> None:
    tuning = ZoneConfig.from_mappings(_minimal_data(), {}).tuning
    assert tuning == ZoneTuning(
        window_auto_cfg=WindowAutoConfig(),
        override_policy="schedule",  # DEFAULT_OVERRIDE_POLICY
        override_cfg=OverrideConfig(),
        trace_enabled=False,  # literal default, no DEFAULT_ constant
        presence_cfg=PresenceConfig(absence_after_min=30.0, eco_delta=2.0),
        category=Category.II,
        comfort_base=21.0,
        hdh_cfg=HdhConfig(annual_kwh=12000.0, price_eur_kwh=0.30),  # electric
        dynamics_override=None,  # DEFAULT_DYNAMICS "auto" -> auto-classify
        mpc_params=MpcParams(),
        compressor_guard="auto",
        comp_min_off_opt=None,  # no get-default
        comp_mode_hold_opt=None,
        thermal_shock_delta=7.0,  # DEFAULT_SHOCK_DELTA_K
        cool_hard_cap=26.0,  # DEFAULT_HARD_CAP_C
        adaptive_cool_cfg="auto",
        cool_min_outdoor=16.0,
        heat_max_outdoor=22.0,
        heat_lockout_enabled=True,
        cool_lockout_enabled=True,
        priority=0.7,  # DEFAULT_COMFORT_WEIGHT 70 / 100
        schedule=ComfortSchedule.always_comfort(),  # no start/end configured
        optimal_start=True,  # literal default
        optimal_stop=True,
        adopt_external_setpoint=True,
        adopt_external_mode=True,
        operative_input=False,  # literal default
    )


def test_hold_defaults_on_minimal_entry() -> None:
    assert HoldTuning.from_mappings(_minimal_data(), {}) == HoldTuning(
        override_timer_h=2.0,
        override_max_h=8.0,
        override_end_on_presence=True,
        boost_duration_min=60.0,
    )


# ---------------------------------------------------------------------------
# merged-dict precedence: options over data (Befund 4: also structural keys)
# ---------------------------------------------------------------------------


def test_options_win_over_data_for_tuning_keys() -> None:
    data = {**_minimal_data(), "comfort_base": 20.0, "override_timer_h": 1.0}
    options = {"comfort_base": 23.5, "override_timer_h": 4.0}
    assert ZoneConfig.from_mappings(data, options).tuning.comfort_base == 23.5
    assert HoldTuning.from_mappings(data, options).override_timer_h == 4.0


def test_options_win_over_data_even_for_structural_keys() -> None:
    # Befund 4: __init__ reads structural fields from the MERGED dict too, so
    # a (hand-edited/legacy) structural key in options shadows data — the
    # parser must reproduce that, not re-interpret "structural = data-only".
    options = {"temp_sensor": "sensor.override_wins"}
    structure = ZoneConfig.from_mappings(_minimal_data(), options).structure
    assert structure.temperature_sensor == "sensor.override_wins"


def test_data_value_used_when_options_silent() -> None:
    data = {**_minimal_data(), "comfort_base": 19.5}
    assert ZoneConfig.from_mappings(data, {}).tuning.comfort_base == 19.5


# ---------------------------------------------------------------------------
# AR-34: required structural fields + category fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["name", "temp_sensor", "actuator"])
def test_missing_required_field_raises(missing: str) -> None:
    data = _minimal_data()
    del data[missing]
    with pytest.raises(MissingStructuralFieldError) as err:
        ZoneConfig.from_mappings(data, {})
    assert err.value.key == missing
    assert f"'{missing}'" in str(err.value)


@pytest.mark.parametrize("bad", ["", 42, None, ["sensor.x"]])
def test_empty_or_non_string_required_field_raises(bad: Any) -> None:
    data = {**_minimal_data(), "temp_sensor": bad}
    with pytest.raises(MissingStructuralFieldError) as err:
        ZoneConfig.from_mappings(data, {})
    assert err.value.key == "temp_sensor"


def test_required_field_error_order_matches_init() -> None:
    # __init__ requires name (Z. 440) before temp (446) before actuator
    # (447) — an all-empty entry must report "name" first, like today.
    with pytest.raises(MissingStructuralFieldError) as err:
        ZoneConfig.from_mappings({}, {})
    assert err.value.key == "name"


def test_corrupt_category_falls_back_to_norm_default() -> None:
    # F11/AR-34: identical guard on both paths — never throws, falls back II.
    options = {"category": "banana"}
    tuning = ZoneConfig.from_mappings(_minimal_data(), options).tuning
    assert tuning.category is Category.II


def test_valid_category_parses() -> None:
    options = {"category": "I"}
    tuning = ZoneConfig.from_mappings(_minimal_data(), options).tuning
    assert tuning.category is Category.I


def test_corrupt_numeric_value_raises_like_today() -> None:
    # Both paths coerce with float(...) and let a corrupt value throw
    # (__init__ fails setup; the parser raises the same error, atomically —
    # see the Befund-3 note in ZoneConfig.from_mappings).
    with pytest.raises(ValueError):
        ZoneConfig.from_mappings(_minimal_data(), {"comfort_base": "warm"})
    with pytest.raises(ValueError):
        HoldTuning.from_mappings(_minimal_data(), {"override_max_h": "long"})


# ---------------------------------------------------------------------------
# dynamics override mapping (Befund 6: "auto"/unknown/empty -> None)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["auto", "", None, "warp_speed"])
def test_dynamics_auto_unknown_or_empty_maps_to_none(raw: Any) -> None:
    options = {"actuator_dynamics": raw}
    tuning = ZoneConfig.from_mappings(_minimal_data(), options).tuning
    assert tuning.dynamics_override is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("fast_air", DeviceDynamics.FAST_AIR),
        ("slow_hydronic", DeviceDynamics.SLOW_HYDRONIC),
        ("very_slow", DeviceDynamics.VERY_SLOW),
    ],
)
def test_dynamics_valid_value_pins_profile(raw: str, expected: DeviceDynamics) -> None:
    options = {"actuator_dynamics": raw}
    tuning = ZoneConfig.from_mappings(_minimal_data(), options).tuning
    assert tuning.dynamics_override is expected


# ---------------------------------------------------------------------------
# entity-list normalisation (as_entity_list semantics, tuple-typed)
# ---------------------------------------------------------------------------


def test_entity_lists_normalise_exactly_like_as_entity_list() -> None:
    data = {
        **_minimal_data(),
        "window_sensor": "binary_sensor.single",  # bare str -> 1-tuple
        "presence_home": [None, "", "person.a", 5],  # truthy filter + str()
        "occupancy_sensor": 123,  # non list/str garbage -> empty
    }
    structure = ZoneConfig.from_mappings(data, {}).structure
    assert structure.windows == ("binary_sensor.single",)
    assert structure.presence_home_entities == ("person.a", "5")
    assert structure.occupancy_entities == ()


# ---------------------------------------------------------------------------
# schedule guard (identical on both paths, including the error path)
# ---------------------------------------------------------------------------


def test_schedule_built_only_with_start_end_and_positive_delta() -> None:
    base = {"comfort_start": "06:30", "comfort_end": "22:00", "setback_delta": 2.0}
    tuning = ZoneConfig.from_mappings(_minimal_data(), dict(base)).tuning
    assert tuning.schedule == ComfortSchedule.from_windows(
        [ComfortWindow(390, 1320)], 2.0
    )
    for degraded in (
        {**base, "comfort_end": None},  # missing end
        {**base, "setback_delta": 0.0},  # zero depth
        {**base, "comfort_start": "25:99"},  # out of range -> parse None
        {**base, "comfort_start": "6"},  # no colon -> parse None
    ):
        tuning = ZoneConfig.from_mappings(_minimal_data(), degraded).tuning
        assert tuning.schedule == ComfortSchedule.always_comfort()


# ---------------------------------------------------------------------------
# HDH price fallback (report_price_eur_kwh wiring)
# ---------------------------------------------------------------------------


def test_hdh_explicit_price_wins_even_zero_or_string() -> None:
    tuning = ZoneConfig.from_mappings(
        {**_minimal_data(), "source_policy": "radiator"},
        {"price_eur_kwh": "0.25"},
    ).tuning
    assert tuning.hdh_cfg.price_eur_kwh == 0.25
    tuning = ZoneConfig.from_mappings(
        {**_minimal_data(), "source_policy": "radiator"}, {"price_eur_kwh": 0}
    ).tuning
    assert tuning.hdh_cfg.price_eur_kwh == 0.0  # explicit 0 is not "absent"


def test_hdh_source_policy_fallback_gas_vs_electric() -> None:
    # strip/lower on the source string, exactly report_price_eur_kwh:
    tuning = ZoneConfig.from_mappings(
        {**_minimal_data(), "source_policy": "  Radiator "}, {}
    ).tuning
    assert tuning.hdh_cfg.price_eur_kwh == 0.11
    tuning = ZoneConfig.from_mappings(
        {**_minimal_data(), "source_policy": "heat_pump"}, {}
    ).tuning
    assert tuning.hdh_cfg.price_eur_kwh == 0.30


# ---------------------------------------------------------------------------
# transform fidelity (exact coercions of today's reads)
# ---------------------------------------------------------------------------


def test_bool_transform_is_pythons_bool_exactly() -> None:
    # bool(...) like today — a non-empty string is truthy, whatever it says.
    options = {"trace_recording": "false", "operative_input": 0}
    tuning = ZoneConfig.from_mappings(_minimal_data(), options).tuning
    assert tuning.trace_enabled is True
    assert tuning.operative_input is False


def test_optimal_stop_stays_coupled_to_optimal_start() -> None:
    on = ZoneConfig.from_mappings(_minimal_data(), {"optimal_start": 1}).tuning
    off = ZoneConfig.from_mappings(_minimal_data(), {"optimal_start": ""}).tuning
    assert (on.optimal_start, on.optimal_stop) == (True, True)
    assert (off.optimal_start, off.optimal_stop) == (False, False)


def test_numeric_strings_coerce_via_float() -> None:
    options = {"comfort_base": "21.5", "comfort_weight": "55"}
    tuning = ZoneConfig.from_mappings(_minimal_data(), options).tuning
    assert tuning.comfort_base == 21.5
    assert tuning.priority == 0.55


# ---------------------------------------------------------------------------
# climate_mode stays unparsed (AR-04, store-owned user intent)
# ---------------------------------------------------------------------------


def test_climate_mode_is_not_parsed_anywhere() -> None:
    # No parsed structure may ever grow a climate_mode field (plan phase 2:
    # store-owned -> UserControlState), and a stored value must not leak
    # into the parse result in any other way.
    for cls in (ZoneStructure, ZoneTuning, HoldTuning, ZoneConfig):
        assert "climate_mode" not in {f.name for f in dataclasses.fields(cls)}
    with_mode = ZoneConfig.from_mappings(_minimal_data(), {"climate_mode": "cool"})
    without_mode = ZoneConfig.from_mappings(_minimal_data(), {})
    assert with_mode == without_mode


# ---------------------------------------------------------------------------
# HotApplyConfig — the hot-apply-path parse (baseline async_apply_options
# Z. 1101-1178: hold before tuning, NO structural reads)
# ---------------------------------------------------------------------------


def test_hot_apply_from_entry_equals_from_mappings() -> None:
    entry = _entry(_data(), _options())
    typed: ConfigEntryLike = entry
    assert HotApplyConfig.from_entry(typed) == HotApplyConfig.from_mappings(
        entry.data, entry.options
    )


def test_hot_apply_equals_setup_path_bundle() -> None:
    # Both wiring paths must feed _apply_hot_tuning the identical shape:
    # __init__ bundles its already parsed pieces via from_zone_config, the
    # options path parses directly — same entry, same HotApplyConfig.
    data, options = _data(), _options()
    cfg = ZoneConfig.from_mappings(data, options)
    hold = HoldTuning.from_mappings(data, options)
    assert HotApplyConfig.from_mappings(data, options) == (
        HotApplyConfig.from_zone_config(cfg, hold)
    )


def test_hot_apply_never_reads_structural_keys() -> None:
    # The baseline hot-apply ran no _require (Z. 1101-1178): a merged mapping
    # missing name/temp_sensor/actuator (legacy entry with the key only in
    # options, dropped by an options submit) must parse cleanly — never raise
    # MissingStructuralFieldError — and yield the identical tuning/hold as a
    # structurally complete entry with the same tuning keys.
    options = _options()
    hot = HotApplyConfig.from_mappings({}, options)
    assert hot.tuning == ZoneConfig.from_mappings(_minimal_data(), options).tuning
    assert hot.hold == HoldTuning.from_mappings(_minimal_data(), options)
    # …including the two options-owned entity lists (Befund 8):
    assert hot.presence_home_entities == ("person.alice", "person.bob")
    assert hot.occupancy_entities == ("binary_sensor.wohnzimmer_bewegung",)


def test_hot_apply_corrupt_hold_value_throws_before_tuning() -> None:
    # Baseline apply order: _read_override_options first (Z. 1102) — with a
    # corrupt hold float AND a corrupt tuning float in the same submit, the
    # hold value names the ValueError, exactly like today.
    options = {"override_timer_h": "bad hold", "comfort_base": "bad tuning"}
    with pytest.raises(ValueError, match="bad hold"):
        HotApplyConfig.from_mappings(_minimal_data(), options)


# ---------------------------------------------------------------------------
# never-parsed constants (analysis "skipped" (d) + Befund 6)
# ---------------------------------------------------------------------------


def test_constant_sub_configs_are_default_constructed() -> None:
    tuning = ZoneConfig.from_mappings(_data(), _options()).tuning
    # Never config-read: window-auto thresholds, preset offsets, MPC params.
    assert tuning.window_auto_cfg == WindowAutoConfig()
    assert tuning.override_cfg == OverrideConfig()
    assert tuning.mpc_params == MpcParams()
    # The presence eco delta is wired to the constant eco offset (Z. 464),
    # even when the absence timing itself is configured.
    assert tuning.presence_cfg.eco_delta == OverrideConfig().eco_offset
