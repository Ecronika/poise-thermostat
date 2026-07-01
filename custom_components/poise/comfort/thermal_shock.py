"""Heat-day cooling band: ΔT-shock floor under the EN adaptive upper (ADR-0051).

On a hot day, cooling to a fixed 26 °C wastes energy and thermally shocks people
at the door; health guidance is ~6-8 K under outdoor. This raises the cooling
setpoint toward ``outdoor - ΔT`` but never above the EN-16798-1 adaptive upper
edge (the norm anchor) nor a hard cap (ASR A3.5 office ceiling 26 °C, raising it
is an employer policy opt-in), and never below the EN cooling setpoint. Pure and
unit-tested; the live raise is rate-limited (``rate_limit``) against churn.
"""

from __future__ import annotations

from dataclasses import dataclass

from .en16798 import Category, adaptive_band

DEFAULT_SHOCK_DELTA_K: float = 7.0  # mid of the 6-8 K health guideline
DEFAULT_HARD_CAP_C: float = 26.0  # ASR A3.5 office ceiling (raising = opt-in)


@dataclass(frozen=True, slots=True)
class AdaptiveCool:
    cool_sp_eff: float  # effective cooling setpoint [°C], air-side
    raised: bool  # True if lifted above the EN cooling setpoint
    en_upper: float  # EN-16798-1 adaptive upper edge [°C] (the norm clamp)
    upper_clamp: float  # min(device_max, hard_cap, en_upper) actually applied
    reason: str


def adaptive_cool_setpoint(
    *,
    cool_sp_en: float,
    t_out_smooth: float,
    t_rm: float,
    category: Category = Category.II,
    device_max: float = 30.0,
    hard_cap: float = DEFAULT_HARD_CAP_C,
    delta_k: float = DEFAULT_SHOCK_DELTA_K,
) -> AdaptiveCool:
    """Raise the cooling setpoint on a hot day, clamped by EN upper + hard cap.

    ``cool_sp_en`` is the EN dual-setpoint cooling value (already dew-point /
    mold protected). The result is never below it and never above
    ``min(device_max, hard_cap, EN_adaptive_upper)``.
    """
    en_upper = adaptive_band(t_rm, category).upper
    upper = min(device_max, hard_cap, en_upper)
    if upper < cool_sp_en:  # the cap never pulls below the EN setpoint
        upper = cool_sp_en
    if delta_k <= 0.0:  # feature off
        return AdaptiveCool(
            round(cool_sp_en, 1), False, round(en_upper, 1), round(upper, 1), "off"
        )
    shock_floor = t_out_smooth - delta_k
    raw = max(cool_sp_en, shock_floor)
    eff = min(raw, upper)
    raised = eff > cool_sp_en + 1e-9
    if raised:
        reason = f"raised to {eff:.1f} (cap {upper:.1f})"
    elif shock_floor > cool_sp_en:
        reason = f"capped {upper:.1f} vs {t_out_smooth:.0f} out"
    else:
        reason = "mild: no raise"
    return AdaptiveCool(
        round(eff, 1), raised, round(en_upper, 1), round(upper, 1), reason
    )


def rate_limit(prev: float | None, target: float, max_step: float) -> float:
    """Move ``prev`` toward ``target`` by at most ``max_step`` per call.

    Anti-churn for the live cooling setpoint (ADR-0051 §4): a hot-day raise must
    not jump the actuator's setpoint in one tick. ``prev=None`` (first sample) or
    ``max_step<=0`` returns ``target`` unchanged.
    """
    if prev is None or max_step <= 0.0:
        return target
    if target > prev:
        return min(target, prev + max_step)
    return max(target, prev - max_step)
