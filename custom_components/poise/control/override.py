"""Override / preset modes with timed auto-revert (ADR-0042).

Modes are an **offset on the user's comfort base**, never a free temperature:
the constraint solver therefore still clamps every mode to the norm floors/cap
(frost/mould/ASR), so no preset can break the norm — the key difference from
competitors that store free per-preset temperatures. A manual setpoint override
auto-reverts after a window so it never sticks indefinitely (community VT#1875).
Pure and unit-tested; the coordinator owns the state and applies the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OverrideMode(str, Enum):  # noqa: UP042 — explicit str+Enum, StrEnum-equivalent
    """Comfort preset. Values match HA's PRESET_* so the frontend translates them."""

    NONE = "none"
    ECO = "eco"
    COMFORT = "comfort"
    BOOST = "boost"
    AWAY = "away"


@dataclass(frozen=True, slots=True)
class OverrideConfig:
    eco_offset: float = 2.0  # K below base (energy saving)
    boost_offset: float = 1.5  # K above base (quick warm-up)
    away_offset: float = 4.0  # K below base (absence setback)
    manual_revert_h: float = 2.0  # manual setpoint auto-reverts after this many hours


_DEFAULT = OverrideConfig()


def mode_comfort_base(
    mode: OverrideMode, base: float, cfg: OverrideConfig = _DEFAULT
) -> float:
    """Effective comfort base for a preset — an offset on ``base``, not a free
    temperature, so the solver still enforces the norm envelope (ADR-0042)."""
    if mode is OverrideMode.ECO:
        return base - cfg.eco_offset
    if mode is OverrideMode.AWAY:
        return base - cfg.away_offset
    if mode is OverrideMode.BOOST:
        return base + cfg.boost_offset
    return base  # NONE / COMFORT keep the user's base


def manual_override_expired(
    set_at: float, now: float, cfg: OverrideConfig = _DEFAULT
) -> bool:
    """True once a manual setpoint override has outlived its auto-revert window.

    Addresses the most-requested override behaviour (VT#1875): a manual change
    must revert to the schedule/preset instead of holding the room high forever.
    ``set_at``/``now`` must share one clock; the coordinator passes a persisted
    *wall-clock* timestamp so a restored hold expires on real elapsed time and
    cannot outlive a restart (review C5).
    """
    return (now - set_at) >= cfg.manual_revert_h * 3600.0
