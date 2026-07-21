"""Parsed zone configuration contracts + the single config parser.

``ZoneConfig`` is the typed shape of one zone entry, split along the
reload-vs-hot-apply boundary the coordinator enforces:

* ``ZoneStructure`` — the entity wiring (structural ``entry.data``): which
  sensors and which actuator make up the zone. A structural change means the
  entry reloads and the running coordinator is discarded, so options must
  never hot-apply onto it.
* ``ZoneTuning`` — hot-applyable tuning (``entry.options`` over
  ``entry.data``): comfort, schedule, override and guard parameters that
  ``async_apply_options`` may swap on a live coordinator.
* ``HoldTuning`` — the ADR-0059 §1/§2 hold/Boost timing that has no
  ``ZoneTuning`` slot; parsed by the same parser as a sibling structure.

Deliberately absent: ``climate_mode``. It is store-owned user intent (the
user flips it at runtime and it must survive restarts), not configuration —
it belongs to ``UserControlState``.

``ZoneConfig.from_entry`` / ``from_mappings`` (plus ``HoldTuning.from_entry``
/ ``from_mappings``) are the single parser feeding both ``__init__`` and
``async_apply_options``, with no value drift between the two paths.
``HotApplyConfig`` is the hot-apply-path view of that parse: it reads NO
structural key (``async_apply_options`` never did), so an options submit can
never raise ``MissingStructuralFieldError``. The module stays pure:
``ConfigEntryLike`` is a structural stand-in for
``homeassistant.config_entries.ConfigEntry``, so ``from_entry(entry)`` is
type-safe without any Home Assistant import. Option defaults keep living in
``const.py`` (or the owning pure module) and are resolved only by the parser —
never by dataclass defaults here, so there is exactly one place a default can
drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ..comfort.en16798 import Category
from ..comfort.presence import PresenceConfig
from ..comfort.schedule import ComfortSchedule, ComfortWindow, parse_hhmm
from ..comfort.thermal_shock import DEFAULT_HARD_CAP_C, DEFAULT_SHOCK_DELTA_K
from ..const import (
    COMPRESSOR_GUARD_AUTO,
    CONF_ABSENCE_AFTER_MIN,
    CONF_ACTUATOR,
    CONF_ADAPTIVE_COOL,
    CONF_ADOPT_EXTERNAL_MODE,
    CONF_ADOPT_EXTERNAL_SETPOINT,
    CONF_ANNUAL_KWH,
    CONF_BOOST_DURATION_MIN,
    CONF_CATEGORY,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_COMPRESSOR_GUARD,
    CONF_COMPRESSOR_MIN_OFF,
    CONF_COMPRESSOR_MODE_HOLD,
    CONF_COOL_HARD_CAP,
    CONF_COOL_LOCKOUT_ENABLED,
    CONF_COOL_MIN_OUTDOOR,
    CONF_DYNAMICS,
    CONF_HEAT_LOCKOUT_ENABLED,
    CONF_HEAT_MAX_OUTDOOR,
    CONF_HUMIDITY_SENSOR,
    CONF_IRRADIANCE,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_OVERRIDE_END_ON_PRESENCE,
    CONF_OVERRIDE_MAX_H,
    CONF_OVERRIDE_POLICY,
    CONF_OVERRIDE_TIMER_H,
    CONF_PRESENCE_HOME,
    CONF_PRICE_EUR_KWH,
    CONF_SETBACK_DELTA,
    CONF_SOURCE_POLICY,
    CONF_TEMP_SENSOR,
    CONF_THERMAL_SHOCK_DELTA,
    CONF_TRACE_RECORDING,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    DEFAULT_ABSENCE_AFTER_MIN,
    DEFAULT_ADAPTIVE_COOL,
    DEFAULT_ADOPT_EXTERNAL_MODE,
    DEFAULT_ADOPT_EXTERNAL_SETPOINT,
    DEFAULT_ANNUAL_KWH,
    DEFAULT_BOOST_DURATION_MIN,
    DEFAULT_COMFORT_BASE,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_COOL_LOCKOUT_ENABLED,
    DEFAULT_COOL_MIN_OUTDOOR_C,
    DEFAULT_DYNAMICS,
    DEFAULT_HEAT_LOCKOUT_ENABLED,
    DEFAULT_HEAT_MAX_OUTDOOR_C,
    DEFAULT_OVERRIDE_END_ON_PRESENCE,
    DEFAULT_OVERRIDE_MAX_H,
    DEFAULT_OVERRIDE_POLICY,
    DEFAULT_OVERRIDE_TIMER_H,
    DEFAULT_PRICE_EUR_KWH,
    DEFAULT_PRICE_GAS_EUR_KWH,
    DEFAULT_SETBACK_DELTA,
)
from ..control.dynamics import DeviceDynamics
from ..control.hdh_savings import HdhConfig, report_price_eur_kwh
from ..control.mpc import MpcParams
from ..control.override import OverrideConfig
from ..control.window_auto import WindowAutoConfig
from ..migration import as_entity_list


class ConfigEntryLike(Protocol):
    """The two mappings the parser needs from a config entry (pure stand-in).

    ``homeassistant.config_entries.ConfigEntry`` satisfies this structurally
    (``data``/``options`` are read-only mapping properties there), so
    ``from_entry(entry)`` stays type-safe while this module keeps its pure
    gate (no ``homeassistant`` import).
    """

    @property
    def data(self) -> Mapping[str, Any]: ...

    @property
    def options(self) -> Mapping[str, Any]: ...


class MissingStructuralFieldError(Exception):
    """A required structural field is missing, empty or not a string.

    Pure stand-in for ``homeassistant.exceptions.ConfigEntryError`` (this
    module cannot import HA): the coordinator wiring catches it and re-raises
    ``ConfigEntryError`` with the exact message — prefixed with the entry id
    only the coordinator knows — so a corrupt entry still fails setup cleanly
    (SETUP_ERROR + repair flow), never as an uncaught ``KeyError``.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"missing the required '{key}' setting; reconfigure the zone")
        self.key = key


