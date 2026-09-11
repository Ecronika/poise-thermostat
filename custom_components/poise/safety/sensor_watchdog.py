"""Frozen-sensor watchdog (ADR-0012).

A sensor that stays *available* but stops changing its value (dead battery,
stuck firmware, stalled integration) is a silent failure: control runs on stale
data and the EKF would mislearn from a flat signal. We detect it from the age
of the last value change and react on two fronts: raise a repair issue and pause
learning, and degrade the control output to a safe state — a heat-capable device
holds the health floor (frost/mould, kept by the actuator's own sensor, fail
toward warmth) while a cool-only device is commanded off, so control never chases
a comfort target computed from a dead value.
"""

from __future__ import annotations

from datetime import datetime


def is_frozen(age_s: float | None, threshold_s: float) -> bool:
    """True if the last value change is at least ``threshold_s`` seconds ago.

    ``age_s`` is the seconds since the sensor value last changed (``None`` when
    unknown, e.g. just started — treated as not frozen).
    """
    if age_s is None or threshold_s <= 0.0:
        return False
    return age_s >= threshold_s


def unavailable_safe_engaged(unavailable_s: float | None, threshold_s: float) -> bool:
    """True once the room sensor has been *unavailable* for at least ``threshold_s``.

    A brief drop-out is tolerated (hold the last state); a sustained loss must
    degrade to the same safe state as a frozen sensor — command the frost/mould
    floor so a heat-capable actuator protects the room with its own sensor
    (fail toward warmth). This matters most in external-feed mode, where the lost
    sensor is the room's only signal (review #7). ``None`` (not currently
    unavailable) and a non-positive threshold read as not engaged.
    """
    if unavailable_s is None or threshold_s <= 0.0:
        return False
    return unavailable_s >= threshold_s


def sensor_source_handback_due(*, select_state: str | None, feed_owned: bool) -> bool:
    """True when a TRV's sensor-source select must be handed back to 'internal'.

    The companion of :func:`unavailable_safe_engaged` for a zone in
    external-feed mode (ADR-0029).  The safe state commands the health floor
    and lets the actuator "hold it with its own sensor" -- which is only true
    if the device actually READS its own sensor.  A TRV parked on 'external'
    keeps regulating against the last value we fed it, frozen at the moment the
    room sensor died, so the floor would be enforced against a stale reading:
    the external-feed pendant of the frozen-sensor degradation (ADR-0012).

    ``feed_owned`` gates on OUR claim: only a select this zone actually drives
    is released, never a foreign automation's (the release pendant of the feed
    path's "switch unless already external").  ``select_state`` is the select's
    live state -- 'internal' is already correct (idempotent, no write) and
    'unavailable'/``None`` cannot be written at all.
    """
    return feed_owned and select_state == "external"


def sensor_source_handback_target(
    *,
    select_entity_id: str | None,
    select_state: str | None,
    configured_feed: str | None,
    last_fed: str | None,
) -> str | None:
    """The sensor-source select to release, or ``None`` when none is due.

    The DECISION half of the ADR-0029 release. It lives here rather than in
    ``ha/phase_actuate`` so that module keeps only the dispatch: its ratchet
    row stood six lines under the 1200-total mark and the rule for the next
    growth was "move lines out instead".

    WHY THE RELEASE EXISTS. With the room sensor gone the TRV must fall back
    to its OWN sensor, or the safe state's health floor is enforced against
    the value we fed last -- frozen at the instant the sensor died, so "the
    actuator holds the floor with its own sensor" (the promise of
    :func:`unavailable_safe_engaged`) would be false. It is the external-feed
    pendant of the frozen-sensor degradation (ADR-0012).

    OWNERSHIP. Only a select THIS zone drives is released, never a foreign
    automation's: the explicitly configured feed target (``configured_feed``),
    or -- for an auto-detected one -- the fact that we have actually fed this
    device in this run (``last_fed``). ``last_fed`` is transient by design, so
    a restart INSIDE an outage degrades to the old behaviour (no handback)
    rather than releasing a select that may be someone else's.

    NO RETURN-PATH COUNTERPART is needed: once the sensor is back,
    ``_stage_ext_temp_feed`` re-claims the select on the next tick ("switch
    unless already external") -- which is also why the release must never
    fire for a select we do not drive.
    """
    if select_entity_id is None:
        return None
    due = sensor_source_handback_due(
        select_state=select_state,
        feed_owned=configured_feed is not None or last_fed is not None,
    )
    return select_entity_id if due else None


def sensor_at_heat_source(
    tau_hours: float, identified: bool, *, min_plausible_tau_h: float
) -> bool:
    """True if an *identified* model has an implausibly short time constant.

    A temperature sensor mounted on or near the radiator (e.g. a TRV's internal
    sensor) reacts almost immediately to heating, so the learned 1R1C model gets
    an implausibly small time constant ``tau = 1/alpha`` — a real room is hours,
    a heat-source sensor is minutes. Gated on ``identified`` so we only judge a
    trusted estimate (charter G17, anti-"garbage in").
    """
    return identified and tau_hours < min_plausible_tau_h


def valve_stuck(closing_steps: float | None, *, min_steps: float = 10.0) -> bool:
    """True if a motorised valve looks jammed / un-calibrated (advisory).

    A healthy calibrated TRV reports a substantial closing-step count (e.g. the
    Sonoff TRVZB ~300); a value near zero means calibration failed or the valve
    is mechanically stuck. ``None`` (no telemetry) is treated as not stuck.
    """
    if closing_steps is None:
        return False
    return closing_steps < min_steps


def sensor_age_seconds(now: datetime, last_changed: datetime) -> float:
    """Seconds since the sensor value last changed (F1 feed for ``is_frozen``).

    Pure timestamp arithmetic extracted from the coordinator glue so the
    last-changed-based ageing is unit-testable without a HA runtime (review M13).
    """
    return (now - last_changed).total_seconds()


def frozen_safe_target(frost_floor: float, mold_min: float | None) -> float:
    """Setpoint to command when the room sensor can no longer be trusted (C3/Ü3).

    On a frozen/stale read we must not chase a comfort target computed from a
    dead value (it could overheat, or miscompute the frost floor). Instead we
    degrade to the *health floor* — the higher of frost protection and the
    mould-avoidance minimum — and let the actuator hold it with its own sensor.
    This "fails toward warmth": frost/mould protection is guaranteed without
    trusting our reading. Pure, unit-tested.
    """
    return max(frost_floor, mold_min if mold_min is not None else frost_floor)


def should_learn(
    *,
    window_open: bool,
    frozen: bool,
    heating_failed: bool = False,
    cooling_failed: bool = False,
) -> bool:
    """Learn only when the room signal is trustworthy and the commanded
    conditioning actually works.

    An open window (air mixing) or a frozen sensor (stale value) must pause EKF
    learning so the model is not poisoned (F1/ADR-0012). A confirmed heating
    failure -- the actuator reports running but the room will not warm, e.g. a
    boiler that is off while the TRV valve is open (VTherm #1428) -- must also
    pause it: integrating a flat room curve under u_h~1 would drive ``beta_h``
    toward its lower bound (R3). ``cooling_failed`` is the C.8 pendant: a flat
    curve under u_c~1 (dead compressor, blocked airflow) would corrupt
    ``beta_c`` the same way. Extracted from the coordinator tick so the gate
    itself is tested (review M13); both failure flags are fed from the
    PREVIOUS tick's latch because the verdicts are only known later in the tick.
    """
    return not window_open and not frozen and not heating_failed and not cooling_failed
