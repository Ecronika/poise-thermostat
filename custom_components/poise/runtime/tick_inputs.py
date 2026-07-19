"""Immutable per-tick HA input snapshot (refactoring plan, section 2).

One ``TickInputs`` is captured at tick start by the future
``ha/input_reader.InputReader`` (plan phase 4) and is the only view of Home
Assistant the hass-free ``ZoneRuntime`` ever sees. Freezing all reads into a
single value object pins two invariants:

* every entity is read exactly once per tick — the pipeline can never observe
  a mid-tick state change (the plan explicitly retires today's double-read of
  the actual setpoint in the frost-rescue branch, section 5.5), and
* the domain tick is replayable — inputs plus prior runtime state fully
  determine the resulting plan (the phase-0 golden tests rely on this).

The weather forecast is deliberately NOT part of this snapshot: it is fetched
mid-prepare via the ``ForecastRequest`` handshake (plan finding 5) only when
the optimal-start decision asks for it, with the tick-current horizon.

Phase-1 scope: type definitions only — no production code imports this module
yet, so introducing it cannot change behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SensorValue:
    """A numeric sensor read plus its provenance.

    Mirrors what the coordinator reads per sensor today: the finite-parsed
    state (``_read``, coordinator.py lines 1359-1362 — NaN/Inf are rejected
    at the boundary, C1) and, where the freeze watchdog needs it, the seconds
    since ``last_changed`` (``_sensor_age``, lines 1364-1374; ``last_changed``
    on purpose — a stuck sensor re-publishing the SAME value still bumps
    ``last_updated``, so only ``last_changed`` ages). ``age_s`` stays ``None``
    for sensors whose age is never consulted. ``entity_id`` names the source
    for repair-issue placeholders; ``None`` when the input is not configured.
    """

    value: float | None
    age_s: float | None = None
    entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class ActuatorSnapshot:
    """Everything one tick reads from the climate actuator's State object.

    Field sources (coordinator.py): ``state`` feeds the F2 online gate (lines
    2429-2434); ``hvac_modes`` the capability and dynamics classification
    (lines 2131-2161); ``actual_setpoint`` (the ``temperature`` attribute) and
    ``target_temperature_step`` the write/echo comparison (lines 2965-2973);
    ``min_temp``/``max_temp`` are the RAW device limits — the ``DEVICE_MAX_C``
    fallback and the "no min -> skip the SAFETY floor clamp" rule (P3-1) are
    pipeline decisions, not read-time defaults; ``hvac_action``, ``fan_mode``
    and ``fan_modes`` feed the fan/PMV shadows (lines 2565-2598);
    ``context_id`` is the actuator state's originating context for own-write
    echo detection (V2, lines 2794-2801).
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

    @property
    def online(self) -> bool:
        """F2 gate: a never-registered entity (``state is None``) and an
        offline device (``"unavailable"``) both report no trustworthy
        setpoint — writes into either would storm a dead device (coordinator
        lines 2429-2434). Any other state, including ``"off"``, is online."""
        return self.state is not None and self.state != "unavailable"


@dataclass(frozen=True, slots=True)
class BinarySensorSnapshot:
    """One binary contact read (the window sensors today).

    ``is_on`` is ``None`` exactly when ``available`` is ``False``: F4a /
    ADR-0041 §5 — a contact that dropped off must stay distinguishable from a
    confirmed "closed", or a dead window sensor silently holds the zone in
    full heating. The OR-across-contacts and failsafe evaluation stay pure in
    the pipeline (``_window_open``, coordinator.py lines 1380-1403).
    """

    entity_id: str
    is_on: bool | None
    available: bool


@dataclass(frozen=True, slots=True)
class PresenceSnapshot:
    """Resolved presence tristates, one entry per configured entity.

    The reader resolves each entity state to ``True``/``False``/``None`` with
    the F8 rule (a person/device_tracker reporting a named zone is a
    confident "not home"; any other odd state stays unresolved ``None``) —
    coordinator.py lines 2254-2273. ``home`` feeds the ADR-0058 house gate
    (lines 2275-2284), ``occupancy`` the room presence level (lines
    2353-2401). ``any_present`` consumes both order-independently; the reader
    still keeps configuration order for stable diagnostics.
    """

    home: tuple[bool | None, ...]
    occupancy: tuple[bool | None, ...]


@dataclass(frozen=True, slots=True)
class DeviceGuardSnapshot:
    """Per-tick values of the auto-discovered device-guard entities.

    Discovery itself (``_resolve_device_guards``, coordinator.py lines
    1216-1272) stays in the reader; this snapshot carries what the tick
    consumes (plan section 3, "Device-Guard-Discovery" + the
    ``_emit_health_issues`` split): ``sched_active``/``fault_active`` — the
    schedule/fault entity reports "on" (lines 1874-1908); ``battery`` — the
    battery percentage for the low-battery issue (lines 1909-1915);
    ``adaptive_mode`` — the RAW state of the device's adaptive/smart loop
    entity (R1: a switch reads "on", a select the option name; the
    evaluation stays pure in the pipeline, lines 1884-1899);
    ``ext_temp_number`` — the discovered external-temperature number's entity
    id (the number is write-only, so there is no value to snapshot; per-tick
    availability is read against the resolved feed target, lines 2335-2340);
    ``sensor_select_state`` — the raw state of the TRV's sensor-source select
    driving the switch-to-external decision (lines 3197-3199);
    ``valve_closing_steps``/``valve_idle_steps`` — calibration step counts
    for the valve-stuck advisory (A3, lines 3502-3515). The discovered valve
    position number is never read by the tick today, so it has no field.
    """

    sched_active: bool
    fault_active: bool
    battery: float | None
    adaptive_mode: str | None
    ext_temp_number: str | None
    sensor_select_state: str | None
    valve_closing_steps: float | None
    valve_idle_steps: float | None


@dataclass(frozen=True, slots=True)
class TickInputs:
    """The complete immutable HA snapshot one domain tick runs on.

    ``now_mono`` is the tick's monotonic anchor (learning/write-throttle
    intervals), ``now_wall`` the epoch wall-clock (hold expiries, persisted
    timestamps) — one read each, so every consumer inside the tick shares the
    same instant (plan section 5.2, "Uhr vereinheitlichen").
    ``local_minute`` is minutes since local midnight for the comfort schedule
    (``_local_minute``, coordinator.py lines 1376-1378); ``sun_elevation``
    comes from ``sun.sun`` for the shading shadow (lines 1433-1438).
    """

    now_mono: float
    now_wall: float
    local_minute: int
    sun_elevation: float | None
    room: SensorValue
    outdoor: SensorValue
    humidity: SensorValue
    trm: SensorValue
    mrt: SensorValue
    irradiance: SensorValue
    windows: tuple[BinarySensorSnapshot, ...]
    presence: PresenceSnapshot
    actuator: ActuatorSnapshot
    device_guards: DeviceGuardSnapshot