def _merged(data: Mapping[str, Any], options: Mapping[str, Any]) -> dict[str, Any]:
    """Options-over-data merge, exactly ``{**entry.data, **entry.options}``.

    Read semantics on BOTH paths: options win — also for structural keys — so
    a hand-edited/legacy entry with structural keys in ``options`` keeps
    behaving options-over-data.
    """
    return {**data, **options}


def _require(merged: Mapping[str, Any], key: str) -> str:
    # A corrupt entry missing a structural field must fail setup cleanly, not
    # crash — missing, non-str or empty all reject.
    val = merged.get(key)
    if not isinstance(val, str) or not val:
        raise MissingStructuralFieldError(key)
    return val


def _float_or_none(raw: Any) -> float | None:
    # The compressor timers have no get-default: absent stays None, anything
    # else coerces — identical on both paths.
    return float(raw) if raw is not None else None


def _parse_dynamics_override(raw: Any) -> DeviceDynamics | None:
    """Map the raw ``actuator_dynamics`` option onto the typed profile.

    Mirrors ``classify_dynamics``'s override handling exactly (ADR-0052):
    falsy (``""``/``None``) or unknown values — including the stored default
    ``"auto"`` — fall through to auto-detection, i.e. ``None`` here; a valid
    ``DeviceDynamics`` value pins the profile. The per-tick derivation of
    ``_dynamics``/``_mpc_params``/PI profile stays in the coordinator —
    deliberately NOT done at parse time.
    """
    if not raw:
        return None
    try:
        return DeviceDynamics(raw)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ZoneStructure:
    """Entity wiring of one zone (the structural ``entry.data`` reads).

    Entity-list fields are tuples (immutable, so the snapshot can never be
    mutated behind the runtime's back) instead of lists; optional single
    entities are ``None`` when not configured.
    """

    zone_name: str
    temperature_sensor: str  # required: the room sensor (setup gate)
    actuator: str  # required: the single-writer target (setup gate)
    trm: str | None  # running-mean outdoor sensor (EN 16798-1 t_rm)
    outdoor: str | None
    humidity: str | None
    mrt: str | None  # mean-radiant sensor for operative temperature
    presence_home_entities: tuple[str, ...]  # ADR-0058: OR-reduced house gate
    occupancy_entities: tuple[str, ...]  # ADR-0058: OR-reduced room occupancy
    windows: tuple[str, ...]
    weather: str | None  # forecast source for optimal start (ADR-0025)
    irradiance: str | None
    trv_ext_temp: str | None  # TRV external-temperature feed (ADR-0029)

    @classmethod
    def from_merged(cls, merged: Mapping[str, Any]) -> ZoneStructure:
        """Parse the wiring from the MERGED mapping (options over data).

        Deliberately *not* ``from_data``: ``__init__`` reads even the
        structural fields from ``{**entry.data, **entry.options}``, so the
        parser must too. The three ``_require`` reads keep the name/temp/
        actuator order, so the first missing key reported stays the same.
        """
        return cls(
            zone_name=_require(merged, CONF_NAME),
            temperature_sensor=_require(merged, CONF_TEMP_SENSOR),
            actuator=_require(merged, CONF_ACTUATOR),
            trm=merged.get(CONF_TRM_SENSOR),
            outdoor=merged.get(CONF_OUTDOOR_SENSOR),
            humidity=merged.get(CONF_HUMIDITY_SENSOR),
            mrt=merged.get(CONF_MRT_SENSOR),
            presence_home_entities=tuple(
                as_entity_list(merged.get(CONF_PRESENCE_HOME))
            ),
            occupancy_entities=tuple(as_entity_list(merged.get(CONF_OCCUPANCY_SENSOR))),
            windows=tuple(as_entity_list(merged.get(CONF_WINDOW_SENSOR))),
            weather=merged.get(CONF_WEATHER),
            irradiance=merged.get(CONF_IRRADIANCE),
            trv_ext_temp=merged.get(CONF_TRV_EXTERNAL_TEMP),
        )


