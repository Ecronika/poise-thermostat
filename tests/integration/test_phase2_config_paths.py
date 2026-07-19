"""Phase 2 — both coordinator config paths ride the ONE parser (glue, CI-only).

Pins the phase-2 rewiring of ``coordinator.py`` onto ``runtime.config``:

* (a) the setup path (``__init__``) and the hot-apply path
  (``async_apply_options``) fill the identical hot-applyable tuning for the
  same entry — the "identisches Config-Objekt aus beiden Pfaden" test of the
  refactoring plan (section 6, phase 2);
* (b) a hot-apply changes tuning but never the structural wiring, never
  ``climate_mode`` (AR-04, store-owned) and never the adopt-external toggles
  (init-only today — pre-existing path drift, phase-2 analysis Befunde 1+2,
  deliberately preserved), while the options-owned presence lists DO
  hot-apply (Befund 8);
* (c) a store-restored ``climate_mode`` survives an options submit (today's
  semantics: the options form value must not clobber the live selection);
* (d) ``structural_unchanged`` (F14) keeps its data-dict predicate: an
  options-only change reads unchanged (hot-apply runs), a data change reads
  structural (hot-apply skipped on the coordinator the reload will discard);
* (e) the hot-apply reads NO structural key (baseline equivalence): a legacy
  entry holding a structural key only in ``options`` (Befund 4) survives an
  options submit that drops the key — the tuning still applies, nothing
  raises into the update listener;
* (f) the deliberate phase-2 error-path change (Befund 3): a corrupt tuning
  value fails the WHOLE hot-apply atomically — every attribute keeps its
  pre-value, no refresh — instead of the baseline's mid-sequence tearing.

The field-by-field parser fidelity itself is pinned by the pure suite
(``tests/test_phase2_config_parser.py``); this module pins the wiring.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_ADOPT_EXTERNAL_SETPOINT,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_DYNAMICS,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_PRESENCE_HOME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)
from custom_components.poise.runtime.config import HoldTuning, ZoneConfig
from custom_components.poise.storage import STORAGE_VERSION

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

# A broad, realistic tuning set covering every hot-apply group (hold timing,
# comfort, HDH, dynamics, compressor guard, presence, shock/cool caps,
# lockouts, weight, schedule, optimal start). Raw option keys, exactly as the
# options flow stores them.
FULL_OPTIONS: dict[str, Any] = {
    "override_policy": "timer",
    "override_timer_h": 3,
    "override_max_h": 12,
    "override_end_on_presence_change": False,
    "boost_duration_min": 45,
    "presence_home": ["person.alice"],
    "occupancy_sensor": "binary_sensor.motion",  # legacy bare str form
    "absence_after_min": 45,
    "category": "III",
    "comfort_base": 21.5,
    "annual_heating_kwh": 9000,
    "actuator_dynamics": "fast_air",
    "compressor_guard": "off",
    "compressor_min_off_s": 240,
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
    "operative_input": False,
}


def _set_states(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "18.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 19.0,
            "current_temperature": 18.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(
    hass: HomeAssistant,
    *,
    options: dict[str, Any] | None = None,
    entry_id: str | None = None,
) -> MockConfigEntry:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_states(hass)
    kwargs: dict[str, Any] = {}
    if entry_id is not None:
        kwargs["entry_id"] = entry_id
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=dict(ROOM_DATA),
        options=dict(options or {}),
        title="Test Room",
        **kwargs,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _hot_tuning_attrs(coord: Any) -> dict[str, Any]:
    """Every attribute ``_apply_hot_tuning`` fills, keyed by parser field."""
    return {
        "override_policy": coord._override_policy,
        "override_timer_h": coord._override_timer_h,
        "override_max_h": coord._override_max_h,
        "override_end_on_presence": coord._override_end_on_presence,
        "boost_duration_min": coord._boost_duration_min,
        "comfort_base": coord._comfort_base,
        "hdh_cfg": coord._hdh_cfg,
        "dynamics_override": coord._dynamics_override,
        "compressor_guard": coord._compressor_guard,
        "comp_min_off_opt": coord._comp_min_off_opt,
        "comp_mode_hold_opt": coord._comp_mode_hold_opt,
        "trace_enabled": coord._trace_enabled,
        "presence_home_entities": list(coord._presence_home_entities),
        "occupancy_entities": list(coord._occupancy_entities),
        "presence_cfg": coord._presence_cfg,
        "thermal_shock_delta": coord._thermal_shock_delta,
        "cool_hard_cap": coord._cool_hard_cap,
        "adaptive_cool_cfg": coord._adaptive_cool_cfg,
        "category": coord._category,
        "cool_min_outdoor": coord._cool_min_outdoor,
        "heat_max_outdoor": coord._heat_max_outdoor,
        "heat_lockout_enabled": coord._heat_lockout_enabled,
        "cool_lockout_enabled": coord._cool_lockout_enabled,
        "priority": coord._priority,
        "schedule": coord._schedule,
        "optimal_start": coord._optimal_start,
        "optimal_stop": coord._optimal_stop,
        "operative_input": coord._operative_input,
    }


def _expected_from_parser(entry: MockConfigEntry) -> dict[str, Any]:
    """The same mapping, built straight from the shared parser."""
    cfg = ZoneConfig.from_entry(entry)
    hold = HoldTuning.from_entry(entry)
    t = cfg.tuning
    return {
        "override_policy": t.override_policy,
        "override_timer_h": hold.override_timer_h,
        "override_max_h": hold.override_max_h,
        "override_end_on_presence": hold.override_end_on_presence,
        "boost_duration_min": hold.boost_duration_min,
        "comfort_base": t.comfort_base,
        "hdh_cfg": t.hdh_cfg,
        "dynamics_override": t.dynamics_override,
        "compressor_guard": t.compressor_guard,
        "comp_min_off_opt": t.comp_min_off_opt,
        "comp_mode_hold_opt": t.comp_mode_hold_opt,
        "trace_enabled": t.trace_enabled,
        "presence_home_entities": list(cfg.structure.presence_home_entities),
        "occupancy_entities": list(cfg.structure.occupancy_entities),
        "presence_cfg": t.presence_cfg,
        "thermal_shock_delta": t.thermal_shock_delta,
        "cool_hard_cap": t.cool_hard_cap,
        "adaptive_cool_cfg": t.adaptive_cool_cfg,
        "category": t.category,
        "cool_min_outdoor": t.cool_min_outdoor,
        "heat_max_outdoor": t.heat_max_outdoor,
        "heat_lockout_enabled": t.heat_lockout_enabled,
        "cool_lockout_enabled": t.cool_lockout_enabled,
        "priority": t.priority,
        "schedule": t.schedule,
        "optimal_start": t.optimal_start,
        "optimal_stop": t.optimal_stop,
        "operative_input": t.operative_input,
    }


async def test_setup_and_hot_apply_fill_identical_config(
    hass: HomeAssistant,
) -> None:
    """(a) Both paths produce the identical config for the same entry.

    The setup path must equal the parser output field by field; scrambling a
    few live values and hot-applying the SAME entry must restore exactly the
    setup-path values — proving ``async_apply_options`` runs the identical
    parse + apply, not a diverging re-read.
    """
    entry = await _setup(hass, options=dict(FULL_OPTIONS))
    coord: Any = entry.runtime_data

    expected = _expected_from_parser(entry)
    assert _hot_tuning_attrs(coord) == expected  # init path == parser

    # The structural wiring of the init path comes from the same parse too.
    structure = ZoneConfig.from_entry(entry).structure
    assert coord.zone_name == structure.zone_name
    assert coord._temp == structure.temperature_sensor
    assert coord._actuator == structure.actuator
    assert coord._windows == list(structure.windows)

    # Scramble hot-applyable values, then hot-apply the unchanged entry.
    coord._comfort_base = -99.0
    coord._override_timer_h = -1.0
    coord._presence_home_entities = []
    coord._priority = 0.0
    await coord.async_apply_options(entry)
    await hass.async_block_till_done()

    assert _hot_tuning_attrs(coord) == expected  # hot-apply path == parser


async def test_hot_apply_changes_tuning_but_not_structure_or_climate_mode(
    hass: HomeAssistant,
) -> None:
    """(b) Options submit hot-applies tuning only.

    Structure (even a structural key smuggled into options), ``climate_mode``
    (AR-04) and the adopt-external toggles (Befunde 1+2) stay untouched; the
    options-owned presence lists do hot-apply (Befund 8).
    """
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    assert coord._comfort_base == 21.0
    assert coord._climate_mode == "auto"
    assert coord._adopt_external_setpoint is True

    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_COMFORT_BASE: 23.5,
            CONF_DYNAMICS: "very_slow",
            CONF_PRESENCE_HOME: ["person.alice"],
            # must all be ignored by the hot-apply:
            CONF_CLIMATE_MODE: "heat",  # store-owned (AR-04)
            CONF_TEMP_SENSOR: "sensor.sneaky",  # structural — reload-only
            CONF_ADOPT_EXTERNAL_SETPOINT: False,  # init-only (Befund 1)
        },
    )
    await hass.async_block_till_done()

    # tuning applied…
    assert coord._comfort_base == 23.5
    assert coord._dynamics_override is not None
    assert coord._presence_home_entities == ["person.alice"]
    # …structure, climate_mode and the adopt toggle untouched:
    assert coord._temp == "sensor.room_temp"
    assert coord.zone_name == "Test Room"
    assert coord._climate_mode == "auto"
    assert coord._adopt_external_setpoint is True


async def test_store_restored_climate_mode_survives_options_update(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """(c) The store-restored ``climate_mode`` outlives an options submit.

    The ``ekf`` key gates the whole restore (``async_bootstrap`` reads the
    payload only when it is present); the entry value says "auto", the store
    says "cool" — and a later options submit carrying "heat" must not clobber
    the restored live selection (today's AR-04 semantics).
    """
    entry_id = "phase2cfg"
    hass_storage[f"{DOMAIN}_{entry_id}_ekf"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}_{entry_id}_ekf",
        "data": {"ekf": {}, "enabled": True, "climate_mode": "cool"},
    }
    entry = await _setup(hass, entry_id=entry_id)
    coord: Any = entry.runtime_data
    assert coord._climate_mode == "cool"  # restored over the entry's "auto"

    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_COMFORT_BASE: 22.0,
            CONF_CLIMATE_MODE: "heat",
        },
    )
    await hass.async_block_till_done()

    assert coord._comfort_base == 22.0  # the hot-apply DID run
    assert coord._climate_mode == "cool"  # …and left the store-owned value


async def test_structural_unchanged_options_vs_data_change(
    hass: HomeAssistant,
) -> None:
    """(d) F14 predicate: options-only -> True (hot-apply), data -> False.

    On a data change the update listener must skip the in-place hot-apply on
    the coordinator the reload is about to discard — pinned here by pairing
    the data change with an options change that must NOT get applied.
    """
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    assert coord.structural_unchanged(entry) is True

    # options-only change: still structurally unchanged, hot-apply runs.
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_COMFORT_BASE: 23.0}
    )
    await hass.async_block_till_done()
    assert coord.structural_unchanged(entry) is True
    assert coord._comfort_base == 23.0

    # data change: structural — the listener must skip the hot-apply, so the
    # simultaneous options change stays unapplied on this coordinator.
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_TEMP_SENSOR: "sensor.other_temp"},
        options={**entry.options, CONF_COMFORT_BASE: 25.0},
    )
    await hass.async_block_till_done()
    assert coord.structural_unchanged(entry) is False
    assert coord._comfort_base == 23.0  # hot-apply skipped (F14)


async def test_hot_apply_survives_structural_key_only_in_options(
    hass: HomeAssistant,
) -> None:
    """(e) The hot-apply never reads structural keys (baseline equivalence).

    A legacy/hand-edited entry may hold a structural key only in
    ``entry.options`` (options-over-data also for structural keys, Befund 4).
    An options-flow submit REPLACES options and drops that key while
    ``entry.data`` stays unchanged — so ``structural_unchanged`` is True and
    the hot-apply runs on a merged mapping missing the key. The baseline
    applied the tuning and carried on (it read no structural keys there);
    the parser wiring must do the same, not raise
    ``MissingStructuralFieldError`` into the update listener.
    """
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_states(hass)
    data = dict(ROOM_DATA)
    legacy_name = data.pop(CONF_NAME)  # structural key lives ONLY in options
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=data,
        options={CONF_NAME: legacy_name},
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord: Any = entry.runtime_data
    assert coord.zone_name == "Test Room"  # merged read seeded the structure

    # The submit drops CONF_NAME from options; data is untouched.
    hass.config_entries.async_update_entry(entry, options={CONF_COMFORT_BASE: 24.0})
    await hass.async_block_till_done()

    assert coord.structural_unchanged(entry) is True  # the hot-apply DID run
    assert coord._comfort_base == 24.0  # …and applied the tuning
    assert coord.zone_name == "Test Room"  # structure untouched, no crash


async def test_corrupt_option_fails_hot_apply_atomically(
    hass: HomeAssistant,
) -> None:
    """(f) Deliberate phase-2 error-path change (Befund 3, plan status box).

    The parse is atomic: one corrupt tuning value fails the WHOLE hot-apply
    up front — every tuning attribute keeps its pre-value and no refresh is
    requested. (The baseline instead applied every field before the throwing
    line and left the rest old, also without a refresh; ``comfort_weight``
    is deliberately a LATE baseline field, so this pins the new atomicity.)
    """
    entry = await _setup(hass, options=dict(FULL_OPTIONS))
    coord: Any = entry.runtime_data
    before = _hot_tuning_attrs(coord)

    refreshes: list[None] = []

    async def _fake_refresh() -> None:
        refreshes.append(None)

    coord.async_request_refresh = _fake_refresh
    corrupt = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv-corrupt",
        data=dict(entry.data),
        options={**FULL_OPTIONS, CONF_COMFORT_WEIGHT: "not-a-number"},
        title="Test Room",
    )  # a bare data/options container; never added to hass
    with pytest.raises(ValueError, match="not-a-number"):
        await coord.async_apply_options(corrupt)

    assert _hot_tuning_attrs(coord) == before  # NOTHING was applied
    assert refreshes == []  # …and no refresh was requested
