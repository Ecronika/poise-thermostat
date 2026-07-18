"""Dual-setpoint cooling decision with capability + outdoor gating (RoomMind, ADR-0023).

Separate heat/cool targets with a neutral dead-band; hard outdoor lockouts and
device-capability gating prevent heating when it is mild outside, cooling when
it is cold, or acting in a direction the device cannot do.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DualSetpoint:
    heat: float
    cool: float


def decide_mode(
    room: float,
    setpoint: DualSetpoint,
    *,
    outdoor: float,
    climate_mode: str = "auto",
    can_heat: bool = True,
    can_cool: bool = True,
    cool_min_outdoor: float | None = 16.0,
    heat_max_outdoor: float | None = 22.0,
) -> str:
    """Return "heat", "cool" or "idle" (the dead-band / gated case).

    ``cool_min_outdoor``/``heat_max_outdoor`` are the outdoor lockouts and are
    **configurable per zone**; ``None`` disables that direction's outdoor gate
    (e.g. an internal-gain room that must cool regardless of outside, ADR-0047).
    """
    # A contradictory band (heat target above cool target) is a mis-config; do
    # not act on it — otherwise both branches match between the edges and 'heat'
    # would win silently (review M6). Upstream dual_setpoint enforces cool>=heat.
    if setpoint.cool < setpoint.heat:
        return "idle"
    heat_ok = (
        can_heat
        and climate_mode in ("auto", "heat_only")
        and (heat_max_outdoor is None or outdoor <= heat_max_outdoor)
    )
    cool_ok = (
        can_cool
        and climate_mode in ("auto", "cool_only")
        and (cool_min_outdoor is None or outdoor >= cool_min_outdoor)
    )
    if heat_ok and room < setpoint.heat:
        return "heat"
    if cool_ok and room > setpoint.cool:
        return "cool"
    return "idle"


def override_mode(
    room: float,
    override: float,
    *,
    hysteresis: float = 0.5,
    outdoor: float,
    climate_mode: str,
    can_heat: bool,
    can_cool: bool,
    cool_min_outdoor: float | None,
    heat_max_outdoor: float | None,
) -> str:
    """Mode for an ACTIVE manual setpoint override (ADR-0059 control-loop fix,
    ADR-0042 / ADR-0023).

    The manual value must DRIVE the direction like a single-setpoint thermostat,
    not merely set the written value. Collapse the comfort band to a small
    hysteresis window around the override and reuse :func:`decide_mode`, so the
    device-capability and outdoor-lockout rules still apply:
    ``override < room - hysteresis`` -> ``cool``,
    ``override > room + hysteresis`` -> ``heat``, within ``+/- hysteresis`` ->
    ``idle`` (still routed through the seam so dry / fan-in-deadband can act).
    """
    band = DualSetpoint(heat=override - hysteresis, cool=override + hysteresis)
    return decide_mode(
        room,
        band,
        outdoor=outdoor,
        climate_mode=climate_mode,
        can_heat=can_heat,
        can_cool=can_cool,
        cool_min_outdoor=cool_min_outdoor,
        heat_max_outdoor=heat_max_outdoor,
    )


def cooling_intent(*, enabled: bool, window_open: bool, mode: str) -> bool:
    """True when Poise actively intends to cool this tick (R10).

    Cooling is neutralised while a window is open -- don't chase a cool target
    against the outside air -- and is only asserted when the zone is enabled and
    the arbitrated ``mode`` is ``"cool"``. Pulled out of the coordinator tick so
    the window gate is unit-tested; the heating counterpart mirrors it
    (``enabled and not window_open and mode == "heat"``).
    """
    return enabled and not window_open and mode == "cool"
