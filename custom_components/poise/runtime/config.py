"""Parsed zone configuration contracts (refactoring plan, phase 1).

``ZoneConfig`` is the typed shape of one zone entry, split along the
reload-vs-hot-apply boundary the coordinator already enforces (F14):

* ``ZoneStructure`` — the entity wiring (structural ``entry.data``): which
  sensors and which actuator make up the zone. A structural change means the
  entry reloads and the running coordinator is discarded, so options must
  never hot-apply onto it.
* ``ZoneTuning`` — hot-applyable tuning (``entry.options`` over
  ``entry.data``): comfort, schedule, override and guard parameters that
  ``async_apply_options`` may swap on a live coordinator.

Deliberately absent: ``climate_mode``. It is store-owned user intent (the
user flips it at runtime and it must survive restarts), not configuration —
it belongs to ``UserControlState`` (plan section 3).

Phase-1 scope: type definitions only. The single ``ZoneConfig.from_entry``
parser that will feed both ``__init__`` and ``async_apply_options`` arrives
in phase 2; it cannot live here because this module stays pure (no
``homeassistant`` import). Option defaults keep living in ``const.py`` and
are resolved by that parser — never by dataclass defaults here, so there is
exactly one place a default can drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..comfort.en16798 import Category
from ..comfort.presence import PresenceConfig
from ..comfort.schedule import ComfortSchedule
from ..control.dynamics import DeviceDynamics
from ..control.hdh_savings import HdhConfig
from ..control.mpc import MpcParams
from ..control.override import OverrideConfig
from ..control.window_auto import WindowAutoConfig


@dataclass(frozen=True, slots=True)
class ZoneStructure:
    """Entity wiring of one zone (the structural ``entry.data`` reads).

    Field <-> today's coordinator attribute (``__init__``):
    ``zone_name`` <- ``zone_name``, ``temperature_sensor`` <- ``_temp``,
    ``actuator`` <- ``_actuator``, ``trm`` <- ``_trm``,
    ``outdoor`` <- ``_outdoor``, ``humidity`` <- ``_humidity``,
    ``mrt`` <- ``_mrt``,
    ``presence_home_entities`` <- ``_presence_home_entities``,
    ``occupancy_entities`` <- ``_occupancy_entities``,
    ``windows`` <- ``_windows``, ``weather`` <- ``_weather``,
    ``irradiance`` <- ``_irradiance``, ``trv_ext_temp`` <- ``_trv_ext_temp``.

    Entity-list fields are tuples (immutable, so the snapshot can never be
    mutated behind the runtime's back) instead of today's lists; optional
    single entities are ``None`` when not configured.
    """

    zone_name: str
    temperature_sensor: str  # required: the room sensor (AR-34 setup gate)
    actuator: str  # required: the single-writer target (AR-34 setup gate)
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


@dataclass(frozen=True, slots=True)
class ZoneTuning:
    """Hot-applyable tuning of one zone — everything ``async_apply_options``
    may change without a reload.

    Field names are today's coordinator attributes minus the leading
    underscore (``__init__`` Z. 299-587); the two non-trivial typings:

    * ``dynamics_override`` — typed as ``DeviceDynamics | None`` instead of
      today's raw option string: ``None`` means auto-classify from the
      actuator's capabilities, exactly the ``classify_dynamics`` semantics
      where ``"auto"`` / any unknown string falls through to detection
      (ADR-0052).
    * ``adaptive_cool_cfg`` — the stored value is the tri-state selector
      string (``"auto"`` / ``"on"`` / ``"off"``) but legacy entries hold a
      boolean; ``adaptive_cool_mode`` normalises at the use site (ADR-0008).

    No ``climate_mode`` field by design: it is store-owned user intent, not
    configuration (plan section 3, ``UserControlState``).
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
    cool_min_outdoor: float  # F4a cooling lockout below this outdoor [degC]
    heat_max_outdoor: float  # F4a heating lockout above this outdoor [degC]
    heat_lockout_enabled: bool
    cool_lockout_enabled: bool
    priority: float  # comfort weight / 100 -> [0, 1]
    schedule: ComfortSchedule  # ADR-0025 comfort windows + setback depth
    optimal_start: bool
    # Coasts to the lower comfort edge before window end; today deliberately
    # coupled to optimal_start (predictive scheduling), splittable later.
    optimal_stop: bool
    adopt_external_setpoint: bool  # P1-4a: TRV wheel -> manual hold
    adopt_external_mode: bool  # K2: IR remote -> manual mode-hold
    operative_input: bool  # ADR-0029 operative-temperature input mode


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    """One fully parsed zone entry: wiring + tuning (plan section 2).

    Phase 2 adds ``from_entry(entry)`` as the *single* parser feeding both
    ``__init__`` and ``async_apply_options`` (no parser here: this module
    must stay importable without Home Assistant).
    """

    structure: ZoneStructure
    tuning: ZoneTuning


def structures_equal(a: ZoneStructure, b: ZoneStructure) -> bool:
    """True when two wirings describe the same physical zone (field-wise).

    Phase-2 basis for ``PoiseCoordinator.structural_unchanged`` (F14): a
    structural change means the entry is reloading, so the in-place options
    hot-apply must not run on the soon-to-be-discarded coordinator. Trivial
    today (dataclass equality), but a named function so the
    reload-vs-hot-apply decision has exactly one greppable seam.
    """
    return a == b
