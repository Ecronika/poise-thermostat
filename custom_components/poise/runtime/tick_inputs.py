"""Immutable per-tick HA input snapshot.

``TickInputs`` is captured by ``ha/input_reader.InputReader.snapshot()`` and is
the hass-free pipeline's view of Home Assistant.

``snapshot()`` bundles EXACTLY the contiguous read block BEFORE the tick's
first ``await`` (the forecast fetch). A state change during an ``await``
(forecast, service calls, save, notify) is visible to every SUBSEQUENT read,
and that must stay observable — so every read that sits AFTER an ``await``
stays a *positioned* reader call at exactly its place in the tick:

* the central actuator read after the forecast await —
  ``InputReader.read_actuator() -> ActuatorSnapshot``,
* the presence/occupancy tristates after the forecast await —
  ``InputReader.read_presence() -> PresenceSnapshot``,
* the ext-temp feed target's availability —
  ``InputReader.ext_feed_target_ok()``,
* the TRV sensor-select state in the write path —
  ``InputReader.ext_select_state()``,
* the valve calibration steps after the save checkpoint —
  ``InputReader.valve_steps()``.

``TickInputs`` therefore carries only the pre-first-await segment: the
room/climate sensors, the window contacts, the actuator's capability view and
the device-guard values that ``_emit_health_issues`` reads.

The weather forecast is deliberately NOT part of this snapshot: it is fetched
mid-prepare via the ``ForecastRequest`` handshake only when the optimal-start
decision asks for it, with the tick-current horizon.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SensorValue:
    """A numeric sensor read plus its provenance.

    ``value`` is the finite-parsed state (NaN/Inf are rejected at the
    boundary). ``age_s`` is the seconds since ``last_changed`` where the freeze
    watchdog needs it — ``last_changed`` on purpose, because a stuck sensor
    re-publishing the SAME value still bumps ``last_updated``, so only
    ``last_changed`` ages; it stays ``None`` for sensors whose age is never
    consulted. ``entity_id`` names the source for repair-issue placeholders;
    ``None`` when the input is not configured.
    """

    value: float | None
    age_s: float | None = None
    entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class ActuatorCapabilitySnapshot:
    """The PRE-first-await view of the climate actuator.

    The pre-await segment consumes exactly three things from the actuator:
    ``state`` for the actuator_unavailable health issue (active when the State
    object is missing — ``state is None`` here — or reads ``"unavailable"``);
    ``hvac_modes`` for the capability resolution and the dynamics
    classification's ``"fan_only"`` membership test; and ``max_temp`` for the
    device ceiling.

    Values are RAW: ``hvac_modes`` is ``()`` when absent/empty — the heat-only
    default ``(True, False)`` stays a consumer rule — and ``max_temp`` is
    ``None`` when absent/non-numeric — the ``DEVICE_MAX_C`` fallback stays a
    consumer rule. ``state`` stays a raw string because two different
    availability predicates exist (online: only ``"unavailable"``; the shadow
    block additionally treats ``"unknown"`` as unavailable) and must not be
    collapsed here.

    Deliberately NOT the full :class:`ActuatorSnapshot`: the central actuator
    read happens AFTER the forecast await, and a device change during that
    await is observable — e.g. ``hvac_modes`` is read once before and once
    after the await, from two different State objects. That asymmetry is
    conserved by keeping the post-await read a positioned
    ``InputReader.read_actuator()`` call.
    """

    state: str | None
    hvac_modes: tuple[str, ...]
    max_temp: float | None


@dataclass(frozen=True, slots=True)
class ActuatorSnapshot:
    """Everything the tick reads from the actuator's central State object.

    Captured AFTER the forecast await by ``InputReader.read_actuator()`` from
    ONE ``states.get`` — every later attribute access in the tick reads the
    SAME immutable State object captured there, never a fresh read; one
    snapshot object models that exactly.

    Field sources: ``state`` feeds the online gate; ``hvac_modes`` the
    mode-nudge/adoption support checks; ``actual_setpoint`` (the
    ``temperature`` attribute) and ``target_temperature_step`` the write/echo
    comparison; ``min_temp``/``max_temp`` are the RAW device limits — the
    ``DEVICE_MAX_C`` fallback and the "no min -> skip the SAFETY floor clamp"
    rule are pipeline decisions, not read-time defaults (``_device_min`` sits
    in the same await-free window, so folding it into this snapshot is
    equivalent); ``hvac_action``, ``fan_mode`` and ``fan_modes`` feed the
    fan/PMV shadows; ``context_id`` is the actuator state's originating context
    for own-write echo detection; ``current_temperature`` is the device's own
    sensor reading for the ADR-0056 reference-offset shadow — parsed with a
    plain ``float()`` (``TypeError``/``ValueError`` -> ``None``, no
    availability gate), NOT with the finite parser.
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
        """Online gate: a never-registered entity (``state is None``) and an
        offline device (``"unavailable"``) both report no trustworthy
        setpoint — writes into either would storm a dead device. Any other
        state, including ``"off"``, is online."""
        return self.state is not None and self.state != "unavailable"


