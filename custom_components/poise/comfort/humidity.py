"""Humidity management: dry-guard + active dehumidification decision (ADR-0050).

Cool-first: cooling dehumidifies and serves Poise's temperature primacy, so
``dry`` is reserved for the gap cooling cannot fill without overcooling (RH high,
temperature already inside the dead-band). The dehumidification RH ceiling is
category-bound (EN 16798-1 Annex B: Cat I 50 %, II 60 %, III 70 %); an absolute
humidity-ratio backstop (12 g/kg, the EN 16798-1 / ASHRAE-55 comfort ceiling)
additionally triggers drying when a warm room's RH still looks acceptable but
its absolute moisture is high. Asymmetric hysteresis (exit = ceiling −
hysteresis) mirrors HA-core ``generic_hygrostat``. A dry-guard blocks any
dehumidifying action below ``rh_low`` and stays the TOP precedence, so the
absolute cap never over-dries already-dry air. ``fan_only`` is NEVER used to
dehumidify — a fan over a wet evaporator coil re-evaporates condensate and
RAISES RH. Pure; wired shadow-first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .en16798 import Category

DEFAULT_RH_HIGH: float = 60.0  # Cat II ceiling; fallback when no category given
DEFAULT_RH_LOW: float = 40.0  # dry-guard floor; below this, block all drying
DEFAULT_RH_HYSTERESIS: float = 5.0  # exit RH = rh_high - hysteresis
DEFAULT_ABS_HIGH_GKG: float = 12.0  # EN 16798-1 / ASHRAE-55 absolute-moisture cap
DEFAULT_ABS_HYSTERESIS_GKG: float = 1.0  # exit w = abs_high - hysteresis (11 g/kg)

# EN 16798-1 Annex B dehumidification RH ceilings [%] per comfort category.
_RH_HIGH_BY_CATEGORY: dict[Category, float] = {
    Category.I: 50.0,
    Category.II: 60.0,
    Category.III: 70.0,
}


@dataclass(frozen=True, slots=True)
class HumidityConfig:
    rh_high: float = DEFAULT_RH_HIGH
    rh_low: float = DEFAULT_RH_LOW
    hysteresis: float = DEFAULT_RH_HYSTERESIS
    abs_high: float = DEFAULT_ABS_HIGH_GKG
    abs_hysteresis: float = DEFAULT_ABS_HYSTERESIS_GKG


_DEFAULT = HumidityConfig()


def rh_high_for_category(
    category: Category | None, cfg: HumidityConfig = _DEFAULT
) -> float:
    """Dehumidification RH ceiling [%] for the comfort category (EN 16798-1 B).

    Falls back to ``cfg.rh_high`` (Cat II, 60 %) when no category is given, so
    existing callers keep their behaviour.
    """
    if category is None:
        return cfg.rh_high
    return _RH_HIGH_BY_CATEGORY.get(category, cfg.rh_high)


@dataclass(frozen=True, slots=True)
class HumidityDecision:
    action: str  # "idle" | "cool" | "dry" | "dry_guard"
    dry_active: bool  # latched dehumidification state (feeds next-tick hysteresis)
    reason: str


def humidity_decide(
    *,
    rh: float | None,
    too_warm: bool,
    in_deadband: bool,
    can_dry: bool,
    can_fan_only: bool = False,
    prev_dry_active: bool = False,
    category: Category | None = None,
    abs_humidity_gkg: float | None = None,
    cfg: HumidityConfig = _DEFAULT,
) -> HumidityDecision:
    """Decide the RH-driven action against the (effective) comfort band.

    ``too_warm`` / ``in_deadband`` are evaluated against the cooling edge AFTER
    the ADR-0051 heat-day raise, so the two features compose coherently. The
    dehumidification ceiling is the EN 16798-1 category limit (via ``category``,
    default Cat II 60 %); ``abs_humidity_gkg`` (from ``humidity_ratio``) adds the
    12 g/kg absolute backstop. Both share the latched ``dry_active`` hysteresis.
    """
    if rh is None:  # no humidity sensor -> feature inactive (graceful)
        return HumidityDecision("idle", False, "no humidity sensor")
    # Dry-guard (ADR §4): never dry already-dry air. TOP precedence — the
    # absolute cap must not override the RH floor and over-dry the room.
    if rh < cfg.rh_low:
        return HumidityDecision(
            "dry_guard", False, f"RH {rh:.0f} < {cfg.rh_low:.0f}: blocked"
        )
    # Cool-first (ADR §2): when too warm, cooling handles temp AND humidity.
    if too_warm:
        return HumidityDecision("cool", False, "cool covers humidity")
    # Active dehumidification only inside the dead-band (ADR §3). Two upper
    # limits — the category RH ceiling and the absolute 12 g/kg backstop — each
    # with asymmetric hysteresis; either keeps the latch engaged until BOTH fall
    # back below their exit thresholds.
    rh_high = rh_high_for_category(category, cfg)
    rh_exit = rh_high - cfg.hysteresis
    abs_exit = cfg.abs_high - cfg.abs_hysteresis
    w = abs_humidity_gkg
    rh_over = rh >= rh_high
    abs_over = w is not None and w >= cfg.abs_high
    still_humid = rh >= rh_exit or (w is not None and w >= abs_exit)
    humid_enough = rh_over or abs_over or (prev_dry_active and still_humid)
    if in_deadband and humid_enough:
        if can_dry:
            if abs_over and w is not None and not rh_over:
                why = f"w {w:.1f} >= {cfg.abs_high:.0f} g/kg: dry"
            else:
                why = f"RH {rh:.0f} / ceiling {rh_high:.0f}: dry"
            return HumidityDecision("dry", True, why)
        if can_fan_only:  # fan re-evaporates condensate -> raises RH; never use it
            return HumidityDecision("idle", False, "no dry; fan_only raises RH")
        return HumidityDecision("idle", False, "device cannot dry")
    return HumidityDecision("idle", False, "RH within band")