@dataclass(frozen=True, slots=True)
class ZoneTuning:
    """Hot-applyable tuning of one zone — everything ``async_apply_options``
    may change without a reload.

    Field names are the coordinator attributes minus the leading underscore;
    the two non-trivial typings:

    * ``dynamics_override`` — typed as ``DeviceDynamics | None`` instead of a
      raw option string: ``None`` means auto-classify from the actuator's
      capabilities, exactly the ``classify_dynamics`` semantics where
      ``"auto"`` / any unknown string falls through to detection (ADR-0052).
    * ``adaptive_cool_cfg`` — the stored value is the tri-state selector
      string (``"auto"`` / ``"on"`` / ``"off"``) but legacy entries hold a
      boolean; ``adaptive_cool_mode`` normalises at the use site (ADR-0008).

    No ``climate_mode`` field by design: it is store-owned user intent, not
    configuration (``UserControlState``).
    """

    window_auto_cfg: WindowAutoConfig  # ADR-0041 slope-based window detection
    override_policy: str  # ADR-0059 §1 hold-expiry policy (timer/schedule/…)
    override_cfg: OverrideConfig  # ADR-0042 preset offsets + revert window
    trace_enabled: bool  # ADR-0011 opt-in golden-file trace recorder
    presence_cfg: PresenceConfig  # ADR-0058 absence timing + eco delta
    category: Category  # EN 16798-1 comfort category
    comfort_base: float  # user comfort base [degC]
    hdh_cfg: HdhConfig  # ADR-0045 savings-report inputs
    dynamics_override: DeviceDynamics | None  # None = auto-classify (ADR-0052)
    mpc_params: MpcParams
    compressor_guard: str  # ADR-0046 §8 kill switch (auto/on/off)
    comp_min_off_opt: float | None  # per-zone min-off override [s]; None = profile
    comp_mode_hold_opt: float | None  # per-zone mode-hold override [s]
    thermal_shock_delta: float  # ADR-0051 max cooling raise per step [K]
    cool_hard_cap: float  # ADR-0051 absolute cooling-setpoint cap [degC]
    adaptive_cool_cfg: str | bool  # tri-state selector; legacy bool (ADR-0008)
    cool_min_outdoor: float  # cooling lockout below this outdoor [degC]
    heat_max_outdoor: float  # heating lockout above this outdoor [degC]
    heat_lockout_enabled: bool
    cool_lockout_enabled: bool
    priority: float  # comfort weight / 100 -> [0, 1]
    schedule: ComfortSchedule  # ADR-0025 comfort windows + setback depth
    optimal_start: bool
    # Coasts to the lower comfort edge before window end; deliberately coupled
    # to optimal_start (predictive scheduling), splittable later.
    optimal_stop: bool
    adopt_external_setpoint: bool  # TRV wheel -> manual hold
    adopt_external_mode: bool  # IR remote -> manual mode-hold
    operative_input: bool  # ADR-0029 operative-temperature input mode

    @classmethod
    def from_merged(cls, merged: Mapping[str, Any]) -> ZoneTuning:
        """Parse the tuning from the MERGED mapping (options over data).

        Every default and coercion below is identical on both paths where both
        paths read the field. Notable exactness:

        * ``window_auto_cfg``/``override_cfg``/``mpc_params`` are default-
          constructed constants, never config-read — the per-tick derivation
          of dynamics/PI/MPC stays in the coordinator.
        * ``adopt_external_setpoint``/``adopt_external_mode`` ARE parsed (they
          are tuning fields), but only ``__init__`` reads them —
          ``async_apply_options`` never re-reads them (pre-existing drift).
          The wiring must keep NOT hot-applying them; fixing that drift is a
          separate, deliberate change.
        * ``climate_mode`` is NOT parsed: store-owned user intent
          (``UserControlState``).
        """
        # Constants by design (never config-read); the presence eco delta is
        # wired to the constant eco offset.
        override_cfg = OverrideConfig()
        # An unknown/corrupt category string must not throw — fall back to the
        # norm default (identical guard on both paths).
        try:
            category = Category(merged.get(CONF_CATEGORY, "II"))
        except ValueError:
            category = Category("II")
        delta = float(merged.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA))
        start = parse_hhmm(merged.get(CONF_COMFORT_START))
        end = parse_hhmm(merged.get(CONF_COMFORT_END))
        # An empty/invalid HH:MM parses to None -> always_comfort (guard
        # identical on both paths, including the error path).
        schedule = (
            ComfortSchedule.from_windows([ComfortWindow(start, end)], delta)
            if start is not None and end is not None and delta > 0.0
            else ComfortSchedule.always_comfort()
        )
        optimal_start = bool(merged.get(CONF_OPTIMAL_START, True))
        return cls(
            window_auto_cfg=WindowAutoConfig(),
            override_policy=str(
                merged.get(CONF_OVERRIDE_POLICY, DEFAULT_OVERRIDE_POLICY)
            ),
            override_cfg=override_cfg,
            trace_enabled=bool(merged.get(CONF_TRACE_RECORDING, False)),
            presence_cfg=PresenceConfig(
                absence_after_min=float(
                    merged.get(CONF_ABSENCE_AFTER_MIN, DEFAULT_ABSENCE_AFTER_MIN)
                ),
                eco_delta=override_cfg.eco_offset,
            ),
            category=category,
            comfort_base=float(merged.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)),
            hdh_cfg=HdhConfig(
                annual_kwh=float(merged.get(CONF_ANNUAL_KWH, DEFAULT_ANNUAL_KWH)),
                price_eur_kwh=report_price_eur_kwh(
                    merged.get(CONF_PRICE_EUR_KWH),
                    # Reads the data-owned installation key source_policy out
                    # of the merged mapping.
                    merged.get(CONF_SOURCE_POLICY),
                    gas=DEFAULT_PRICE_GAS_EUR_KWH,
                    electric=DEFAULT_PRICE_EUR_KWH,
                ),
            ),
            dynamics_override=_parse_dynamics_override(
                merged.get(CONF_DYNAMICS, DEFAULT_DYNAMICS)
            ),
            mpc_params=MpcParams(),
            compressor_guard=str(
                merged.get(CONF_COMPRESSOR_GUARD, COMPRESSOR_GUARD_AUTO)
            ),
            comp_min_off_opt=_float_or_none(merged.get(CONF_COMPRESSOR_MIN_OFF)),
            comp_mode_hold_opt=_float_or_none(merged.get(CONF_COMPRESSOR_MODE_HOLD)),
            thermal_shock_delta=float(
                merged.get(CONF_THERMAL_SHOCK_DELTA, DEFAULT_SHOCK_DELTA_K)
            ),
            cool_hard_cap=float(merged.get(CONF_COOL_HARD_CAP, DEFAULT_HARD_CAP_C)),
            # Deliberately no coercion (both paths keep the raw str|bool;
            # resolve_adaptive_cool normalises per tick).
            adaptive_cool_cfg=merged.get(CONF_ADAPTIVE_COOL, DEFAULT_ADAPTIVE_COOL),
            cool_min_outdoor=float(
                merged.get(CONF_COOL_MIN_OUTDOOR, DEFAULT_COOL_MIN_OUTDOOR_C)
            ),
            heat_max_outdoor=float(
                merged.get(CONF_HEAT_MAX_OUTDOOR, DEFAULT_HEAT_MAX_OUTDOOR_C)
            ),
            # The lockout toggles stay in lockstep on both paths.
            heat_lockout_enabled=bool(
                merged.get(CONF_HEAT_LOCKOUT_ENABLED, DEFAULT_HEAT_LOCKOUT_ENABLED)
            ),
            cool_lockout_enabled=bool(
                merged.get(CONF_COOL_LOCKOUT_ENABLED, DEFAULT_COOL_LOCKOUT_ENABLED)
            ),
            priority=(
                float(merged.get(CONF_COMFORT_WEIGHT, DEFAULT_COMFORT_WEIGHT)) / 100.0
            ),
            schedule=schedule,
            optimal_start=optimal_start,
            optimal_stop=optimal_start,  # coupled by design
            adopt_external_setpoint=bool(
                merged.get(
                    CONF_ADOPT_EXTERNAL_SETPOINT, DEFAULT_ADOPT_EXTERNAL_SETPOINT
                )
            ),
            adopt_external_mode=bool(
                merged.get(CONF_ADOPT_EXTERNAL_MODE, DEFAULT_ADOPT_EXTERNAL_MODE)
            ),
            operative_input=bool(merged.get(CONF_OPERATIVE_INPUT, False)),
        )


