"""Pure per-tick resolution helpers extracted from the coordinator glue.

These hold the *decision* logic the coordinator used to inline — source
selection for the shadow estimators (T_rm, solar, MRT) and the final
write-target resolution (window / override / comfort → setpoint + mode + norm
clamp). Keeping them pure makes the trickiest tick logic unit-testable without a
Home Assistant runtime (ADR-0005/0011/0031); the coordinator only reads states
and calls these.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..comfort.norm_compliance import ASR_MAX_ROOM_C
from ..constraints import Constraint, ConstraintKind, resolve_constraints
from ..contracts import Precedence
from ..estimation.solar import clear_sky_normalized, normalize_irradiance


def select_t_rm(
    sensor: float | None, internal: float | None, t_out: float | None
) -> tuple[float | None, str | None]:
    """Running-mean source: external sensor → internal shadow → outdoor fallback."""
    if sensor is not None:
        return sensor, "sensor"
    if internal is not None:
        return internal, "internal"
    return t_out, ("outdoor" if t_out is not None else None)


def select_q_solar(
    elevation: float | None, ghi: float | None
) -> tuple[float, str, float]:
    """Solar input: measured irradiance overrides the always-on clear-sky shadow.

    Returns ``(q_solar_used, source, q_solar_internal)``.
    """
    internal = clear_sky_normalized(elevation) if elevation is not None else 0.0
    if ghi is not None:
        return normalize_irradiance(ghi), "sensor", internal
    if elevation is not None:
        return internal, "internal", internal
    return 0.0, "none", internal


def select_mrt(sensor: float | None, internal: float) -> tuple[float, str]:
    """MRT source: a measured globe/MRT sensor overrides the virtual estimate."""
    if sensor is not None:
        return sensor, "sensor"
    return internal, "internal"


@dataclass(frozen=True, slots=True)
class WriteTarget:
    target: float
    mode: str
    norm_binding: str | None
    binding_precedence: str | None = None
    override_clamped: bool = False


def resolve_write_target(
    *,
    window_open: bool,
    override: float | None,
    heat_sp: float,
    cool_sp: float,
    write_setpoint: float,
    comfort_mode: str,
    frost_floor: float,
    mold_min: float | None,
    device_max: float,
    device_min: float | None = None,
) -> WriteTarget:
    """Final write target: window/override/comfort → setpoint + mode, then the
    unconditional norm envelope (ASR cap + frost/mould floor, skipped when
    cooling) and the device max (ADR-0023/0027).

    ``override_clamped`` reports when a manual setpoint was silently limited by
    the comfort band ``[heat_sp, cool_sp]`` (review V10) — true only when the
    override lies outside it. Inside the comfort window the band is tight so a
    far-off manual value is capped without feedback; the flag surfaces that.

    ``device_min`` (the actuator's own ``min_temp``, when known) is a physical
    SAFETY floor: a device silently holds its minimum, so writing below it makes
    the echo-compare rewrite every tick (review P3-1). The floor is clamped up to
    it in both heating and cooling.
    """
    floor = max(frost_floor, mold_min if mold_min is not None else frost_floor)
    override_clamped = False
    if window_open:
        target, mode = round(floor, 1), "off"
    elif override is not None:
        clamped = min(max(override, heat_sp), cool_sp)
        override_clamped = clamped != override
        target, mode = round(clamped, 1), "manual"
    else:
        target, mode = round(write_setpoint, 1), comfort_mode

    # Unified hard envelope (ADR-0035): device max + (unless cooling) the ASR
    # cap and frost/mould floor, composed with precedence. The device max is a
    # physical SAFETY cap, the norm floor HEALTH, the norm cap COMFORT.
    # M2: a misreported device max *below* the active health floor would win the
    # inversion (SAFETY > HEALTH) and silently defeat frost/mould protection.
    # When heating, clamp the cap up to the floor so health is never undercut —
    # the device still caps its own physical reach; we simply never command less.
    device_cap = max(device_max, floor) if mode != "cool" else device_max
    caps = [Constraint(device_cap, "device_max", ConstraintKind.CAP, Precedence.SAFETY)]
    floors: list[Constraint] = []
    if mode != "cool":
        caps.append(
            Constraint(
                ASR_MAX_ROOM_C, "norm_cap", ConstraintKind.CAP, Precedence.COMFORT
            )
        )
        floors.append(
            Constraint(floor, "norm_floor", ConstraintKind.FLOOR, Precedence.HEALTH)
        )
    if device_min is not None:
        # P3-1: the actuator holds its own min_temp regardless — writing below it
        # just thrashes the echo-compare each tick. Clamp up to it as a physical
        # SAFETY floor, in both heating and cooling.
        floors.append(
            Constraint(
                device_min, "device_min", ConstraintKind.FLOOR, Precedence.SAFETY
            )
        )
    res = resolve_constraints(target, floors + caps)
    norm_binding = (
        res.binding.cause
        if (res.binding and res.binding.cause in ("norm_floor", "norm_cap"))
        else None
    )
    precedence = res.binding.precedence.name.lower() if res.binding else None
    return WriteTarget(
        round(res.value, 1), mode, norm_binding, precedence, override_clamped
    )


def should_write(
    actual: float | None,
    target: float,
    *,
    mode_changed: bool,
    deadband: float,
) -> bool:
    """Whether the actuator setpoint must be (re)written this tick (ADR-0012).

    ``actual`` is the actuator's *current* reported setpoint. Writes when it is
    unknown, on a mode change, or when it differs from ``target`` by at least
    ``deadband`` K. Comparing against the device's real setpoint (not our last
    command) means we re-assert after an external change while still skipping
    redundant writes — sparing battery/Zigbee TRVs from per-tick traffic.
    """
    if actual is None or mode_changed:
        return True
    # setpoints are 0.1-resolution; round the delta to avoid float artefacts
    return round(abs(target - actual), 3) >= deadband


def external_feed_due(
    last_fed: float | None,
    fed: float,
    *,
    last_fed_ts: float,
    now: float,
    keepalive_s: float,
    deadband: float = 0.1,
) -> bool:
    """Whether to (re)push the room temperature to a TRV external-temp input (P2-2).

    Pushes when the fed value has moved by at least ``deadband`` K (the normal
    trigger, via :func:`should_write`) OR when ``keepalive_s`` has elapsed since
    the last push. The keep-alive matters because some TRVs time out an external-
    temperature input and silently fall back to their internal (mounted) sensor,
    so a perfectly stable room would otherwise let the feed go stale. ``now`` and
    ``last_fed_ts`` share the caller's monotonic clock; a non-positive
    ``keepalive_s`` disables the time-based re-push (value-move writes still fire).
    """
    if should_write(last_fed, fed, mode_changed=False, deadband=deadband):
        return True
    if keepalive_s > 0.0:
        return (now - last_fed_ts) >= keepalive_s
    return False


def snap_to_step(value: float, step: float) -> float:
    """Round ``value`` to the actuator's setpoint resolution.

    Comparing our 0.1-resolution target against a device that reports back in a
    coarser step (e.g. 0.5 K) would otherwise re-write every tick once the
    rounding gap reaches the deadband; snapping makes the comparison like-for-
    like so the write-throttle keeps sparing battery/Zigbee TRVs (review R2).
    """
    if step <= 0.0:
        return value
    return round(round(value / step) * step, 2)


def heat_drive_signal(hvac_action: str | None, *, fallback_heating: bool) -> float:
    """EKF heating-drive input (0/1): prefer the actuator's *real* running state.

    A TRV's ``hvac_action``/``running_state`` (e.g. Sonoff TRVZB) reports whether
    the valve is actually heating, which is ground truth for the building-physics
    EKF (ADR-0002). When the device does not report one, fall back to Poise's own
    heat intent so devices without the attribute still learn.
    """
    if not hvac_action:
        return 1.0 if fallback_heating else 0.0
    return 1.0 if hvac_action == "heating" else 0.0


def cool_drive_signal(hvac_action: str | None, *, fallback_cooling: bool) -> float:
    """EKF cooling-drive input (0/1): the β_c counterpart of heat_drive_signal.

    ``beta_c`` (cooling responsivity) is only observable when the cooling input
    ``u_c`` is actually excited (ADR-0024). Prefer the actuator's real running
    state — an AC reporting ``hvac_action == "cooling"`` is ground truth — and
    fall back to Poise's own cool intent so a device that reports no
    ``hvac_action`` still excites β_c during the cooling season instead of
    leaving ``cooling_identified`` False forever.
    """
    if not hvac_action:
        return 1.0 if fallback_cooling else 0.0
    return 1.0 if hvac_action == "cooling" else 0.0


def needs_mode_nudge(
    current_mode: str | None, desired_mode: str, *, supported: bool
) -> bool:
    """True if the actuator must be commanded into ``desired_mode`` (H1).

    A TRV left in ``off`` ignores our setpoint, ``auto`` runs the device's own
    weekly schedule (Sonoff TRVZB ``system_mode=auto``), and a device sitting in a
    *different active* mode (an auto/seasonal heat-pump that switched to ``heat``
    while we now cool, or an AC still in ``dry`` after the room has dried out) all
    diverge from what we write — so we assert ``desired_mode`` whenever the device
    is not already in it. The rule is simply "current ≠ desired": it subsumes the
    old auto/off + opposite-mode cases and, since ADR-0050, also *leaves* the
    ``dry`` mode once we no longer want it (a stuck ``dry`` keeps dehumidifying).
    We only assert a mode the device *literally* offers (``supported`` from the
    actuator's real ``hvac_modes``); otherwise the call is rejected and spams the
    log every tick (review V1). An ``unknown``/``unavailable`` current mode is
    left alone (conservative — the device may be booting or briefly offline).
    """
    if not supported or current_mode in (None, "unknown", "unavailable"):
        return False
    return current_mode != desired_mode


def resolve_desired_mode(
    *,
    final_mode: str,
    current_device_mode: str | None,
    can_cool: bool,
    can_heat: bool,
    idle_park_mode: str | None = None,
) -> str:
    """The hvac_mode to command this tick — the nudge target (review Finding 1, V1).

    ``heat``/``cool``/``dry`` map to themselves. A window / safety ``off`` must
    NOT leave a cooling device in ``cool`` — it would cool toward the frost floor
    (review V1). So ``off`` maps to ``heat`` on a heat-capable device (it holds
    the frost floor by heating minimally) and to a real ``off`` on a cool-only
    device (stop, never cool). On a passive ``idle`` tick we take the room-position
    park (``idle_park_mode``) so a warm reversible AC parks in ``cool`` at the cool
    edge instead of ``heat`` at the low idle-hold (Finding 1 follow-up); when no
    park is supplied we keep the device's current active mode so a cooling AC still
    idles in ``cool`` instead of ping-ponging cool<->heat at the compressor.
    ``manual`` and off/unknown fall back to the current mode or ``heat``.
    """
    if final_mode in ("heat", "cool", "dry"):
        return final_mode
    if final_mode == "off":
        return "heat" if can_heat else "off"
    if final_mode == "idle" and idle_park_mode in ("heat", "cool", "fan_only"):
        return idle_park_mode
    if can_cool and current_device_mode in ("heat", "cool"):
        return current_device_mode
    return "heat"


def idle_park(
    *,
    room: float,
    heat_sp: float,
    cool_sp: float,
    can_heat: bool,
    can_cool: bool,
    can_fan_only: bool = False,
    current_mode: str | None = None,
    hysteresis: float = 0.5,
) -> tuple[str, float]:
    """Where to park a device idling in the neutral dead-band (Finding 1 follow-up).

    An idle reversible AC must not sit in ``heat`` at the low heat edge through the
    cooling season — the room would have to fall many kelvin before anything happens
    and a *warming* room triggers nothing. A **fan_only-capable** device circulates
    in the dead-band instead of holding the cool edge (holding ``cool`` compressor-
    cools against the device's own warmer sensor and dries the room — the office-AC
    finding); the rules below are the legacy park for devices without a fan_only
    mode (``can_fan_only`` False → byte-identical to the old behaviour). Rules:

    * a heat-only TRV always parks in ``heat`` (``can_cool`` False); a cool-only
      device always parks in ``cool``;
    * a device **already cooling** keeps cooling and idles at the cool edge. When
      the tick is idle the room is by definition at/above the heat setpoint (else
      the decision would be ``heat``), so there is no heat demand and flipping to
      heat would only thrash the compressor (Finding 1). The warm-room flip below
      is one-way and sticky — the next tick sees ``current_mode == "cool"`` — so it
      never ping-pongs;
    * otherwise (heat / off / auto / unknown) park toward the edge the room is
      closest to: a clearly warm room (upper half, beyond the ``hysteresis`` buffer
      that keeps 0.1 K sensor noise from flipping it) parks in ``cool`` at the cool
      edge instead of the low heat idle-hold (the idle-park fix); a neutral or cool
      room holds ``heat``.

    Returns ``(mode, setpoint)`` so the coordinator drives the mode nudge AND the
    written value from ONE decision — they can never disagree.
    """
    if not can_cool:
        return "heat", heat_sp
    mid = (heat_sp + cool_sp) / 2.0
    # Over-dry fix (office-AC finding): a fan_only-capable device *circulates* in
    # the dead-band instead of holding the cool edge. Holding ``cool`` makes the
    # device compressor-cool against its OWN (often warmer, ceiling/return-air)
    # sensor and dry the room out even while Poise reads it at or below the edge.
    # Only on the clearly cool side does a heat-capable device stay heat-ready (no
    # draft); the compressor re-engages the instant decide() calls for real
    # cooling. A device WITHOUT a fan_only mode keeps the legacy Finding-1 park —
    # ``can_fan_only`` defaults False, so the old behaviour is byte-identical.
    if can_fan_only and not (can_heat and room < mid - hysteresis):
        return "fan_only", cool_sp
    if not can_heat:
        return "cool", cool_sp
    if current_mode == "cool":
        return "cool", cool_sp
    return ("cool", cool_sp) if room > mid + hysteresis else ("heat", heat_sp)


def sanitize_override(target: float | None, lo: float, hi: float) -> float | None:
    """Validate a manual setpoint override at the boundary (review C2/Ü2).

    Rejects a non-finite value (so NaN/Inf can never reach the actuator) and
    clamps a finite one into ``[lo, hi]`` (frost floor .. device max).
    """
    if target is None or not math.isfinite(target):
        return None
    return min(hi, max(lo, target))


def frost_rescue_target(
    *,
    can_heat: bool,
    actual_sp: float | None,
    device_state: str | None,
    frost_floor: float,
    mold_min: float | None,
    deadband: float,
) -> float | None:
    """The health floor to write when Poise is DISABLED for a zone (review V4).

    Even disabled, the frost/mould floor is unconditional (README promise), but a
    disabled zone must not fight a reasonable manual setpoint. Rescue-only: return
    the floor only when a heat-capable device sits below it (or is off / unknown /
    reports no setpoint); otherwise ``None`` (hands-off). A cool-only device has no
    frost duty and always returns ``None``.
    """
    if not can_heat:
        return None
    floor = round(
        max(frost_floor, mold_min if mold_min is not None else frost_floor), 1
    )
    inactive = device_state in (None, "off", "unknown", "unavailable")
    below = actual_sp is None or actual_sp < floor - deadband
    return floor if (inactive or below) else None
