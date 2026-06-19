"""Comfort-corridor assembly (ADR-0013/0017).

Builds the air-side :class:`ComfortCorridor` from the EN 16798 adaptive band
(operative, transformed to air), the mould floor (DIN 4108-2), the frost floor
and the device limit. Bounds are kept as lists with their causes; the *binding*
bound is computed later by the corridor itself / arbitration (ADR-0013).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Bound, ComfortCorridor
from .en16798 import Category, adaptive_band
from .mold import DEFAULT_F_RSI, mold_min_air_temperature
from .operative import operative_to_air


@dataclass(frozen=True, slots=True)
class ComfortContext:
    t_rm: float
    t_air: float
    frost_floor: float
    device_max: float
    rh_percent: float | None = None
    t_out: float | None = None
    t_mrt: float | None = None
    velocity: float = 0.1
    category: Category = Category.II
    f_rsi: float = DEFAULT_F_RSI


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
    if ctx.rh_percent is not None and ctx.t_out is not None:
        mold_min = mold_min_air_temperature(
            ctx.t_out, ctx.rh_percent, ctx.t_air, ctx.f_rsi
        )
        lower.append(Bound(mold_min, "mold"))

    upper: list[Bound] = [
        Bound(ctx.device_max, "device_max"),
        Bound(upper_air, "en16798"),
    ]
    return ComfortCorridor(tuple(lower), tuple(upper), round(target_air, 2), "air")
