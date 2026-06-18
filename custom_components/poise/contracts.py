"""Typed data contracts exchanged between Poise layers (ADR-0005).

These frozen dataclasses are the *only* objects allowed to cross a layer
boundary — never plain dicts. Every value carries its provenance and
confidence so degradation is never hidden (ADR-0012, charter G15).

Pipeline order of contracts:
    Reading -> ThermalState -> ComfortCorridor -> ControlRequest -> ActuatorCommand
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Source(Enum):
    """Provenance along the degradation ladder (ADR-0012, charter G14)."""

    MEASURED = "measured"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    DEFAULT = "default"


class Precedence(IntEnum):
    """Hard conflict ordering (charter). Lower value = higher priority."""

    SAFETY = 0
    HEALTH = 1
    COMFORT = 2
    EFFICIENCY = 3
    LEARNING = 4
    OPERATION = 5


class Maturity(IntEnum):
    """Learning maturity phase (ADR-0009 cold-start staging)."""

    COLD = 0  # < 5 observations
    EARLY = 1  # < 50
    LEARNING = 2  # < 150
    MATURE = 3  # >= 150


class ActuatorPath(Enum):
    """Exclusive actuation path per device (ADR-0015)."""

    TPI_VALVE = "tpi_valve"
    CALIBRATION = "calibration"
    PI_SETPOINT = "pi_setpoint"
    SETPOINT = "setpoint"  # Phase-0 trivial path


@dataclass(frozen=True, slots=True)
class Reading:
    """A conditioned input value with provenance (ADR-0005/0012)."""

    value: float
    unit: str
    source: Source
    confidence: float
    ts: float
    sensor_ok: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of [0, 1]: {self.confidence}")


@dataclass(frozen=True, slots=True)
class ThermalState:
    """Estimated building-physics state (ADR-0002). Single source of truth.

    Phase 0 fills only ``t_air``; the Extended Kalman Filter populates the
    remaining fields from Phase 2 onward.
    """

    t_air: float
    tau: float
    loss_uc: float
    beta_h: float
    beta_c: float
    beta_s: float
    beta_o: float
    q_solar: float
    t_rm: float
    confidence: float
    maturity: Maturity
    dewpoint: float | None = None
    surface_rh: float | None = None


@dataclass(frozen=True, slots=True)
class Bound:
    """A single comfort/safety bound plus the cause that imposes it (G3/G15)."""

    value: float
    cause: str


@dataclass(frozen=True, slots=True)
class ComfortCorridor:
    """Allowed setpoint corridor; the binding bound is computed, not stored
    (ADR-0013 constraint composition). ``quantity`` is already air-side, i.e.
    the operative->air transform (ADR-0017) has been applied.
    """

    lower: tuple[Bound, ...]
    upper: tuple[Bound, ...]
    target: float
    quantity: str = "air"

    def binding_lower(self) -> Bound:
        return max(self.lower, key=lambda b: b.value)

    def binding_upper(self) -> Bound:
        return min(self.upper, key=lambda b: b.value)

    def clamp(self, value: float) -> tuple[float, str | None]:
        """Clamp into ``[max(lower), min(upper)]``; return (value, cause|None)."""
        lo = self.binding_lower()
        hi = self.binding_upper()
        if value < lo.value:
            return lo.value, lo.cause
        if value > hi.value:
            return hi.value, hi.cause
        return value, None


@dataclass(frozen=True, slots=True)
class ControlRequest:
    """A controller's *request* — never a direct actuator command (ADR-0013)."""

    actuator_id: str
    path: ActuatorPath
    target_setpoint: float | None = None
    power: float | None = None  # 0..1
    duty: float | None = None  # 0..1
    urgency: Precedence = Precedence.COMFORT
    reason: str = ""
    regime: str = "hold"


@dataclass(frozen=True, slots=True)
class ActuatorCommand:
    """The single arbitrated command written to exactly one actuator (ADR-0013)."""

    actuator_id: str
    path: ActuatorPath
    value: float
    hvac_mode: str
    reason: str = ""
    clamped_by: str | None = None
