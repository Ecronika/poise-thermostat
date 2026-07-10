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
    t_out: float | None = None
    prediction_std: float | None = None
    identified: bool | None = None


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


@dataclass(frozen=True, slots=True)
class ZoneRequest:
    """One zone's per-tick state handed to the multi-zone hub (ADR-0038).

    The hub builds one of these per active zone in
    ``hub_coordinator._collect_requests`` by *pulling* the zone's last published
    ``runtime_data`` snapshot (there is no shared push registry), then resolves
    the shared resources (boiler, power budget, compressor, flow temp) from the
    whole set. It is never an actuator command; the hub exposes the resolved
    result as diagnostics and (opt-in) actuates only the shared boiler — it does
    not send a per-zone reply back (see the ADR-0038 correction note).
    """

    zone_id: str
    heating: bool
    hvac_action: str
    heat_demand: float  # 0..1, this zone's call-for-heat intensity
    comfort_gap: float  # target - room (K); positive = below target
    frost_active: bool
    controls_boiler: bool
    mono_ts: float
    declared_power: float | None = None  # weighting unit, free choice (charter)
    flow_temp_request: float | None = None
    source_pref: str | None = None  # energy-aware source policy (Deliverable 4)
    compressor_group: str | None = None
    health_active: bool = False  # mould/health floor binding (excluded from shed)
    frozen: bool = False  # room sensor stale — call-for-heat not trusted (V9)


@dataclass(frozen=True, slots=True)
class ResourceRelease:
    """RESERVED / UNUSED — the per-zone hub reply from the original ADR-0038 design.

    NOTE: the shipped hub does **not** use this type. It resolves shared resources
    by pulling each zone's ``runtime_data`` snapshot and exposes the result as a
    plain diagnostics dict (see ``hub_coordinator._collect_requests`` /
    ``_async_update_data``); there is no per-zone ``ResourceRelease`` reply channel,
    and nothing imports or instantiates this class. It is kept as a reserved
    contract for the not-yet-wired zone-side cap enforcement (ADR-0038 §3, S3/S4);
    see the "Nachtrag/Korrektur" section in ADR-0038.

    Design intent (not wired): the hub would publish this release and the zone
    would compose ``power_cap``/``shed`` into its own constraint solver (ADR-0035)
    as an additional high-precedence bound, keeping single-writer.
    """

    zone_id: str
    shed: bool = False
    power_cap: float | None = None
    source_grant: str | None = None
    mono_ts: float = 0.0
