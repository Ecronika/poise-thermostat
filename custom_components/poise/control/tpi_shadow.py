"""Shadow TPI valve duty for the live path (ADR-0036, shadow stage).

Computes what the direct-valve TPI controller *would* command (the valve-open
duty) against the live learned model, but only to **report** it — it never
writes the valve (shadow-estimator principle, ADR-0026/0033). Active once a
writable valve-open entity is detected on the device. Wiring the actual valve
write is a separate, cold-season-validated step.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..estimation.thermal_ekf import ThermalModel
from .tpi import seed_from_model, tpi_duty


@dataclass(frozen=True, slots=True)
class TpiShadow:
    """What the TPI valve controller would command this tick (diagnostic only)."""

    active: bool
    duty: float | None = None  # 0..1 valve-open fraction
    valve_percent: float | None = None  # 0..100, what we would write
    coef_int: float | None = None
    coef_ext: float | None = None


def evaluate_tpi_shadow(
    *,
    valve_available: bool,
    model: ThermalModel,
    target: float,
    room: float,
    t_out: float,
) -> TpiShadow:
    """Compute the shadow TPI duty; inactive until a writable valve is present."""
    if not valve_available:
        return TpiShadow(active=False)
    coef_int, coef_ext = seed_from_model(model.alpha, model.beta_h)
    duty = tpi_duty(coef_int, coef_ext, target, room, t_out)
    return TpiShadow(
        active=True,
        duty=round(duty, 3),
        valve_percent=round(duty * 100.0),
        coef_int=round(coef_int, 3),
        coef_ext=round(coef_ext, 4),
    )