@dataclass(frozen=True, slots=True)
class HoldTuning:
    """ADR-0059 §1/§2 hold/Boost timing — ``_read_override_options`` minus
    ``override_policy`` (which is pinned into ``ZoneTuning``).

    These four attributes (``override_timer_h`` / ``override_max_h`` /
    ``override_end_on_presence`` / ``boost_duration_min``) have no
    ``ZoneTuning`` slot, because the ``ZoneTuning`` field contract is pinned
    (``test_phase1_config``). They live in this sibling structure, parsed with
    the identical merged-dict semantics: the wiring calls
    ``ZoneConfig.from_entry`` AND ``HoldTuning.from_entry`` on both paths.
    """

    override_timer_h: float  # §1 timer-policy hold length [h]
    override_max_h: float  # §1 hard cap on any announced hold expiry [h]
    override_end_on_presence: bool  # §1 presence flip ends an active hold
    boost_duration_min: float  # §2 timed Boost preset length [min]

    @classmethod
    def from_merged(cls, merged: Mapping[str, Any]) -> HoldTuning:
        """Parse the hold timing (defaults/coercions identical on both paths)."""
        return cls(
            override_timer_h=float(
                merged.get(CONF_OVERRIDE_TIMER_H, DEFAULT_OVERRIDE_TIMER_H)
            ),
            override_max_h=float(
                merged.get(CONF_OVERRIDE_MAX_H, DEFAULT_OVERRIDE_MAX_H)
            ),
            override_end_on_presence=bool(
                merged.get(
                    CONF_OVERRIDE_END_ON_PRESENCE, DEFAULT_OVERRIDE_END_ON_PRESENCE
                )
            ),
            boost_duration_min=float(
                merged.get(CONF_BOOST_DURATION_MIN, DEFAULT_BOOST_DURATION_MIN)
            ),
        )

    @classmethod
    def from_mappings(
        cls, data: Mapping[str, Any], options: Mapping[str, Any]
    ) -> HoldTuning:
        """Parse from the two entry mappings (options over data)."""
        return cls.from_merged(_merged(data, options))

    @classmethod
    def from_entry(cls, entry: ConfigEntryLike) -> HoldTuning:
        """Parse from a config entry (structural typing, stays pure)."""
        return cls.from_mappings(entry.data, entry.options)


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    """One fully parsed zone entry: wiring + tuning.

    ``from_entry`` / ``from_mappings`` are the single parser feeding both
    ``__init__`` and ``async_apply_options``. The ADR-0059 hold timing rides
    alongside in ``HoldTuning`` (the field contracts of this class and
    ``ZoneTuning`` are pinned, so it cannot nest here); wiring code must parse
    both.
    """

    structure: ZoneStructure
    tuning: ZoneTuning

    @classmethod
    def from_mappings(
        cls, data: Mapping[str, Any], options: Mapping[str, Any]
    ) -> ZoneConfig:
        """Parse one zone entry from its two config mappings.

        One merged mapping (options over data, also for structural keys), then
        the field reads of both paths (verified drift-free). Corrupt numeric
        values raise out of ``float(...)`` — but atomically, before anything is
        applied. A corrupt value therefore fails the WHOLE hot-apply instead of
        tearing the tuning mid-sequence (the baseline applied fields before the
        throwing line and kept the rest old, without a refresh). That
        error-path change is a deliberate consequence of the atomic parser,
        pinned by ``test_phase2_config_paths.py::
        test_corrupt_option_fails_hot_apply_atomically``.

        Accepted marginal deviation: WITHIN one parse the order of throwing
        coercions differs from the baseline — ``setback_delta`` coerces first
        here (the schedule guard consumes it) while the baseline coerced it
        after all other tuning floats. Observable only when >= 2 values are
        corrupt at once, and then only in WHICH value the (identically typed
        and handled) ``ValueError`` names. Unfixable exactly anyway: the
        baseline ``__init__`` and ``async_apply_options`` orders differ from
        each other, and one shared parser cannot reproduce both.
        """
        merged = _merged(data, options)
        return cls(
            structure=ZoneStructure.from_merged(merged),
            tuning=ZoneTuning.from_merged(merged),
        )

    @classmethod
    def from_entry(cls, entry: ConfigEntryLike) -> ZoneConfig:
        """Parse a zone config entry (structural typing, stays pure)."""
        return cls.from_mappings(entry.data, entry.options)


