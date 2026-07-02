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
