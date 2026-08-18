"""The single READING Home-Assistant adapter.

``InputReader`` owns every ``hass.states.get`` primitive of the coordinator
plus the device-guard registry discovery.  Two kinds of API, mirroring the
constraint that a module boundary may move but read POSITIONS in the tick
must not:

* ``snapshot() -> TickInputs`` bundles the contiguous read block BEFORE the
  tick's first ``await`` (the forecast fetch).  Within that segment Home
  Assistant's single-threaded event loop guarantees no state can change
  between reads, so merging them into one snapshot — including collapsing the
  segment's four actuator reads into ONE — is provably equivalent.  The
  segment's ad-hoc clock calls are unified onto the snapshot instants
  (``now_mono``/``now_wall``/``local_minute``/``local_day_ordinal``); the
  sub-millisecond divergence this removes is unobservable.

* Positioned single reads stay separate named methods because they run AFTER
  an ``await``, where a state change during the await is observable and must
  remain so: ``read_presence()``/``ext_feed_target_ok()`` (after the forecast
  await), ``actuator_state()``/``read_actuator()`` (the central actuator read;
  also the unavailable-path safe-state read after the dirty-flush await),
  ``ext_select_state()`` (in the write path after the mode/setpoint awaits)
  and ``valve_steps()`` (after the save checkpoint).  Clock calls after awaits
  are untouched by this module.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, Final

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..clock import Clock
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
    """Numeric state parse.

    ``unknown``/``unavailable``/empty read as ``None``; ``parse_finite``
    rejects NaN/Inf at the boundary.
    """
    if state is None or state.state in _INVALID:
        return None
    return parse_finite(state.state)


def parse_attr_number(state: State | None, key: str) -> float | None:
    """Numeric attribute parse.

    Excludes ONLY ``state == "unavailable"`` — attributes are read even while
    the state is ``"unknown"`` (deliberately narrower than
    :func:`parse_state_number`; e.g. a just-restarted climate device reports
    its setpoint before its mode).
    """
    if state is None or state.state == "unavailable":
        return None
    return parse_finite(state.attributes.get(key))


def finite_attr_num(value: Any) -> float | None:
    """Strict isinstance-numeric attribute capture, rejecting NaN/Inf (B.5).

    Deliberately NOT :func:`parse_finite`: these raw capability reads keep
    their strict numeric-type semantics (no numeric strings) — only non-finite
    garbage is rejected on top, so a NaN device limit reads as "absent"
    instead of silently fail-opening the SAFETY clamps downstream.
    """
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def actuator_snapshot(state: State | None) -> ActuatorSnapshot:
    """Freeze one already-captured actuator State into an ActuatorSnapshot.

    One-object rule: every attribute access after the central actuator read
    reads the SAME immutable State object, never a fresh ``states.get``.
    Per-field parse semantics: ``actual_setpoint``/``target_temperature_step``
    via the attribute-number rule; ``current_temperature`` via ``parse_finite``
    directly on the attribute (keeps its NO-availability-gate contract, gains
    the finite rejection — a NaN there used to poison the ADR-0056 deviation
    EMA until restart, review B.5); ``min_temp``/``max_temp`` via the strict
    isinstance-numeric capture with finite rejection (the ``None``/
    ``DEVICE_MAX_C`` fallback rules stay with the consumer — a non-finite
    limit must read as "absent", never fail-open the SAFETY clamps
    downstream).
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
    hvac_action = attrs.get("hvac_action")
    fan_mode = attrs.get("fan_mode")
    # parse_finite directly on the attribute: current_temperature keeps its
    # NO-availability-gate contract (unlike parse_attr_number), gaining only
    # the finite rejection (review B.5).
    current = parse_finite(attrs.get("current_temperature"))
    return ActuatorSnapshot(
        state=state.state,
        hvac_modes=tuple(str(m) for m in (attrs.get("hvac_modes") or ())),
        actual_setpoint=parse_attr_number(state, "temperature"),
        # HA serialises ClimateEntity.target_temperature_step under the
        # ATTR_TARGET_TEMP_STEP key "target_temp_step", not the property name.
        target_temperature_step=parse_attr_number(state, "target_temp_step"),
        min_temp=finite_attr_num(attrs.get("min_temp")),
        max_temp=finite_attr_num(attrs.get("max_temp")),
        hvac_action=str(hvac_action) if hvac_action is not None else None,
        fan_mode=str(fan_mode) if fan_mode is not None else None,
        fan_modes=tuple(str(m) for m in (attrs.get("fan_modes") or ())),
        context_id=state.context.id if state.context is not None else None,
        current_temperature=current,
    )