@dataclass(frozen=True, slots=True)
class BinarySensorSnapshot:
    """One binary contact read (the window sensors).

    ``is_on`` is ``None`` exactly when ``available`` is ``False`` (ADR-0041
    §5): a contact that dropped off must stay distinguishable from a confirmed
    "closed", or a dead window sensor silently holds the zone in full heating.
    The OR-across-contacts and failsafe evaluation stay pure in the pipeline.
    """

    entity_id: str
    is_on: bool | None
    available: bool


@dataclass(frozen=True, slots=True)
class PresenceSnapshot:
    """Resolved presence tristates, one entry per configured entity.

    NOT part of :class:`TickInputs`: the presence entities are read AFTER the
    forecast await, so ``InputReader.read_presence()`` stays a positioned call
    at that place in the tick. Both reads sit in the same await-free window, so
    merging them into one snapshot is equivalent.

    The reader resolves each entity state to ``True``/``False``/``None``: a
    person/device_tracker reporting a named zone is a confident "not home";
    any other odd state stays unresolved ``None``. ``home`` feeds the ADR-0058
    house gate, ``occupancy`` the room presence level. ``any_present`` consumes
    both order-independently; the reader still keeps configuration order for
    stable diagnostics.
    """

    home: tuple[bool | None, ...]
    occupancy: tuple[bool | None, ...]


@dataclass(frozen=True, slots=True)
class DeviceGuardSnapshot:
    """Pre-first-await values of the auto-discovered device-guard entities.

    Discovery itself stays in the reader; this snapshot carries what the
    pre-await health block consumes: ``sched_active``/``fault_active`` — the
    schedule/fault entity reports "on"; ``battery`` — the battery percentage
    for the low-battery issue; ``adaptive_mode`` — the RAW state of the
    device's adaptive/smart loop entity (a switch reads "on", a select the
    option name; the evaluation stays a consumer rule); ``ext_temp_number`` —
    the discovered external-temperature number's entity id (the number is
    write-only, so there is no value to snapshot).

    Deliberately NOT here (read after awaits, so they stay positioned reader
    calls): the feed target's per-tick availability (after the forecast await —
    ``ext_feed_target_ok()``), the TRV sensor-select state (after the
    mode/setpoint awaits — ``ext_select_state()``) and the valve calibration
    step counts (after the save await — ``valve_steps()``). The discovered
    valve position number is never read by the tick, so it has no field.
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
    intervals, also unifying the pre-await learn/observe anchors), ``now_wall``
    the epoch wall-clock at snapshot time (also the sensor-age anchor) — one
    read each, so every pre-await consumer shares the same instant; clock calls
    AFTER the first await stay untouched. ``local_minute`` is minutes since
    local midnight for the comfort schedule; ``local_day_ordinal`` is the local
    calendar day's ordinal for the running-mean and seasonless observers
    (``dt_util.now().toordinal()``); ``sun_elevation`` comes from ``sun.sun``
    for the solar estimate.

    Boundary (see the module docstring): presence, the central actuator read
    and the select/valve reads are NOT fields here — they happen after awaits
    and remain positioned ``InputReader`` calls.
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
