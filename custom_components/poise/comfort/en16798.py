"""EN 16798-1 adaptive comfort for free-running buildings (Annex B).

Neutral operative comfort temperature:  Θ_comf = 0.33 · T_rm + 18.8
valid for 10 °C <= T_rm <= 30 °C. Category tolerances are asymmetric (the
upper bound sits closer to neutral than the lower bound).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

T_RM_MIN: float = 10.0
T_RM_MAX: float = 30.0


class Category(Enum):
    """EN 16798-1 comfort categories (I = highest expectation)."""

    I = "I"  # noqa: E741
    II = "II"
    III = "III"


# Asymmetric tolerances around the comfort temperature [K].
_UPPER: dict[Category, float] = {Category.I: 2.0, Category.II: 3.0, Category.III: 4.0}
_LOWER: dict[Category, float] = {Category.I: 3.0, Category.II: 4.0, Category.III: 5.0}


@dataclass(frozen=True, slots=True)
class ComfortBand:
    comfort: float  # neutral operative comfort temperature [°C]
    lower: float  # lower operative limit [°C]
    upper: float  # upper operative limit [°C]
    extrapolated: bool  # True if T_rm was clamped to the [10, 30] validity range


def comfort_temperature(t_rm: float) -> float:
    """Neutral operative comfort temperature (EN 16798-1 Eq. B.x)."""
    return 0.33 * t_rm + 18.8


def adaptive_band(t_rm: float, category: Category = Category.II) -> ComfortBand:
    """Adaptive operative comfort band for the given running mean and category."""
    clamped = min(max(t_rm, T_RM_MIN), T_RM_MAX)
    comfort = comfort_temperature(clamped)
    return ComfortBand(
        comfort=comfort,
        lower=comfort - _LOWER[category],
        upper=comfort + _UPPER[category],
        extrapolated=clamped != t_rm,
    )


# Fixed design operative-temperature ranges for *mechanically conditioned*
# buildings (EN 16798-1: heating = winter, cooling = summer). The adaptive band
# above applies only to free-running buildings; when actively heating/cooling
# these fixed category ranges govern. Values consistent with the Smart Setpoint
# blueprint (Cat. II heating 20-24, cooling 23-26).
HEATING_LOWER: dict[Category, float] = {
    Category.I: 21.0,
    Category.II: 20.0,
    Category.III: 19.0,
}
HEATING_UPPER: dict[Category, float] = {
    Category.I: 23.0,
    Category.II: 24.0,
    Category.III: 25.0,
}
COOLING_LOWER: dict[Category, float] = {
    Category.I: 23.0,
    Category.II: 23.0,
    Category.III: 22.0,
}
COOLING_UPPER: dict[Category, float] = {
    Category.I: 25.0,
    Category.II: 26.0,
    Category.III: 27.0,
}