# Minimum monotonic spacing between two device-guard discovery attempts,
# indexed by the number of attempts already made: attempt 2 runs no earlier
# than 60 s after attempt 1, attempt 3 no earlier than 300 s after attempt 2.
# The tuple's LENGTH is the retry budget (see ``_GUARD_MAX_ATTEMPTS``).
#
# The two numbers are Home Assistant's own setup timings, not taste.
# ``homeassistant.setup`` warns at ``SLOW_SETUP_WARNING`` (10 s) that an
# integration's setup is slow and waits at most ``SLOW_SETUP_MAX_WAIT``
# (300 s) before giving up on it — both verified against the two pinned HA
# targets (2025.10.1 and 2026.8.2).  So one minute after the first tick every
# integration that sets up normally has registered its entities, and 300 s
# after that even the slowest still-legal setup has either finished or been
# aborted.  Three attempts spanning ~6 minutes therefore cover the entire
# "Home Assistant is still coming up" window; a miss that outlives it is not
# transient any more and a reload — which rebuilds this reader — is its cure.
#
# Cost ceiling: three registry lookups per zone per reload, plus one float
# comparison per tick while unresolved.  With TICK_INTERVAL_S = 60 s an
# unguarded retry would instead cost one lookup per tick, forever.
_GUARD_RETRY_SPACING_S: Final[tuple[float, ...]] = (60.0, 300.0)
_GUARD_MAX_ATTEMPTS: Final = len(_GUARD_RETRY_SPACING_S) + 1


