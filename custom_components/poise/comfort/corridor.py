"""Comfort-corridor assembly (ADR-0017/0035).

Builds the air-side :class:`ComfortCorridor` from the EN 16798 adaptive band
(operative, transformed to air), the mould floor, the frost floor and the
device limit. Bounds are kept as lists with their causes; the *binding* bound
is resolved later by the precedence solver (ADR-0035).

ADR-0071: the mould floor is no longer DERIVED here. It used to be a one-line
inversion of the 80 % surface-RH criterion, which is a pure function of the
current reading — the dose model that replaced it carries multi-day state and
therefore cannot live inside a stateless corridor build. The floor now ARRIVES
as ``ComfortContext.mold_min`` (``MouldRisk.floor``, ``None`` when the
protection is not engaged), which also keeps this module free of any
``runtime``/``control`` import (ADR-0005).

Reference-pipeline scope only (``pipeline.run_tick``, harness + pure-core
tests): the live coordinator assembles its envelope in
``control/tick_resolve``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Bound, ComfortCorridor
from .en16798 import Category, adaptive_band
from .operative import operative_to_air


@dataclass(frozen=True, slots=True)
class ComfortContext:
    t_rm: float
    t_air: float
    frost_floor: float
    device_max: float
    t_mrt: float | None = None
    velocity: float = 0.1
    category: Category = Category.II
    # ADR-0071: the mould floor as the dose model decided it this tick
    # (``MouldRisk.floor``); ``None`` while the protection is not engaged, in
    # which case no "mold" bound enters the corridor at all.
    mold_min: float | None = None


def build_corridor(ctx: ComfortContext) -> ComfortCorridor:
    """Assemble the air-side comfort corridor for one zone."""
    band = adaptive_band(ctx.t_rm, ctx.category)
    # operative -> air for the neutral target and both band edges (ADR-0017)
    target_air = operative_to_air(band.comfort, ctx.t_mrt, ctx.velocity)
    lower_air = operative_to_air(band.lower, ctx.t_mrt, ctx.velocity)
    upper_air = operative_to_air(band.upper, ctx.t_mrt, ctx.velocity)

    lower: list[Bound] = [
        Bound(ctx.frost_floor, "frost"),
        Bound(lower_air, "en16798"),
    ]
    if ctx.mold_min is not None:
        lower.append(Bound(ctx.mold_min, "mold"))

    upper: list[Bound] = [
        Bound(ctx.device_max, "device_max"),
        Bound(upper_air, "en16798"),
    ]
    return ComfortCorridor(tuple(lower), tuple(upper), round(target_air, 2), "air")
