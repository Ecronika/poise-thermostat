"""Heating-degree-hour savings estimate in kWh/€ (ADR-0045).

Vesta *method* (verified from `portbusy/ha-vesta` `climate.py`), re-implemented:
estimate how much heating energy Poise saves by holding the room below the full
comfort base during setback / eco / coasting. Each eligible minute accumulates a
saved fraction ``ΔT_saved / ΔT_base`` (the share of the heating gradient not
spent); the monthly mean fraction × a configured annual heating consumption ÷ 12
× tariff gives kWh/€. It is an **estimate** from a configured annual figure, not
metered energy — honest by construction. Pure and unit-tested; the coordinator
accumulates and persists it. Summer (no heating gradient) accrues nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class HdhConfig:
    annual_kwh: float = 12000.0  # configured annual heating energy (sane EU default)
    price_eur_kwh: float = 0.30  # tariff
    base_floor: float = 1.0  # never divide the gradient by less than this [K]


_DEFAULT = HdhConfig()


def report_price_eur_kwh(
    explicit: float | int | str | None,
    source: object,
    *,
    gas: float,
    electric: float,
) -> float:
    """Report-only €/kWh fallback: an explicit price wins; otherwise pick by heat
    source (a gas radiator is ~3× cheaper than electricity, so a fixed electric
    default would overstate a gas home's running cost — report trust, no control
    effect)."""
    if explicit is not None:
        return float(explicit)
    if isinstance(source, str) and source.strip().lower() == "radiator":
        return gas
    return electric


def saved_fraction_tick(
    comfort: float,
    setpoint: float,
    outdoor: float,
    dt_min: float,
    cfg: HdhConfig = _DEFAULT,
) -> float:
    """Saved fraction contributed by ``dt_min`` minutes: ``ΔT_saved/ΔT_base × min``.

    Zero unless heating is plausible (``comfort > outdoor``) and the applied
    setpoint is below the comfort base (an actual setback).
    """
    if comfort <= outdoor:
        return 0.0
    saved = max(0.0, comfort - setpoint)
    base = max(cfg.base_floor, comfort - outdoor)
    return (saved / base) * dt_min


@dataclass(frozen=True, slots=True)
class HdhSavings:
    """Monthly accumulator of saved fraction vs eligible minutes (kWh/€ on report)."""

    saved_min: float = 0.0  # Σ (ΔT_saved/ΔT_base) × minutes
    eligible_min: float = 0.0  # Σ minutes with a heating gradient
    month: int | None = None

    def observe(
        self,
        *,
        comfort: float,
        setpoint: float,
        outdoor: float,
        dt_min: float,
        now_month: int,
        cfg: HdhConfig = _DEFAULT,
    ) -> HdhSavings:
        # Reset the accumulators at the start of each calendar month.
        base = self if self.month in (None, now_month) else HdhSavings(month=now_month)
        if comfort <= outdoor:  # no heating context (e.g. summer) -> accrue nothing
            return replace(base, month=now_month)
        return HdhSavings(
            saved_min=base.saved_min
            + saved_fraction_tick(comfort, setpoint, outdoor, dt_min, cfg),
            eligible_min=base.eligible_min + dt_min,
            month=now_month,
        )

    def report(self, cfg: HdhConfig = _DEFAULT) -> dict[str, float]:
        """Estimated savings this month: kWh, €, and the saved percentage."""
        if self.eligible_min <= 0.0 or cfg.annual_kwh <= 0.0:
            return {"kwh": 0.0, "eur": 0.0, "pct": 0.0}
        frac = min(self.saved_min / self.eligible_min, 1.0)
        kwh = frac * cfg.annual_kwh / 12.0
        return {
            "kwh": round(kwh, 2),
            "eur": round(kwh * cfg.price_eur_kwh, 2),
            "pct": round(frac * 100.0, 1),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "saved_min": self.saved_min,
            "eligible_min": self.eligible_min,
            "month": self.month,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HdhSavings:
        return cls(
            saved_min=float(d.get("saved_min", 0.0)),
            eligible_min=float(d.get("eligible_min", 0.0)),
            month=d.get("month"),
        )