class InputReader:
    """Owns all state reads + guard discovery for one zone.

    The discovered guard entity ids are plain public attributes so the
    coordinator can proxy them and tests can pin them — pinned values survive
    re-resolution because discovery is idempotent.
    """

    def __init__(
        self, hass: HomeAssistant, structure: ZoneStructure, clock: Clock
    ) -> None:
        self._hass = hass
        self._structure = structure
        self._clock = clock
        # Device-guard discovery results.
        self.guards_resolved = False
        # Bounded-retry bookkeeping for that discovery (see
        # resolve_device_guards): attempts made so far and the monotonic
        # instant of the last one.
        self._guard_attempts = 0
        self._guard_last_attempt = 0.0
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
        """Follow a hot-applied presence-list change.

        The presence entity lists are the ONE options-owned, hot-applied piece
        of the otherwise reload-only :class:`ZoneStructure`; without this sync
        :meth:`read_presence` would keep reading the setup-time lists after an
        options submit.
        """
        self._structure = replace(
            self._structure,
            presence_home_entities=tuple(home),
            occupancy_entities=tuple(occupancy),
        )

    # ------------------------------------------------------------------
    # registry discovery
    # ------------------------------------------------------------------

    def resolve_device_guards(self, *, now: float | None = None) -> None:
        """Find schedule/fault/battery entities on the actuator's device.

        Runs pre-first-await via the health block on every tick until it
        settles.  ``guards_resolved`` is the terminal gate and keeps its
        external meaning — "no further attempt will ever be made": a manually
        pinned entity is never overwritten by a later re-resolution, and a
        broken registry can never become a per-tick retry storm.  That storm
        protection used to be bought by setting the flag BEFORE the try, which
        also threw away every merely TRANSIENT failure (registry not populated
        yet, the actuator's own integration still starting) until the next
        reload.  A classified, bounded retry buys the same protection without
        that price:

        * :meth:`_discover_device_guards` reports whether its outcome is
          FINAL.  A final outcome (a device was scanned, or the registry gave
          a definitive negative) sets the gate immediately — exactly today's
          semantics for every case that is not a race.
        * A non-final outcome (the registry raised, or the actuator is in
          neither the registry nor the state machine) is retried, at most
          ``_GUARD_MAX_ATTEMPTS`` times and never closer together than
          ``_GUARD_RETRY_SPACING_S``.  When the budget is spent the gate is
          set anyway, so a permanently broken registry costs a fixed three
          lookups and then one float comparison per tick — never a lookup.

        A failure is swallowed either way (guard resolution must never break
        setup) and the neutral guard defaults stay in effect.  Logging
        escalates once per STAGE, never per attempt: the first failure keeps
        today's debug traceback, giving up adds one info line.

        ``now`` is the caller's monotonic anchor — ``snapshot()`` passes its
        unified instant (same contract as :meth:`sensor_age`), ad-hoc callers
        get a fresh read of the injected clock.
        """
        if self.guards_resolved:
            return
        anchor = self._clock.monotonic() if now is None else now
        if self._guard_attempts:
            # In range because the branch below sets the terminal gate as soon
            # as the budget is spent, so _guard_attempts never reaches
            # _GUARD_MAX_ATTEMPTS here.
            spacing = _GUARD_RETRY_SPACING_S[self._guard_attempts - 1]
            if anchor - self._guard_last_attempt < spacing:
                return
        self._guard_attempts += 1
        self._guard_last_attempt = anchor
        try:
            final = self._discover_device_guards()
        except Exception:  # noqa: BLE001 - guard resolution must never break setup
            final = False
            if self._guard_attempts == 1:
                _LOGGER.debug("Poise: device-guard resolution failed", exc_info=True)
        if final:
            self.guards_resolved = True
            return
        if self._guard_attempts >= _GUARD_MAX_ATTEMPTS:
            self.guards_resolved = True
            _LOGGER.info(
                "Poise: device-guard discovery for %s gave up after %d attempts; "
                "the neutral guard defaults stay in effect until the next reload",
                self._structure.actuator,
                self._guard_attempts,
            )

    def _discover_device_guards(self) -> bool:
        """One discovery pass; ``True`` when its outcome is FINAL.

        "Final" separates a definitive registry answer from a race with a
        still-starting integration, so only the latter is worth retrying:

        * a registry entry WITH a ``device_id`` — the sibling scan ran, which
          is the success case even when the device owns no guard entity at
          all (the registry answered about a real device);
        * a registry entry WITHOUT a ``device_id`` — the entity was registered
          device-less.  The device link is written when the platform registers
          the entity, so re-asking this same entry cannot change the answer;
        * NO registry entry but a live State — permanent.
          ``EntityPlatform._async_add_entity`` creates the registry entry
          BEFORE ``add_to_platform_finish`` writes the state (verified on both
          pinned HA targets), so an actuator that already has a state and
          still no entry carries no ``unique_id`` and will never get one.
          This is the ordinary ``generic_thermostat``/template-actuator setup,
          and burning the retry budget on it would be pure waste;
        * NO registry entry and NO State — the only genuinely transient miss:
          nothing has added this entity yet, so it may still be on its way in.
          NOT final.

        Registry errors are not classified here at all; they propagate to
        :meth:`resolve_device_guards`, which treats them as transient.
        """
        reg = er.async_get(self._hass)
        ent = reg.async_get(self._structure.actuator)
        if ent is None:
            # Existence probe only — the sole extra actuator read in the
            # pre-await segment, reached at most once per attempt and never
            # after the guards settle.  It consumes existence, not attributes,
            # so snapshot()'s one-object rule is untouched.
            return self._hass.states.get(self._structure.actuator) is not None
        if ent.device_id is None:
            return True
        for e in er.async_entries_for_device(
            reg, ent.device_id, include_disabled_entities=False
        ):
            eid = e.entity_id
            # A device-internal adaptive/smart-temperature loop is orthogonal
            # to the roles below and can be a ``switch.`` OR a ``select.``
            # entity, so detect it independently of the elif chain (a
            # ``select.`` would otherwise be consumed by the sensor-select
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
            elif (
                self.valve_closing_steps is None
                and looks_like_valve_steps(eid) == "closing"
            ):
                self.valve_closing_steps = eid
            elif (
                self.valve_idle_steps is None and looks_like_valve_steps(eid) == "idle"
            ):
                self.valve_idle_steps = eid
        return True

    def configured_ext_temp_signature(
        self, entity_id: str
    ) -> tuple[str | None, str | None]:
        """Registry/state signature of the CONFIGURED ext-temp number.

        device_class from the registry entry (``device_class or
        original_device_class``) with the live state's attribute as fallback,
        same for the unit.  Returns ``(device_class, unit)``; registry errors
        propagate — the caller owns the "a registry miss must never block
        setup" boundary.
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
    # scalar read primitives
    # ------------------------------------------------------------------

    def read(self, entity_id: str | None) -> float | None:
        """Finite-parsed numeric state, ``None`` when unset/invalid."""
        if not entity_id:
            return None
        return parse_state_number(self._hass.states.get(entity_id))

    def attr_number(self, entity_id: str | None, key: str) -> float | None:
        """Finite-parsed numeric ATTRIBUTE of an entity (ADR-0066: the
        weather entity's ``humidity`` feeds the outdoor-humidity ladder)."""
        if not entity_id:
            return None
        return parse_attr_number(self._hass.states.get(entity_id), key)

    def sensor_age(
        self, entity_id: str, *, now: datetime | None = None
    ) -> float | None:
        """Seconds since the sensor's value last CHANGED.

        ``last_changed`` (the value-change time, per the watchdog contract): a
        dead/stuck sensor that keeps re-publishing the SAME value still bumps
        ``last_updated``, so only ``last_changed`` detects "available but
        frozen".  ``snapshot()`` passes its unified wall anchor as ``now``;
        ad-hoc callers get a fresh ``utcnow``.
        """
        state = self._hass.states.get(entity_id)
        if state is None:
            return None
        anchor = dt_util.utcnow() if now is None else now
        return sensor_age_seconds(anchor, state.last_changed)

    def read_windows(self) -> tuple[BinarySensorSnapshot, ...]:
        """Per-contact window reads (pre-first-await).

        ADR-0041 §5 availability rule: a missing State, ``unavailable`` or
        ``unknown`` all mean the contact dropped off (``available=False``,
        ``is_on=None`` — distinguishable from a confirmed "closed"); anything
        else reports ``is_on = (state == "on")``.
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

        Returns ``(sensor_open, sensor_unavailable)``: a dropped contact flags
        ``unavailable`` (the caller falls back to slope/auto-detection instead
        of trusting stale "closed" data), while a confirmed "on" from any
        OTHER still-working contact is trusted regardless (real positive
        evidence beats a sibling's dropout), so this never early-returns.
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
        """(can_heat, can_cool) from a FRESH actuator read.

        Empty/missing ``hvac_modes`` defaults to ``(True, False)`` — assume a
        heat-only TRV.
        """
        act = self._hass.states.get(self._structure.actuator)
        modes = act.attributes.get("hvac_modes") if act else None
        if modes:
            return climate_capability([str(m) for m in modes])
        return True, False

    def device_min(self) -> float | None:
        """The actuator's own ``min_temp`` (a physical write floor), if known.

        Returns ``None`` when absent/non-numeric/non-finite so
        resolve_write_target skips the SAFETY floor clamp entirely (fresh read;
        its tick call site sits in the same await-free window as the central
        actuator read).
        """
        act = self._hass.states.get(self._structure.actuator)
        if act is not None:
            return finite_attr_num(act.attributes.get("min_temp"))
        return None

    def sun_elevation(self) -> float | None:
        """``sun.sun``'s elevation attribute."""
        sun = self._hass.states.get("sun.sun")
        if sun is None:
            return None
        return finite_attr_num(sun.attributes.get("elevation"))

    def tristate(self, entity_id: str | None) -> bool | None:
        """Presence tristate resolution.

        A person/device_tracker reporting a named zone ("Work", "Gym", ...) is
        a resolved, confident "not home" — not a sensor failure.  Any other
        domain's odd/custom state stays genuinely unresolved (None).
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
    # the pre-first-await snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> TickInputs:
        """Bundle the tick's contiguous pre-first-await read block.

        Covers the reads before the forecast await: room, the health block's
        actuator state / room age / guard discovery + guard values, outdoor,
        trm, humidity, sun + irradiance, mrt, the window contacts and the
        actuator's capability view.  Within this await-free segment HA's
        single-threaded loop makes the read order unobservable, so the four
        actuator reads collapse into ONE ``states.get`` here.  The segment's
        clock calls are unified onto the snapshot instants — a sub-ms,
        unobservable divergence.  Everything read after an await stays a
        positioned method of this class (module docstring).
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

        # Health-block reads (the first tick resolves the guards; a merely
        # transient miss gets a bounded, clock-spaced retry on later ticks,
        # then it is idempotent).  The snapshot's own monotonic instant is the
        # retry anchor, so the backoff follows the injected clock like every
        # other duration in the tick.  Guard entity reads only happen once
        # discovered — an un-discovered entity contributes the neutral
        # defaults.
        self.resolve_device_guards(now=now_mono)
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

        # ONE actuator read for the whole pre-await segment (merges the
        # health/capability/dynamics/max reads; raw values — the heat-only and
        # DEVICE_MAX_C defaults stay consumer rules, see
        # ActuatorCapabilitySnapshot).
        act = self._hass.states.get(s.actuator)
        act_max = act.attributes.get("max_temp") if act is not None else None
        actuator = ActuatorCapabilitySnapshot(
            state=act.state if act is not None else None,
            hvac_modes=(
                tuple(str(m) for m in (act.attributes.get("hvac_modes") or ()))
                if act is not None
                else ()
            ),
            max_temp=finite_attr_num(act_max),
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

        Home and occupancy sit in the same await-free window, so one merged
        read is equivalent — but the pair must NOT move before the forecast
        await (a presence flip during the fetch is observable).
        """
        s = self._structure
        return PresenceSnapshot(
            home=tuple(self.tristate(e) for e in s.presence_home_entities),
            occupancy=tuple(self.tristate(e) for e in s.occupancy_entities),
        )

    def actuator_state(self) -> State | None:
        """The raw positioned actuator read.

        Used at the central position (after the forecast await; the online
        gate and every later attribute access consume this ONE object) and at
        the unavailable-path safe-state read (after the conditional
        dirty-flush save await).  Both must observe a device change that
        happened during the preceding await, so this is deliberately NOT part
        of ``snapshot()``.
        """
        return self._hass.states.get(self._structure.actuator)

    def read_actuator(self) -> ActuatorSnapshot:
        """Typed capture of the central actuator read."""
        return actuator_snapshot(self.actuator_state())

    def ext_feed_target_ok(self, entity_id: str | None) -> bool:
        """Availability of the ext-temp feed target (post-forecast-await).

        The number is write-only, so an ``unknown`` state is fine; only
        ``unavailable`` (or a missing/unconfigured entity) means the device is
        offline (ADR-0029).  The caller passes the resolved feed target
        (configured id or the discovered ``ext_temp_auto``).
        """
        state = self._hass.states.get(entity_id) if entity_id else None
        return state is not None and state.state != "unavailable"

    def ext_select_state(self) -> str | None:
        """FRESH state of the TRV's sensor-source select (write-path read).

        Read in the write path after the mode-nudge/setpoint awaits — a select
        change during those service calls is observable and stays so.  ``None``
        when no select was discovered or its State is missing; the caller's
        "switch unless already external/unavailable" decision is unaffected (a
        State's ``state`` string is never ``None``, so ``None`` cannot collide
        with a real state).
        """
        if not self.sensor_select:
            return None
        sel = self._hass.states.get(self.sensor_select)
        return sel.state if sel is not None else None

    def valve_steps(self) -> tuple[float | None, float | None]:
        """FRESH valve calibration step counts.

        ``(closing_steps, idle_steps)`` for the valve-stuck advisory — read
        AFTER the save checkpoint await, so they stay positioned reads.
        """
        return self.read(self.valve_closing_steps), self.read(self.valve_idle_steps)
