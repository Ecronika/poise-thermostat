"""Capability-aware dual-setpoint comfort decision (ADR-0023).

Produces a heating setpoint + cooling setpoint with a neutral dead-band, picks
the direction from device capability + outdoor gating + comfort/efficiency
priority, and yields a capability-correct setpoint to write so an idle device
is never clamped to the wrong band edge. Air-side (operative->air applied).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..control.cooling import DualSetpoint, decide_mode
from .en16798 import COOLING_UPPER, HEATING_LOWER, HEATING_UPPER, Category
from .operative import operative_to_air

_EFFICIENCY_WIDEN_K = 1.5  # max dead-band widening per side at full efficiency


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


@dataclass(frozen=True, slots=True)
class ComfortDecision:
    heat_sp: float  # heating setpoint, air-side
    cool_sp: float  # cooling setpoint, air-side
    mode: str  # "heat" | "cool" | "idle"
    write_setpoint: float  # capability-correct value for the SETPOINT path
    target: float | None  # active target when conditioning, else None


def decide(
    *,
    t_rm: float,
    room: float,
    category: Category = Category.II,
    comfort_base: float = 21.0,
    can_heat: bool = True,
    can_cool: bool = False,
    climate_mode: str = "auto",
    t_out: float,
    t_mrt: float | None = None,
    velocity: float = 0.1,
    frost_floor: float = 7.0,
    mold_min: float | None = None,
    dewpoint: float | None = None,
    priority: float = 1.0,  # 0 = efficiency (wide band), 1 = comfort (tight band)
) -> ComfortDecision:
    """Build the dual-setpoint comfort decision for one zone."""
    _ = t_rm  # regime indicator; fixed design bands govern when conditioning
    # operative dead-band from the fixed conditioned-building ranges
    heat_op = _clamp(comfort_base, HEATING_LOWER[category], HEATING_UPPER[category])
    cool_op = COOLING_UPPER[category]

    # comfort/efficiency priority widens the dead-band toward efficiency
    widen = (1.0 - _clamp(priority, 0.0, 1.0)) * _EFFICIENCY_WIDEN_K
    heat_op -= widen
    cool_op += widen

    # operative -> air
    heat_sp = operative_to_air(heat_op, t_mrt, velocity)
    cool_sp = operative_to_air(cool_op, t_mrt, velocity)

    # hard floors / caps
    heat_sp = max(heat_sp, frost_floor)
    if mold_min is not None:
        heat_sp = max(heat_sp, mold_min)
    if dewpoint is not None:  # never cool below dewpoint + 2 K (condensation)
        cool_sp = max(cool_sp, dewpoint + 2.0)
    cool_sp = max(cool_sp, heat_sp)  # never invert the band

    setpoint = DualSetpoint(round(heat_sp, 1), round(cool_sp, 1))
    mode = decide_mode(
        room,
        setpoint,
        outdoor=t_out,
        climate_mode=climate_mode,
        can_heat=can_heat,
        can_cool=can_cool,
    )

    if mode == "heat":
        write, target = setpoint.heat, setpoint.heat
    elif mode == "cool":
        write, target = setpoint.cool, setpoint.cool
    else:  # idle: capability-correct hold so the device does not condition
        write = setpoint.heat if can_heat else setpoint.cool
        target = None

    return ComfortDecision(setpoint.heat, setpoint.cool, mode, write, target)
