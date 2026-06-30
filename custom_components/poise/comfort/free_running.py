"""EN-16798-1 free-running band widening (ADR-0023 §1).

When a building is free-running — the running mean is in the adaptive validity
range AND the room is floating inside the fixed neutral dead-band (no active
heating or cooling is demanded) — the adaptive comfort band widens the dead-band:
it may LOWER the heating edge toward the adaptive lower limit and RAISE the
cooling edge toward the adaptive upper limit, saving energy. It NEVER raises the
heating setpoint (the original live bug was the adaptive neutral ~24 °C becoming
a warm heat target).

Pure; wired shadow-first (diagnostic only). The regime gate must be validated
against real data before it drives the live setpoint: an ungated adaptive raise
would push the cooling edge to ~31 °C on a hot day (T_rm high) and suppress
legitimate summer cooling — which is also why the active path keeps the fixed
design bands (and ADR-0051 handles the heat-day cool target separately).
"""

from __future__ import annotations

from dataclasses import dataclass

from .en16798 import Category, adaptive_band


@dataclass(frozen=True, slots=True)
class FreeRunningBand:
    heat_op: float  # heating edge after widening (operative °C)
    cool_op: float  # cooling edge after widening (operative °C)
    active: bool  # True if the free-running widening applied
    adaptive_lower: float  # EN adaptive lower limit [°C] (diagnostic)
    adaptive_upper: float  # EN adaptive upper limit [°C] (diagnostic)


def free_running_widen(
    *,
    heat_op: float,
    cool_op: float,
    room: float,
    t_rm: float,
    category: Category = Category.II,
) -> FreeRunningBand:
    """Widen the neutral band by the EN adaptive band when free-running."""
    ab = adaptive_band(t_rm, category)
    # Free-running := adaptive model valid (10 <= T_rm <= 30, not extrapolated)
    # AND the room floats inside the fixed neutral band (no active demand). The
    # second clause is the safety gate: it guarantees the widening can never
    # suppress an active heating or cooling demand (room outside -> not active).
    free_running = (not ab.extrapolated) and (heat_op <= room <= cool_op)
    if not free_running:
        return FreeRunningBand(heat_op, cool_op, False, ab.lower, ab.upper)
    new_heat = min(heat_op, ab.lower)  # widen down; NEVER raise the heat edge
    new_cool = max(cool_op, ab.upper)  # widen up toward the adaptive upper
    return FreeRunningBand(new_heat, new_cool, True, ab.lower, ab.upper)
