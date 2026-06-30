"""Humidity management: dry-guard + active dehumidification decision (ADR-0050).

Cool-first: cooling dehumidifies and serves Poise's temperature primacy, so
``dry`` is reserved for the gap cooling cannot fill without overcooling (RH high,
temperature already inside the dead-band). Asymmetric hysteresis (enter 60 %,
exit 55 %) mirrors HA-core ``generic_hygrostat``. A dry-guard blocks any
dehumidifying action below ``rh_low`` so already-dry air is not dried further.
``fan_only`` is NEVER used to dehumidify — a fan over a wet evaporator coil
re-evaporates condensate and RAISES RH. Pure; wired shadow-first.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RH_HIGH: float = 60.0  # enter active dehumidification
DEFAULT_RH_LOW: float = 40.0  # dry-guard floor; below this, block all drying
DEFAULT_RH_HYSTERESIS: float = 5.0  # exit RH = rh_high - hysteresis (55 %)


@dataclass(frozen=True, slots=True)
class HumidityConfig:
    rh_high: float = DEFAULT_RH_HIGH
    rh_low: float = DEFAULT_RH_LOW
    hysteresis: float = DEFAULT_RH_HYSTERESIS


_DEFAULT = HumidityConfig()


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
    cfg: HumidityConfig = _DEFAULT,
) -> HumidityDecision:
    """Decide the RH-driven action against the (effective) comfort band.

    ``too_warm`` / ``in_deadband`` are evaluated against the cooling edge AFTER
    the ADR-0051 heat-day raise, so the two features compose coherently.
    """
    if rh is None:  # no humidity sensor -> feature inactive (graceful)
        return HumidityDecision("idle", False, "no humidity sensor")
    # Dry-guard (ADR §4): never dry already-dry air.
    if rh < cfg.rh_low:
        return HumidityDecision(
            "dry_guard", False, f"RH {rh:.0f} < {cfg.rh_low:.0f}: blocked"
        )
    # Cool-first (ADR §2): when too warm, cooling handles temp AND humidity.
    if too_warm:
        return HumidityDecision("cool", False, "cool covers humidity")
    # Active dehumidification only inside the dead-band (ADR §3), with
    # asymmetric hysteresis: enter at rh_high, hold down to rh_high - hysteresis.
    exit_rh = cfg.rh_high - cfg.hysteresis
    humid_enough = rh >= cfg.rh_high or (prev_dry_active and rh >= exit_rh)
    if in_deadband and humid_enough:
        if can_dry:
            return HumidityDecision(
                "dry", True, f"RH {rh:.0f} >= {cfg.rh_high:.0f}: dry"
            )
        if can_fan_only:  # fan re-evaporates condensate -> raises RH; never use it
            return HumidityDecision("idle", False, "no dry; fan_only raises RH")
        return HumidityDecision("idle", False, "device cannot dry")
    return HumidityDecision("idle", False, "RH within band")