@dataclass(frozen=True, slots=True)
class HotApplyConfig:
    """Exactly what ``async_apply_options`` hot-applies.

    Equivalence contract: the hot-apply path reads NO structural key —
    ``_require`` never ran there — so a merged mapping missing ``name``/
    ``temp_sensor``/``actuator`` must still hot-apply the tuning cleanly
    instead of raising ``MissingStructuralFieldError`` (reachable: a
    legacy/hand-edited entry holds a structural key only in ``entry.options``,
    and an options-flow submit replaces ``options`` and drops the key while
    ``entry.data`` stays unchanged, so ``structural_unchanged`` still routes
    into the hot-apply). Only the two options-owned entity lists
    (presence/occupancy) are re-read, via the never-throwing ``as_entity_list``.

    Parse order is hold-before-tuning, mirroring the
    ``_read_override_options``-first read on BOTH paths: with several corrupt
    values at once the hold floats throw first. ``__init__`` does not use this
    parse (it needs the structure and must keep its require-before-tuning throw
    order); it bundles its already parsed pieces via ``from_zone_config`` so
    both paths still feed the ONE apply method with the identical shape.
    """

    tuning: ZoneTuning
    hold: HoldTuning
    presence_home_entities: tuple[str, ...]  # options-owned, hot-applied
    occupancy_entities: tuple[str, ...]  # options-owned, hot-applied

    @classmethod
    def from_zone_config(cls, cfg: ZoneConfig, hold: HoldTuning) -> HotApplyConfig:
        """Bundle an already parsed setup-path config (no re-parse)."""
        return cls(
            tuning=cfg.tuning,
            hold=hold,
            presence_home_entities=cfg.structure.presence_home_entities,
            occupancy_entities=cfg.structure.occupancy_entities,
        )

    @classmethod
    def from_merged(cls, merged: Mapping[str, Any]) -> HotApplyConfig:
        """Parse the hot-apply view from the MERGED mapping (options>data)."""
        hold = HoldTuning.from_merged(merged)
        tuning = ZoneTuning.from_merged(merged)
        return cls(
            tuning=tuning,
            hold=hold,
            presence_home_entities=tuple(
                as_entity_list(merged.get(CONF_PRESENCE_HOME))
            ),
            occupancy_entities=tuple(as_entity_list(merged.get(CONF_OCCUPANCY_SENSOR))),
        )

    @classmethod
    def from_mappings(
        cls, data: Mapping[str, Any], options: Mapping[str, Any]
    ) -> HotApplyConfig:
        """Parse from the two entry mappings (options over data)."""
        return cls.from_merged(_merged(data, options))

    @classmethod
    def from_entry(cls, entry: ConfigEntryLike) -> HotApplyConfig:
        """Parse from a config entry (structural typing, stays pure)."""
        return cls.from_mappings(entry.data, entry.options)


def structures_equal(a: ZoneStructure, b: ZoneStructure) -> bool:
    """True when two wirings describe the same physical zone (field-wise).

    Basis for ``PoiseCoordinator.structural_unchanged``: a structural change
    means the entry is reloading, so the in-place options hot-apply must not
    run on the soon-to-be-discarded coordinator. Trivial (dataclass equality),
    but a named function so the reload-vs-hot-apply decision has exactly one
    greppable seam.

    WARNING: this field-wise comparison is NOT a drop-in replacement for the
    predicate ``dict(entry.data) == self._data_snapshot``. Room ``entry.data``
    carries keys outside these 13 fields (the installation keys
    ``controls_boiler``/``compressor_group``/``declared_power``/
    ``design_flow_temp``/``source_policy``; on fresh v2.2 entries also
    ``comfort_base`` + ``category`` until their first reconfigure), whose
    changes must KEEP reading as structural (hot-apply skipped on the
    coordinator the reload is about to discard). Conversely
    ``presence_home_entities``/``occupancy_entities`` are options-owned and
    hot-applied, so they must stay OUT of any reload predicate. The coordinator
    therefore keeps the data-dict comparison until that gap is deliberately
    resolved.
    """
    return a == b
