"""Per-tick read-only views of the coordinator (plan step O.2).

The tick program reads 39 coordinator attributes purely for information: 30
policy/config values and 9 entity bindings. Reading them one by one through
the transitional ``TickOrchestrator._c`` backreference makes every stage
depend on the whole ``PoiseCoordinator`` type. The two frozen objects here
replace that with an explicit, narrow contract:

* ``TickConfigSnapshot`` — the tick-stable, read-only policy/config values.
  Built ONCE per tick, AFTER the availability gate (the unavailable
  short-circuit provably reads none of these fields, so building it earlier
  would be blind work on the most common degradation path).
* ``ZoneBindings`` — the zone's identity and entity wiring. Built ONCE per
  tick, BEFORE the availability gate: the gate's very first HA state read is
  ``bindings.temp``, and the unavailable path itself needs ``temp``,
  ``actuator`` and ``zone_name``. It must NOT be snapshotted in a constructor
  either — ``HealthReporter.validate_configured_ext_temp`` resets
  ``_trv_ext_temp`` during ``async_bootstrap``, so a construction-time copy
  would be stale for every tick that follows.

Why a snapshot is legitimate at all (the load-bearing argument, pinned by
``tests/test_o2_tick_snapshot.py``): the 30 config attributes are written
only by ``PoiseCoordinator.__init__`` and ``PoiseCoordinator._apply_hot_tuning``
(four of them by ``__init__`` alone), and ``_apply_hot_tuning`` runs only from
``__init__`` and from ``async_apply_options``, which takes the SAME tick lock
that ``_async_update_data`` holds for the whole tick. The bindings are written
by ``__init__`` alone, except ``_trv_ext_temp``, whose one other writer runs
in ``async_bootstrap`` — before the first tick. Nothing can therefore mutate
either object's sources while a tick is running.

``PoiseCoordinator`` is imported under ``TYPE_CHECKING`` only: this module
belongs to the tick program that ``coordinator.py`` itself imports, so a
runtime import would close the cycle (``ha/tick_orchestrator.py`` does the
same for the same reason).

MUTABILITY RULE (gated by ``tests/test_tick_chain_structure.py``): no field of
either class may be typed ``list``/``dict``/``set``. ``frozen=True`` freezes
the field BINDING, not the object behind it — ``coordinator._windows`` is a
live ``list[str]``, so ``windows`` is a ``tuple[str, ...]`` built with
``tuple(...)``. Every future sequence field follows that rule. The same gate
keeps entity-ID fields out of ``TickConfigSnapshot``: identity and wiring
belong to ``ZoneBindings``, configuration does not carry entity ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from ..comfort.en16798 import Category
    from ..comfort.presence import PresenceConfig
    from ..comfort.schedule import ComfortSchedule
    from ..control.dynamics import DeviceDynamics
    from ..control.hdh_savings import HdhConfig
    from ..control.override import OverrideConfig
    from ..control.window_auto import WindowAutoConfig
    from ..coordinator import PoiseCoordinator


@dataclass(frozen=True, slots=True)
class TickConfigSnapshot:
    """The tick's read-only policy/config view (30 fields).

    Field name == coordinator attribute without the leading underscore. Every
    field is either hot-applyable tuning (26, written by ``_apply_hot_tuning``)
    or deliberately init-only (4: ``window_auto_cfg``, ``override_cfg``,
    ``adopt_external_mode``, ``adopt_external_setpoint``). Both groups are
    constant for the duration of a tick — see the module docstring.

    Deliberately NOT here: ``_mpc_params`` (written by the tick itself through
    ``_set_mpc_params``) and ``_unavailable_logged`` (adapter state the
    orchestrator writes). Both stay coordinator-owned ports.
    """

    active_comfort: bool
    adaptive_cool_cfg: str | bool
    adopt_external_mode: bool
    adopt_external_setpoint: bool
    category: Category
    clo_offset: float
    comfort_base: float
    comp_min_off_opt: float | None
    comp_mode_hold_opt: float | None
    compressor_guard: str
    cool_hard_cap: float
    cool_lockout_enabled: bool
    cool_min_outdoor: float
    dynamics_override: DeviceDynamics | None
    hdh_cfg: HdhConfig
    heat_lockout_enabled: bool
    heat_max_outdoor: float
    operative_input: bool
    optimal_start: bool
    optimal_stop: bool
    override_cfg: OverrideConfig
    override_policy: str
    presence_cfg: PresenceConfig
    priority: float
    room_profile: str
    schedule: ComfortSchedule
    thermal_shock_delta: float
    trace_enabled: bool
    vent_notify: bool
    window_auto_cfg: WindowAutoConfig

    @classmethod
    def from_coordinator(cls, coordinator: PoiseCoordinator) -> TickConfigSnapshot:
        """Copy the 30 config attributes off the live coordinator.

        Called ONCE per tick, right after the availability gate has passed.
        Every keyword below names exactly one coordinator attribute (bijection
        pinned by ``tests/test_o2_tick_snapshot.py``).
        """
        return cls(
            active_comfort=coordinator._active_comfort,
            adaptive_cool_cfg=coordinator._adaptive_cool_cfg,
            adopt_external_mode=coordinator._adopt_external_mode,
            adopt_external_setpoint=coordinator._adopt_external_setpoint,
            category=coordinator._category,
            clo_offset=coordinator._clo_offset,
            comfort_base=coordinator._comfort_base,
            comp_min_off_opt=coordinator._comp_min_off_opt,
            comp_mode_hold_opt=coordinator._comp_mode_hold_opt,
            compressor_guard=coordinator._compressor_guard,
            cool_hard_cap=coordinator._cool_hard_cap,
            cool_lockout_enabled=coordinator._cool_lockout_enabled,
            cool_min_outdoor=coordinator._cool_min_outdoor,
            dynamics_override=coordinator._dynamics_override,
            hdh_cfg=coordinator._hdh_cfg,
            heat_lockout_enabled=coordinator._heat_lockout_enabled,
            heat_max_outdoor=coordinator._heat_max_outdoor,
            operative_input=coordinator._operative_input,
            optimal_start=coordinator._optimal_start,
            optimal_stop=coordinator._optimal_stop,
            override_cfg=coordinator._override_cfg,
            override_policy=coordinator._override_policy,
            presence_cfg=coordinator._presence_cfg,
            priority=coordinator._priority,
            room_profile=coordinator._room_profile,
            schedule=coordinator._schedule,
            thermal_shock_delta=coordinator._thermal_shock_delta,
            trace_enabled=coordinator._trace_enabled,
            vent_notify=coordinator._vent_notify,
            window_auto_cfg=coordinator._window_auto_cfg,
        )


@dataclass(frozen=True, slots=True)
class ZoneBindings:
    """The zone's identity and entity wiring (9 fields).

    Field name == coordinator attribute without the leading underscore
    (``zone_name`` has none). All nine are structural (``entry.data``), so a
    change reloads the entry and discards the running coordinator; the one
    exception, ``trv_ext_temp``, is additionally reset by
    ``HealthReporter.validate_configured_ext_temp`` during ``async_bootstrap``
    — which is why this object is rebuilt every tick instead of once.
    """

    entry_id: str
    zone_name: str
    temp: str
    humidity: str | None
    weather: str | None
    outdoor_humidity: str | None
    trv_ext_temp: str | None
    actuator: str
    windows: tuple[str, ...]

    @classmethod
    def from_coordinator(cls, coordinator: PoiseCoordinator) -> ZoneBindings:
        """Copy the 9 wiring attributes off the live coordinator.

        Called as the FIRST statement of every tick, before the availability
        gate. ``windows`` is copied into a tuple because the coordinator holds
        a live ``list[str]`` and ``frozen=True`` would not freeze its contents.
        """
        return cls(
            entry_id=coordinator._entry_id,
            zone_name=coordinator.zone_name,
            temp=coordinator._temp,
            humidity=coordinator._humidity,
            weather=coordinator._weather,
            outdoor_humidity=coordinator._outdoor_humidity,
            trv_ext_temp=coordinator._trv_ext_temp,
            actuator=coordinator._actuator,
            windows=tuple(coordinator._windows),
        )
