"""Capability-aware dual-setpoint comfort decision (ADR-0023).

Produces a heating setpoint + cooling setpoint with a neutral dead-band, picks
the direction from device capability + outdoor gating + comfort/efficiency
priority, and yields a capability-correct setpoint to write so an idle device
is never clamped to the wrong band edge. Air-side (operative->air applied).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..control.cooling import DualSetpoint, decide_mode
from .en16798 import (
    COOLING_LOWER,
    COOLING_UPPER,
    HEATING_LOWER,
    HEATING_UPPER,
    Category,
)
from .free_running import adaptive_cool_edge
from .operative import operative_to_air

_EFFICIENCY_WIDEN_K = 1.5  # max dead-band widening per side at full efficiency
_NEUTRAL_DEADBAND_K = 2.0  # cooling edge sits this far above the comfort centre


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
    cool_min_outdoor: float | None = 16.0,
    heat_max_outdoor: float | None = 22.0,
    t_out: float,
    t_mrt: float | None = None,
    velocity: float = 0.1,
    frost_floor: float = 7.0,
    mold_min: float | None = None,
    dewpoint: float | None = None,
    priority: float = 1.0,  # 0 = efficiency (wide band), 1 = comfort (tight band)
    occupied: bool = True,  # False during an unoccupied setback (review V3)
    adaptive_cool: bool = False,  # capability-default (auto: active if cool-capable)
    adaptive_cap: float = 26.0,  # ASR office ceiling for the adaptive cool edge
    eco_widen: float = 0.0,  # ADR-0058: presence Eco band-widening (both edges)
    cool_ceiling_override: float | None = None,  # ADR-0058: unoccupied cool ceiling
) -> ComfortDecision:
    """Build the dual-setpoint comfort decision for one zone."""
    # The fixed design bands are anchored to the comfort centre (heat/cool edges
    # from comfort_base +/- the neutral dead-band, widened by the efficiency
    # priority — review M1). When ``adaptive_cool`` is enabled the cooling edge is
    # then lifted to the EN 16798 adaptive upper for the running mean (ADR-0023
    # §1), so a warm free-running summer is not over-cooled toward the fixed band.
    widen = (1.0 - _clamp(priority, 0.0, 1.0)) * _EFFICIENCY_WIDEN_K
    # Clamp each edge into its EN-16798 category band AFTER widening, so a wide
    # efficiency band can never breach the comfort category lower/upper (review
    # M2). The norm limits act as guardrails (clamp), never as the setpoint.
    # V3: the EN band is an *occupied*-comfort guardrail. During an unoccupied
    # night/away setback the room is meant to drift below the comfort lower toward
    # the health floor, so the lower clamp relaxes to the frost floor — otherwise a
    # setback target below HEATING_LOWER is silently clamped back up and the whole
    # setback is neutralised. The air-side frost/mould floor is re-applied below,
    # so protection is never weakened; only the comfort lower is waived.
    heat_lower = HEATING_LOWER[category] if occupied else frost_floor
    heat_op = _clamp(
        comfort_base - widen - eco_widen, heat_lower, HEATING_UPPER[category]
    )
    # ADR-0058: presence Eco widens both edges symmetrically (heat down, cool up);
    # the unoccupied cool ceiling relaxes from COOLING_UPPER to the caller's
    # override (ROOM_ECO -> cool_hard_cap, AWAY -> device_max). eco_widen is baked
    # into the FIXED edge before the adaptive lift below, so max(fixed+eco,
    # adaptive) holds — the adaptive edge can never undo an Eco relaxation.
    cool_ceiling = (
        cool_ceiling_override
        if cool_ceiling_override is not None
        else COOLING_UPPER[category]
    )
    cool_op = _clamp(
        comfort_base + _NEUTRAL_DEADBAND_K + widen + eco_widen,
        COOLING_LOWER[category],
        cool_ceiling,
    )
    # ADR-0023 §1 (live, capability-default): lift the cooling edge from
    # the fixed summer band to the EN adaptive upper (capped at the ASR ceiling),
    # so a room within the adaptive comfort band is not over-cooled toward 23 °C.
    if adaptive_cool:
        cool_op, _raised = adaptive_cool_edge(
            fixed_cool_op=cool_op,
            t_rm=t_rm,
            category=category,
            cap=adaptive_cap,
            enabled=True,
            can_cool=can_cool,
        )

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
        cool_min_outdoor=cool_min_outdoor,
        heat_max_outdoor=heat_max_outdoor,
    )

    if mode == "heat":
        write, target = setpoint.heat, setpoint.heat
    elif mode == "cool":
        write, target = setpoint.cool, setpoint.cool
    else:  # idle: capability-correct hold so the device does not condition
        write = setpoint.heat if can_heat else setpoint.cool
        target = None

    return ComfortDecision(setpoint.heat, setpoint.cool, mode, write, target)
