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
# EN 16798-1: the lower operative-limit line is only defined for 15 <= T_rm; the
# upper line extends down to 10. Below 15 the lower bound is extrapolated.
T_RM_LOWER_MIN: float = 15.0


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
    extrapolated: bool  # T_rm outside [10, 30] -> comfort/upper line extrapolated
    extrapolated_lower: bool  # T_rm < 15 -> lower operative limit extrapolated


def comfort_temperature(t_rm: float) -> float:
    """Neutral operative comfort temperature, EN 16798-1:2019 Annex B:
    ``Θ_comf = 0.33 · T_rm + 18.8`` [°C]."""
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
        extrapolated_lower=t_rm < T_RM_LOWER_MIN,
    )


# Fixed design operative-temperature ranges for *mechanically conditioned*
# buildings (heating = winter, cooling = summer). The adaptive band above
# applies only to free-running buildings; when actively heating/cooling these
# fixed category ranges govern. Source (ADR-0023 N1): the EN 16798-1:2019
# design criteria as tabulated in REHVA Journal 04/2019 (Boerstra, Table 1),
# operative, 1.0 clo winter / 0.5 clo summer, 1.2 met. The heating rows below
# are the OFFICE row (21-23 / 20-24 / 19-25 °C) — the default space type; the
# cooling rows are identical for offices and residential spaces.
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
# The RESIDENTIAL row of the same table (21-25 / 20-25 / 18-25 °C). Until
# ADR-0023 N1 every zone used the office row, so a bedroom or kitchen in
# Category III was clamped up to 19 °C against its own configuration, and a
# Category II bathroom at 24 °C sat on a ceiling that is not the residential
# one — which also left the PMV band shift no room to act there.
HEATING_LOWER_RESIDENTIAL: dict[Category, float] = {
    Category.I: 21.0,
    Category.II: 20.0,
    Category.III: 18.0,
}
HEATING_UPPER_RESIDENTIAL: dict[Category, float] = {
    Category.I: 25.0,
    Category.II: 25.0,
    Category.III: 25.0,
}


def heating_band(category: Category, *, residential: bool) -> tuple[float, float]:
    """The heating-season design range ``(lower, upper)`` for a space type."""
    if residential:
        return HEATING_LOWER_RESIDENTIAL[category], HEATING_UPPER_RESIDENTIAL[category]
    return HEATING_LOWER[category], HEATING_UPPER[category]


COOLING_LOWER: dict[Category, float] = {
    Category.I: 23.5,
    Category.II: 23.0,
    Category.III: 22.0,
}
COOLING_UPPER: dict[Category, float] = {
    Category.I: 25.5,
    Category.II: 26.0,
    Category.III: 27.0,
}
# ADR-0023 N2: the cooling DESIGN value an occupied, actively cooled room is
# held at — the category upper limit minus a 1 K margin, so control deviation
# does not breach the limit. EN 16798-1 sizes cooling on the upper value of the
# range; holding the room at the LOWER edge (23 °C in Category II, as the
# comfort-base coupling did until v0.195.0) costs cooling energy for no
# comfort the category asks for.
COOLING_DESIGN_MARGIN_K: float = 1.0
COOLING_DESIGN: dict[Category, float] = {
    c: COOLING_UPPER[c] - COOLING_DESIGN_MARGIN_K for c in Category
}
