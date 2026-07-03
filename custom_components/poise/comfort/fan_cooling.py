"""Elevated-air-speed cooling effect (ASHRAE 55) — a fan as an energy lever.

A moving airstream lets people stay comfortable at a higher operative temperature,
so when a fan runs the cooling setpoint may be raised by the "cooling effect" (CE)
with no loss of comfort — cooling with less (or no) compressor (roadmap M3 §4.2).

ASHRAE 55 derives CE from the SET model; a faithful live SET solve needs a full
two-node thermophysiological model, so this uses the standard's *published*
elevated-air-speed cooling effect at reference conditions (~0.5 clo / ~1.1 met),
piecewise-linear in air speed and capped — conservative, pure, no dependency. The
anchor points are the ASHRAE 55 graphic-method limits: 0.6 m/s -> 1.2 K, 0.9 -> 1.8,
1.2 -> 2.2; CE is 0 below the 0.2 m/s elevated-air-speed threshold (a still room is
never credited). Shadow-first: the coordinator only reports the CE and the setpoint
it *would* raise to; a raise never lowers comfort below the norm's own upper edge.
"""

from __future__ import annotations

STILL_AIR_MS = 0.1  # operative-temperature baseline velocity (EN ISO 7726 default)
_ELEVATED_THRESHOLD_MS = 0.2  # below this no cooling-effect credit (ASHRAE 55)
# ASHRAE 55 elevated-air-speed cooling effect [K] at reference clothing/metabolism.
_CE_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.2, 0.0),
    (0.6, 1.2),
    (0.9, 1.8),
    (1.2, 2.2),
)


def cooling_effect(air_speed: float) -> float:
    """Elevated-air-speed cooling effect [K] (ASHRAE 55, SET-derived, tabulated).

    Piecewise-linear through the standard's published points; 0 below the 0.2 m/s
    threshold, flat at the 1.2 m/s cap (2.2 K) above. Concave (diminishing returns),
    which matches the SET model.
    """
    if air_speed <= _ELEVATED_THRESHOLD_MS:
        return 0.0
    if air_speed >= _CE_ANCHORS[-1][0]:
        return _CE_ANCHORS[-1][1]
    for (v0, c0), (v1, c1) in zip(_CE_ANCHORS, _CE_ANCHORS[1:], strict=False):
        if v0 <= air_speed <= v1:
            return round(c0 + (c1 - c0) * (air_speed - v0) / (v1 - v0), 2)
    return 0.0  # unreachable (air_speed is within the anchor range here)


def fan_cool_setpoint(
    *,
    cool_sp: float,
    air_speed: float,
    fan_running: bool,
    upper_cap: float,
) -> tuple[float, float]:
    """Cooling setpoint raised by the cooling effect when a fan runs (ASHRAE 55).

    Returns ``(cool_sp_eff, ce_k)``. No raise when the fan is off or the air is still
    (``air_speed <= STILL_AIR_MS``); the raise is clamped to ``upper_cap`` (the EN
    adaptive upper / ASR ceiling) so the room is never allowed warmer than the norm
    permits, and never pulled *below* ``cool_sp``.
    """
    if not fan_running or air_speed <= STILL_AIR_MS:
        return round(cool_sp, 1), 0.0
    ce = cooling_effect(air_speed)
    raised = min(cool_sp + ce, upper_cap)
    raised = max(raised, cool_sp)  # a low cap never lowers the setpoint
    return round(raised, 1), round(raised - cool_sp, 2)


# Occupied-zone air-speed estimate [m/s] by fan stage, credited only while the
# indoor fan is actually running (device/geometry-dependent — an estimate, not a
# measurement). Below the 0.2 m/s threshold cooling_effect() credits nothing.
_FAN_SPEED_MS: dict[str, float] = {
    "silent": 0.25,
    "quiet": 0.25,
    "low": 0.25,
    "min": 0.25,
    "medium": 0.40,
    "mid": 0.40,
    "high": 0.65,
    "strong": 0.65,
    "focus": 0.65,
    "turbo": 0.85,
    "powerful": 0.85,
    "max": 0.85,
    "auto": 0.35,
}
_FAN_SPEED_RUNNING_DEFAULT = 0.30  # running, but an unrecognised stage label
# hvac_action values in which the indoor fan is actually moving air.
_MOVING_ACTIONS = frozenset({"cooling", "drying", "dry", "fan", "fan_only", "heating"})


def fan_velocity(
    *,
    fan_mode: str | None,
    hvac_action: str | None,
    can_recirculate: bool = True,
) -> float:
    """Estimated occupied-zone air speed [m/s] from the actuator's fan state.

    Returns the still-air baseline unless the indoor fan is *actually* running —
    ``hvac_action`` shows active conditioning/fan on a fan-capable device — so a
    fan-off idle (e.g. ``fan_mode=auto`` with the compressor off) is never
    credited with movement. Conservative by design (under-crediting is the safe
    direction for a shadow that informs a later live raise); the per-stage speeds
    are estimates, not measurements.
    """
    if not can_recirculate:
        return STILL_AIR_MS
    if (hvac_action or "").lower() not in _MOVING_ACTIONS:
        return STILL_AIR_MS
    return _FAN_SPEED_MS.get((fan_mode or "").lower(), _FAN_SPEED_RUNNING_DEFAULT)
