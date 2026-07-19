"""Immutable per-tick HA input snapshot (refactoring plan, section 2).

``TickInputs`` is captured by ``ha/input_reader.InputReader.snapshot()`` (plan
phase 4) and is the hass-free pipeline's view of Home Assistant.

Phase-4 scope note (binding, plan phase 4): ``snapshot()`` bundles EXACTLY the
contiguous read block BEFORE the tick's first ``await`` (the forecast fetch,
coordinator.py line 2064). Today a state change during an ``await`` (forecast,
service calls, save, notify) is visible to every SUBSEQUENT read, and that
must stay observable — so every read that sits AFTER an ``await`` today stays
a *positioned* reader call at exactly its current place in the tick:

* the central actuator read (line 2250, after the forecast await) —
  ``InputReader.read_actuator() -> ActuatorSnapshot``,
* the presence/occupancy tristates (lines 2096/2181, after the forecast
  await) — ``InputReader.read_presence() -> PresenceSnapshot``,
* the ext-temp feed target's availability (line 2159) —
  ``InputReader.ext_feed_target_ok()``,
* the TRV sensor-select state in the write path (line 3019) —
  ``InputReader.ext_select_state()``,
* the valve calibration steps after the save checkpoint (lines 3325-3326) —
  ``InputReader.valve_steps()``.

Consolidating ALL reads into one snapshot per tick is deliberately reserved
for the phase-6 prepare/resume structure. Until then ``TickInputs`` carries
only the pre-first-await segment (lines 1810-2063): the room/climate sensors,
the window contacts, the actuator's capability view and the device-guard
values that ``_emit_health_issues`` reads.

The weather forecast is deliberately NOT part of this snapshot: it is fetched
mid-prepare via the ``ForecastRequest`` handshake (plan finding 5) only when
the optimal-start decision asks for it, with the tick-current horizon.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SensorValue:
    """A numeric sensor read plus its provenance.

    Mirrors what the coordinator reads per sensor today: the finite-parsed
    state (``_read``, coordinator.py lines 1183-1186 — NaN/Inf are rejected
    at the boundary, C1) and, where the freeze watchdog needs it, the seconds
    since ``last_changed`` (``_sensor_age``, lines 1188-1198; ``last_changed``
    on purpose — a stuck sensor re-publishing the SAME value still bumps
    ``last_updated``, so only ``last_changed`` ages). ``age_s`` stays ``None``
    for sensors whose age is never consulted. ``entity_id`` names the source
    for repair-issue placeholders; ``None`` when the input is not configured.
    """

    value: float | None
    age_s: float | None = None
    entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class ActuatorCapabilitySnapshot:
    """The PRE-first-await view of the climate actuator (phase-4 split).

    The pre-await segment consumes exactly three things from the actuator:
    ``state`` for the actuator_unavailable health issue (coordinator.py lines
    1680-1686: issue is active when the State object is missing — ``state is
    None`` here — or reads ``"unavailable"``); ``hvac_modes`` for the
    capability resolution (lines 1952 -> 1229-1234) and the dynamics
    classification's ``"fan_only"`` membership test (lines 1961-1970); and
    ``max_temp`` for the device ceiling (lines 1982 -> 1236-1242).

    Values are RAW: ``hvac_modes`` is ``()`` when absent/empty — the
    heat-only default ``(True, False)`` stays a consumer rule — and
    ``max_temp`` is ``None`` when absent/non-numeric — the ``DEVICE_MAX_C``
    fallback stays a consumer rule. ``state`` stays a raw string because two
    different availability predicates exist (F2 online: only
    ``"unavailable"``; the shadow block additionally treats ``"unknown"`` as
    unavailable) and must not be collapsed here.

    Deliberately NOT the full :class:`ActuatorSnapshot`: the central actuator
    read (line 2250) happens AFTER the forecast await, and a device change
    during that await is observable today — e.g. ``hvac_modes`` is read once
    before (line 1952) and once after (line 2519) the await, from two
    different State objects. That asymmetry is conserved by keeping the
    post-await read a positioned ``InputReader.read_actuator()`` call.
    """

    state: str | None
    hvac_modes: tuple[str, ...]
    max_temp: float | None


@dataclass(frozen=True, slots=True)
class ActuatorSnapshot:
    """Everything the tick reads from the actuator's central State object.

    Captured at today's line-2250 position (AFTER the forecast await) by
    ``InputReader.read_actuator()`` from ONE ``states.get`` — every later
    attribute access in the tick (lines 2790/2793, 3082-3083, 3239-3273,
    3428-3429, 3641-3643) reads the SAME immutable State object captured
    there, never a fresh read; one snapshot object models that exactly.

    Field sources (coordinator.py): ``state`` feeds the F2 online gate (lines
    2250-2255); ``hvac_modes`` the mode-nudge/adoption support checks (line
    2519); ``actual_setpoint`` (the ``temperature`` attribute) and
    ``target_temperature_step`` the write/echo comparison (lines 2790-2793);
    ``min_temp``/``max_temp`` are the RAW device limits — the ``DEVICE_MAX_C``
    fallback and the "no min -> skip the SAFETY floor clamp" rule (P3-1) are
    pipeline decisions, not read-time defaults (``_device_min`` at line 2325
    sits in the same await-free window as line 2250, so folding it into this
    snapshot is equivalent); ``hvac_action``, ``fan_mode`` and ``fan_modes``
    feed the fan/PMV shadows (lines 2351-2413); ``context_id`` is the
    actuator state's originating context for own-write echo detection (V2,
    lines 2618-2621); ``current_temperature`` is the device's own sensor
    reading for the ADR-0056 reference-offset shadow (lines 3428-3434) —
    parsed with a plain ``float()`` (``TypeError``/``ValueError`` -> ``None``,
    no availability gate) exactly as today, NOT with the finite parser.
    """

    state: str | None
    hvac_modes: tuple[str, ...]
    actual_setpoint: float | None
    target_temperature_step: float | None
    min_temp: float | None
    max_temp: float | None
    hvac_action: str | None
    fan_mode: str | None
    fan_modes: tuple[str, ...]
    context_id: str | None
    current_temperature: float | None

    @property
    def online(self) -> bool:
        """F2 gate: a never-registered entity (``state is None``) and an
        offline device (``"unavailable"``) both report no trustworthy
        setpoint — writes into either would storm a dead device (coordinator
        lines 2250-2255). Any other state, including ``"off"``, is online."""
        return self.state is not None and self.state != "unavailable"


@dataclass(frozen=True, slots=True)
class BinarySensorSnapshot:
    """One binary contact read (the window sensors today).

    ``is_on`` is ``None`` exactly when ``available`` is ``False``: F4a /
    ADR-0041 §5 — a contact that dropped off must stay distinguishable from a
    confirmed "closed", or a dead window sensor silently holds the zone in
    full heating. The OR-across-contacts and failsafe evaluation stay pure in
    the pipeline (``_window_open``, coordinator.py lines 1204-1227).
    """

    entity_id: str
    is_on: bool | None
    available: bool


@dataclass(frozen=True, slots=True)
class PresenceSnapshot:
    """Resolved presence tristates, one entry per configured entity.

    NOT part of :class:`TickInputs` in phase 4: the presence entities are
    read AFTER the forecast await today (home at line 2096, occupancy at line
    2181), so ``InputReader.read_presence()`` stays a positioned call at that
    place in the tick. Both reads sit in the same await-free window, so
    merging them into one snapshot is equivalent.

    The reader resolves each entity state to ``True``/``False``/``None`` with
    the F8 rule (a person/device_tracker reporting a named zone is a
    confident "not home"; any other odd state stays unresolved ``None``) —
    coordinator.py lines 2075-2094. ``home`` feeds the ADR-0058 house gate
    (line 2096), ``occupancy`` the room presence level (lines 2181-2196).
    ``any_present`` consumes both order-independently; the reader still keeps
    configuration order for stable diagnostics.
    """

    home: tuple[bool | None, ...]
    occupancy: tuple[bool | None, ...]


@dataclass(frozen=True, slots=True)
class DeviceGuardSnapshot:
    """Pre-first-await values of the auto-discovered device-guard entities.

    Discovery itself (``_resolve_device_guards``, coordinator.py lines
    1040-1096) stays in the reader; this snapshot carries what the pre-await
    health block (``_emit_health_issues``, lines 1673-1748) consumes:
    ``sched_active``/``fault_active`` — the schedule/fault entity reports
    "on" (lines 1697/1722); ``battery`` — the battery percentage for the
    low-battery issue (line 1733); ``adaptive_mode`` — the RAW state of the
    device's adaptive/smart loop entity (R1: a switch reads "on", a select
    the option name; the evaluation stays a consumer rule, lines 1705-1720);
    ``ext_temp_number`` — the discovered external-temperature number's entity
    id (the number is write-only, so there is no value to snapshot).

    Deliberately NOT here (phase-4 split — these are read after awaits and
    stay positioned reader calls): the feed target's per-tick availability
    (line 2159, after the forecast await — ``ext_feed_target_ok()``), the
    TRV sensor-select state (line 3019, after the mode/setpoint awaits —
    ``ext_select_state()``) and the valve calibration step counts (lines
    3325-3326, after the save await — ``valve_steps()``). The discovered
    valve position number is never read by the tick today, so it has no
    field.
    """

    sched_active: bool
    fault_active: bool
    battery: float | None
    adaptive_mode: str | None
    ext_temp_number: str | None


@dataclass(frozen=True, slots=True)
class TickInputs:
    """The immutable pre-first-await HA snapshot one domain tick starts on.

    ``now_mono`` is the tick's monotonic anchor (learning/write-throttle
    intervals — today's line 1873, also unifying the pre-await learn/observe
    anchors at lines 1310/1358/1397), ``now_wall`` the epoch wall-clock at
    snapshot time (also the sensor-age anchor, line 1198) — one read each, so
    every pre-await consumer shares the same instant (plan section 5.2, "Uhr
    vereinheitlichen"; clock calls AFTER the first await stay untouched).
    ``local_minute`` is minutes since local midnight for the comfort schedule
    (``_local_minute``, coordinator.py lines 1200-1202 via line 2047);
    ``local_day_ordinal`` is the local calendar day's ordinal for the
    running-mean and seasonless observers (``dt_util.now().toordinal()``,
    lines 1893/1404); ``sun_elevation`` comes from ``sun.sun`` for the solar
    estimate (lines 1257-1262).

    Phase-4 boundary (see the module docstring): presence, the central
    actuator read and the select/valve reads are NOT fields here — they
    happen after awaits today and remain positioned ``InputReader`` calls.
    """

    now_mono: float
    now_wall: float
    local_minute: int
    local_day_ordinal: int
    sun_elevation: float | None
    room: SensorValue
    outdoor: SensorValue
    humidity: SensorValue
    trm: SensorValue
    mrt: SensorValue
    irradiance: SensorValue
    windows: tuple[BinarySensorSnapshot, ...]
    actuator: ActuatorCapabilitySnapshot
    device_guards: DeviceGuardSnapshot
