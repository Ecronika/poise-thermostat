"""The single READING Home-Assistant adapter (refactoring plan, phase 4).

``InputReader`` owns every ``hass.states.get`` primitive of the coordinator
plus the device-guard registry discovery. Two kinds of API, mirroring the
plan's binding phase-4 constraint (module boundary moves, read POSITIONS in
the tick do not):

* ``snapshot() -> TickInputs`` bundles EXACTLY the contiguous read block
  BEFORE the tick's first ``await`` (coordinator.py lines 1810-2063; the
  first await is the forecast fetch at line 2064). Within that segment Home
  Assistant's single-threaded event loop guarantees no state can change
  between reads, so merging them into one snapshot — including collapsing
  the segment's four actuator reads (lines 1680/1952/1961/1982) into ONE —
  is provably equivalent. The segment's ad-hoc clock calls are unified onto
  the snapshot instants (``now_mono``/``now_wall``/``local_minute``/
  ``local_day_ordinal``) per the plan's "Uhr vereinheitlichen" directive;
  the sub-millisecond divergence this removes is unobservable.

* Positioned single reads stay separate named methods because they run AFTER
  an ``await`` today, where a state change during the await is observable
  and must remain so: ``read_presence()``/``ext_feed_target_ok()`` (after
  the forecast await, lines 2096/2181 and 2159), ``actuator_state()``/
  ``read_actuator()`` (the central actuator read, line 2250; also the
  unavailable-path safe-state read after the dirty-flush await, line 1761),
  ``ext_select_state()`` (in the write path after the mode/setpoint awaits,
  line 3019) and ``valve_steps()`` (after the save checkpoint, lines
  3325-3326). Clock calls after awaits are untouched by this module.

Full one-snapshot-per-tick consolidation is reserved for the phase-6
prepare/resume structure. All line numbers reference the phase-3 baseline
coordinator.py (3648 lines).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..clock import Clock
from ..const import DEVICE_MAX_C
from ..devices.capability import classify_number_entity, climate_capability
from ..devices.model_fixes import (
    is_external_sensor_select,
    looks_like_adaptive_mode_switch,
    looks_like_external_temp_number,
    looks_like_fault_alarm,
    looks_like_internal_schedule,
    looks_like_valve_steps,
)
from ..ingestion import parse_finite
from ..runtime.config import ZoneStructure
from ..runtime.tick_inputs import (
    ActuatorCapabilitySnapshot,
    ActuatorSnapshot,
    BinarySensorSnapshot,
    DeviceGuardSnapshot,
    PresenceSnapshot,
    SensorValue,
    TickInputs,
)
from ..safety.sensor_watchdog import sensor_age_seconds

_LOGGER = logging.getLogger(__name__)

_INVALID = {"unknown", "unavailable", ""}


def parse_state_number(state: State | None) -> float | None:
    """Numeric state parse (coordinator ``_num``, lines 217-220, 1:1).

    ``unknown``/``unavailable``/empty read as ``None``; ``parse_finite``
    rejects NaN/Inf at the boundary (C1).
    """
    if state is None or state.state in _INVALID:
        return None
    return parse_finite(state.state)


def parse_attr_number(state: State | None, key: str) -> float | None:
    """Numeric attribute parse (coordinator ``_num_attr``, lines 223-227, 1:1).

    Excludes ONLY ``state == "unavailable"`` — attributes are read even while
    the state is ``"unknown"`` (deliberately narrower than
    :func:`parse_state_number`; e.g. a just-restarted climate device reports
    its setpoint before its mode).
    """
    if state is None or state.state == "unavailable":
        return None
    return parse_finite(state.attributes.get(key))


def actuator_snapshot(state: State | None) -> ActuatorSnapshot:
    """Freeze one already-captured actuator State into an ActuatorSnapshot.

    Models today's one-object rule: every attribute access after the central
    read at line 2250 (lines 2790/2793, 3082-3083, 3239-3273, 3428-3429,
    3641-3643) reads the SAME immutable State object, never a fresh
    ``states.get``. Parse semantics per field are conserved exactly:
    ``actual_setpoint``/``target_temperature_step`` via the ``_num_attr``
    rule (line 2790/2793); ``min_temp``/``max_temp`` via the raw
    isinstance-numeric capture (``_device_min``/``_device_max``, lines
    1244-1255/1236-1242 — the ``None``/``DEVICE_MAX_C`` fallback rules stay
    with the consumer); ``current_temperature`` via a plain ``float()`` with
    ``TypeError``/``ValueError`` -> ``None`` and NO availability gate (lines
    3428-3434 — the finite parser is deliberately not applied there today).
    """
    if state is None:
        return ActuatorSnapshot(
            state=None,
            hvac_modes=(),
            actual_setpoint=None,
            target_temperature_step=None,
            min_temp=None,
            max_temp=None,
            hvac_action=None,
            fan_mode=None,
            fan_modes=(),
            context_id=None,
            current_temperature=None,
        )
    attrs = state.attributes
    mn = attrs.get("min_temp")
    mx = attrs.get("max_temp")
    hvac_action = attrs.get("hvac_action")
    fan_mode = attrs.get("fan_mode")
    current_raw = attrs.get("current_temperature")
    try:
        current = float(current_raw) if current_raw is not None else None
    except (TypeError, ValueError):
        current = None
    return ActuatorSnapshot(
        state=state.state,
        hvac_modes=tuple(str(m) for m in (attrs.get("hvac_modes") or ())),
        actual_setpoint=parse_attr_number(state, "temperature"),
        target_temperature_step=parse_attr_number(state, "target_temperature_step"),
        min_temp=float(mn) if isinstance(mn, (int, float)) else None,
        max_temp=float(mx) if isinstance(mx, (int, float)) else None,
        hvac_action=str(hvac_action) if hvac_action is not None else None,
        fan_mode=str(fan_mode) if fan_mode is not None else None,
        fan_modes=tuple(str(m) for m in (attrs.get("fan_modes") or ())),
        context_id=state.context.id if state.context is not None else None,
        current_temperature=current,
    )


class InputReader:
    """Owns all state reads + guard discovery for one zone (plan section 2).

    The discovered guard entity ids are plain public attributes (mirroring
    today's coordinator attributes ``_sched_entity`` etc., plan section 3)
    so the wiring step can proxy them and tests can pin them — pinned values
    survive re-resolution because discovery is idempotent.
    """

    def __init__(
        self, hass: HomeAssistant, structure: ZoneStructure, clock: Clock
    ) -> None:
        self._hass = hass
        self._structure = structure
        self._clock = clock
        # Device-guard discovery results (coordinator __init__ lines 573-582).
        self.guards_resolved = False
        self.sched_entity: str | None = None
        self.fault_entity: str | None = None
        self.adaptive_mode_entity: str | None = None
        self.battery_entity: str | None = None
        self.ext_temp_auto: str | None = None
        self.sensor_select: str | None = None
        self.valve_entity: str | None = None
        self.valve_closing_steps: str | None = None
        self.valve_idle_steps: str | None = None

    def set_presence_entities(
        self, home: Sequence[str], occupancy: Sequence[str]
    ) -> None:
        """Follow a hot-applied presence-list change (wiring step, phase 4).

        The presence entity lists are the ONE options-owned, hot-applied piece
        of the otherwise reload-only :class:`ZoneStructure` (coordinator
        ``_apply_hot_tuning``); without this sync :meth:`read_presence` would
        keep reading the setup-time lists after an options submit.
        """
        self._structure = replace(
            self._structure,
            presence_home_entities=tuple(home),
            occupancy_entities=tuple(occupancy),
        )

    # ------------------------------------------------------------------
    # registry discovery (coordinator lines 1040-1096, 1:1)
    # ------------------------------------------------------------------

    def resolve_device_guards(self) -> None:
        """Find schedule/fault/battery entities on the actuator's device (once).

        Position conserved: runs pre-first-await via the health block on the
        first tick (line 1694) and is a no-op afterwards (``guards_resolved``
        gate) — a manually pinned entity is never overwritten by a later
        re-resolution. A discovery failure is swallowed (debug log): guard
        resolution must never break setup.
        """
        if self.guards_resolved:
            return
        self.guards_resolved = True
        try:
            reg = er.async_get(self._hass)
            ent = reg.async_get(self._structure.actuator)
            if ent is None or ent.device_id is None:
                return
            for e in er.async_entries_for_device(
                reg, ent.device_id, include_disabled_entities=False
            ):
                eid = e.entity_id
                # R1: a device-internal adaptive/smart-temperature loop is
                # orthogonal to the roles below and can be a switch. OR a
                # select., so detect it independently of the elif chain (a
                # select. would otherwise be consumed by the sensor-select
                # branch first).
                if self.adaptive_mode_entity is None and (
                    looks_like_adaptive_mode_switch(eid)
                ):
                    self.adaptive_mode_entity = eid
                if self.sched_entity is None and looks_like_internal_schedule(eid):
                    self.sched_entity = eid
                elif self.fault_entity is None and looks_like_fault_alarm(eid):
                    self.fault_entity = eid
                elif (
                    self.battery_entity is None
                    and eid.startswith("sensor.")
                    and e.original_device_class == "battery"
                ):
                    self.battery_entity = eid
                elif self.ext_temp_auto is None and looks_like_external_temp_number(
                    eid, e.original_device_class
                ):
                    self.ext_temp_auto = eid
                elif self.sensor_select is None and eid.startswith("select."):
                    sel = self._hass.states.get(eid)
                    if is_external_sensor_select(
                        eid, sel.attributes.get("options") if sel else None
                    ):
                        self.sensor_select = eid
                elif (
                    self.valve_entity is None
                    and eid.startswith("number.")
                    and classify_number_entity(eid) == "valve"
                ):
                    self.valve_entity = eid
                elif looks_like_valve_steps(eid) == "closing":
                    self.valve_closing_steps = eid
                elif looks_like_valve_steps(eid) == "idle":
                    self.valve_idle_steps = eid
        except Exception:  # noqa: BLE001 - guard resolution must never break setup
            _LOGGER.debug("Poise: device-guard resolution failed", exc_info=True)

    def configured_ext_temp_signature(
        self, entity_id: str
    ) -> tuple[str | None, str | None]:
        """Registry/state signature of the CONFIGURED ext-temp number.

        The read half of ``_validate_configured_ext_temp`` (coordinator lines
        1139-1152, bootstrap position): device_class from the registry entry
        (``device_class or original_device_class``) with the live state's
        attribute as fallback, same for the unit. Returns
        ``(device_class, unit)``; registry errors propagate — the caller owns
        the "a registry miss must never block setup" boundary, exactly like
        today's surrounding try.
        """
        reg = er.async_get(self._hass)
        ent = reg.async_get(entity_id)
        device_class: str | None = None
        unit: str | None = None
        if ent is not None:
            device_class = ent.device_class or ent.original_device_class
            unit = ent.unit_of_measurement
        state = self._hass.states.get(entity_id)
        if state is not None:
            device_class = device_class or state.attributes.get("device_class")
            unit = unit or state.attributes.get("unit_of_measurement")
        return device_class, unit

    # ------------------------------------------------------------------
    # scalar read primitives (coordinator lines 1183-1262, 1:1)
    # ------------------------------------------------------------------

    def read(self, entity_id: str | None) -> float | None:
        """Finite-parsed numeric state, ``None`` when unset/invalid (``_read``)."""
        if not entity_id:
            return None
        return parse_state_number(self._hass.states.get(entity_id))

    def sensor_age(
        self, entity_id: str, *, now: datetime | None = None
    ) -> float | None:
        """Seconds since the sensor's value last CHANGED (``_sensor_age``).

        ``last_changed`` (the value-change time, per the watchdog contract): a
        dead/stuck sensor that keeps re-publishing the SAME value still bumps
        ``last_updated``, so only ``last_changed`` detects "available but
        frozen". ``snapshot()`` passes its unified wall anchor as ``now``
        (plan clock directive); ad-hoc callers get a fresh ``utcnow`` exactly
        like today's line 1198.
        """
        state = self._hass.states.get(entity_id)
        if state is None:
            return None
        anchor = dt_util.utcnow() if now is None else now
        return sensor_age_seconds(anchor, state.last_changed)

    def read_windows(self) -> tuple[BinarySensorSnapshot, ...]:
        """Per-contact window reads (pre-first-await, line 1914).

        F4a / ADR-0041 §5 availability rule conserved: a missing State,
        ``unavailable`` or ``unknown`` all mean the contact dropped off
        (``available=False``, ``is_on=None`` — distinguishable from a
        confirmed "closed"); anything else reports ``is_on = (state == "on")``.
        """
        contacts: list[BinarySensorSnapshot] = []
        for entity_id in self._structure.windows:
            state = self._hass.states.get(entity_id)
            if state is None or state.state in ("unavailable", "unknown"):
                contacts.append(
                    BinarySensorSnapshot(entity_id, is_on=None, available=False)
                )
            else:
                contacts.append(
                    BinarySensorSnapshot(
                        entity_id, is_on=state.state == "on", available=True
                    )
                )
        return tuple(contacts)

    def window_open(self) -> tuple[bool, bool]:
        """OR across the picker: any contact reporting "on" = open.

        Returns ``(sensor_open, sensor_unavailable)`` — the exact
        ``_window_open`` fold (coordinator lines 1204-1227): a dropped
        contact flags ``unavailable`` (the caller falls back to
        slope/auto-detection instead of trusting stale "closed" data), while
        a confirmed "on" from any OTHER still-working contact is trusted
        regardless (real positive evidence beats a sibling's dropout), so
        this never early-returns.
        """
        open_found = False
        unavailable = False
        for contact in self.read_windows():
            if not contact.available:
                unavailable = True
                continue
            if contact.is_on:
                open_found = True
        return open_found, unavailable

    def capability(self) -> tuple[bool, bool]:
        """(can_heat, can_cool) from a FRESH actuator read (``_capability``).

        Empty/missing ``hvac_modes`` defaults to ``(True, False)`` — assume a
        heat-only TRV (lines 1229-1234).
        """
        act = self._hass.states.get(self._structure.actuator)
        modes = act.attributes.get("hvac_modes") if act else None
        if modes:
            return climate_capability([str(m) for m in modes])
        return True, False  # default: assume a heat-only TRV

    def device_max(self) -> float:
        """The actuator's ``max_temp`` with the ``DEVICE_MAX_C`` fallback
        (``_device_max``, lines 1236-1242, fresh read)."""
        act = self._hass.states.get(self._structure.actuator)
        if act is not None:
            mx = act.attributes.get("max_temp")
            if isinstance(mx, (int, float)):
                return float(mx)
        return DEVICE_MAX_C

    def device_min(self) -> float | None:
        """The actuator's own ``min_temp`` (a physical write floor), if known.

        Returns ``None`` when absent/non-numeric so resolve_write_target
        skips the SAFETY floor clamp entirely (P3-1; ``_device_min``, lines
        1244-1255, fresh read — its tick call site at line 2325 sits in the
        same await-free window as the central actuator read).
        """
        act = self._hass.states.get(self._structure.actuator)
        if act is not None:
            mn = act.attributes.get("min_temp")
            if isinstance(mn, (int, float)):
                return float(mn)
        return None

    def sun_elevation(self) -> float | None:
        """``sun.sun``'s elevation attribute (``_sun_elevation``, 1257-1262)."""
        sun = self._hass.states.get("sun.sun")
        if sun is None:
            return None
        elev = sun.attributes.get("elevation")
        return float(elev) if isinstance(elev, (int, float)) else None

    def tristate(self, entity_id: str | None) -> bool | None:
        """Presence tristate resolution (``_tristate``, lines 2075-2094, 1:1).

        F8: a person/device_tracker reporting a named zone ("Work", "Gym",
        ...) is a resolved, confident "not home" — not a sensor failure. Any
        other domain's odd/custom state stays genuinely unresolved (None).
        """
        if not entity_id:
            return None
        st = self._hass.states.get(entity_id)
        if st is None or st.state in ("unknown", "unavailable"):
            return None
        s = st.state.lower()
        if s in ("home", "on", "true"):
            return True
        if s in ("not_home", "off", "false", "away"):
            return False
        if entity_id.split(".", 1)[0] in ("person", "device_tracker"):
            return False
        return None

    # ------------------------------------------------------------------
    # the pre-first-await snapshot (coordinator lines 1810-2063)
    # ------------------------------------------------------------------

    def snapshot(self) -> TickInputs:
        """Bundle the tick's contiguous pre-first-await read block.

        Covers exactly today's reads before the forecast await at line 2064:
        room (1810), the health block's actuator state / room age / guard
        discovery + guard values (1680-1733 via 1870), outdoor (1890), trm
        (1895), humidity (1903), sun + irradiance (1908), mrt (1913), the
        window contacts (1914) and the actuator's capability view
        (1952/1961/1982). Within this await-free segment HA's single-threaded
        loop makes the read order unobservable, so the four actuator reads
        collapse into ONE ``states.get`` here. The segment's clock calls are
        unified onto the snapshot instants (mono 1873 + learn/observe anchors
        1310/1358/1397; sensor-age utcnow 1198; local minute 2047 and day
        ordinals 1893/1404) — a sub-ms, unobservable divergence per the plan.
        Everything read after an await stays a positioned method of this
        class (module docstring).
        """
        now_mono = self._clock.monotonic()
        now_wall_dt = dt_util.utcnow()
        local_now = dt_util.now()
        s = self._structure

        room = SensorValue(
            value=self.read(s.temperature_sensor),
            age_s=self.sensor_age(s.temperature_sensor, now=now_wall_dt),
            entity_id=s.temperature_sensor,
        )

        # Health-block reads (position: first tick resolves the guards, then
        # idempotent). Guard entity reads only happen once discovered — an
        # un-discovered entity contributes today's neutral defaults.
        self.resolve_device_guards()
        sched_state = (
            self._hass.states.get(self.sched_entity) if self.sched_entity else None
        )
        adaptive_state = (
            self._hass.states.get(self.adaptive_mode_entity)
            if self.adaptive_mode_entity
            else None
        )
        fault_state = (
            self._hass.states.get(self.fault_entity) if self.fault_entity else None
        )
        device_guards = DeviceGuardSnapshot(
            sched_active=sched_state is not None and sched_state.state == "on",
            fault_active=fault_state is not None and fault_state.state == "on",
            battery=self.read(self.battery_entity) if self.battery_entity else None,
            adaptive_mode=(
                adaptive_state.state if adaptive_state is not None else None
            ),
            ext_temp_number=self.ext_temp_auto,
        )

        # ONE actuator read for the whole pre-await segment (merges today's
        # health/capability/dynamics/max reads at 1680/1952/1961/1982; raw
        # values — the heat-only and DEVICE_MAX_C defaults stay consumer
        # rules, see ActuatorCapabilitySnapshot).
        act = self._hass.states.get(s.actuator)
        act_max = act.attributes.get("max_temp") if act is not None else None
        actuator = ActuatorCapabilitySnapshot(
            state=act.state if act is not None else None,
            hvac_modes=(
                tuple(str(m) for m in (act.attributes.get("hvac_modes") or ()))
                if act is not None
                else ()
            ),
            max_temp=float(act_max) if isinstance(act_max, (int, float)) else None,
        )

        return TickInputs(
            now_mono=now_mono,
            now_wall=now_wall_dt.timestamp(),
            local_minute=int(local_now.hour * 60 + local_now.minute),
            local_day_ordinal=local_now.toordinal(),
            sun_elevation=self.sun_elevation(),
            room=room,
            outdoor=SensorValue(value=self.read(s.outdoor), entity_id=s.outdoor),
            humidity=SensorValue(value=self.read(s.humidity), entity_id=s.humidity),
            trm=SensorValue(value=self.read(s.trm), entity_id=s.trm),
            mrt=SensorValue(value=self.read(s.mrt), entity_id=s.mrt),
            irradiance=SensorValue(
                value=self.read(s.irradiance), entity_id=s.irradiance
            ),
            windows=self.read_windows(),
            actuator=actuator,
            device_guards=device_guards,
        )

    # ------------------------------------------------------------------
    # positioned post-await reads (order in the tick is behaviour)
    # ------------------------------------------------------------------

    def read_presence(self) -> PresenceSnapshot:
        """Presence + occupancy tristates (position: AFTER the forecast await).

        Today home is read at line 2096 and occupancy at line 2181; both sit
        in the same await-free window, so one merged read is equivalent —
        but the pair must NOT move before the forecast await (a presence flip
        during the fetch is observable today).
        """
        s = self._structure
        return PresenceSnapshot(
            home=tuple(self.tristate(e) for e in s.presence_home_entities),
            occupancy=tuple(self.tristate(e) for e in s.occupancy_entities),
        )

    def actuator_state(self) -> State | None:
        """The raw positioned actuator read.

        Used at the central line-2250 position (after the forecast await;
        the F2 online gate and every later attribute access consume this ONE
        object) and at the unavailable-path safe-state read (line 1761,
        after the conditional dirty-flush save await). Both must observe a
        device change that happened during the preceding await, so this is
        deliberately NOT part of ``snapshot()``.
        """
        return self._hass.states.get(self._structure.actuator)

    def read_actuator(self) -> ActuatorSnapshot:
        """Typed capture of the central actuator read (line-2250 position)."""
        return actuator_snapshot(self.actuator_state())

    def ext_feed_target_ok(self, entity_id: str | None) -> bool:
        """Availability of the ext-temp feed target (line 2159-2160 position).

        The number is write-only, so an ``unknown`` state is fine; only
        ``unavailable`` (or a missing/unconfigured entity) means the device
        is offline (ADR-0029). Positioned after the forecast await; the
        caller passes the resolved feed target (configured id or the
        discovered ``ext_temp_auto``).
        """
        state = self._hass.states.get(entity_id) if entity_id else None
        return state is not None and state.state != "unavailable"

    def ext_select_state(self) -> str | None:
        """FRESH state of the TRV's sensor-source select (line 3019 position).

        Read in the write path after the mode-nudge/setpoint awaits — a
        select change during those service calls is observable today and
        stays so. ``None`` when no select was discovered or its State is
        missing; the caller's "switch unless already external/unavailable"
        decision is unchanged (a State's ``state`` string is never ``None``,
        so ``None`` cannot collide with a real state).
        """
        if not self.sensor_select:
            return None
        sel = self._hass.states.get(self.sensor_select)
        return sel.state if sel is not None else None

    def valve_steps(self) -> tuple[float | None, float | None]:
        """FRESH valve calibration step counts (lines 3325-3326 position).

        ``(closing_steps, idle_steps)`` for the A3 valve-stuck advisory —
        read AFTER the save checkpoint await, so they stay positioned reads.
        """
        return self.read(self.valve_closing_steps), self.read(self.valve_idle_steps)
