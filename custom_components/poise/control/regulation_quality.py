"""Control-accuracy / regulation-quality metric (EN 15500-1 CA), pure (ADR-0055).

Poise doctrine: no feature leaves shadow without a measurable acceptance
criterion. This is that measure — a continuous, bilateral control-quality metric
that turns ADR-0033's prose "flip criteria" into executable numbers and becomes
the gate for every shadow->live flip.

Three time-weighted (EWMA) figures over scored (comfort-window, unmasked) ticks:
  * ``deviation_k``     mean Kelvin the room sits OUTSIDE the comfort band (0
                        in-band; EN 15500-1 control accuracy in a dead-band
                        system — inside the band every point is "on target").
  * ``in_band``         fraction of scored time inside [heat_sp, cool_sp].
  * ``cycles_per_hour`` regime-change rate (mode/actuation transitions) — the
                        hunting detector a band-only metric would miss.

Shadow-first: the coordinator only reports these; the flip gate (meets_quality)
is defined here but wired later, per device class (ADR-0055 section 6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_HORIZON_H = 72.0  # EWMA time constant [h] ~ "recent sustained" quality
DEV_MAX_K = 0.5  # conservative default flip thresholds (per class in wiring)
CYCLE_MAX_PER_H = 3.0
BAND_MIN = 0.9
WARMUP_MIN = 3.0 * 24.0 * 60.0  # >= 3 days of scored comfort minutes before a flip
PPD_SEED = 5.0  # ISO 7730 theoretical optimum — PPD can never sit below 5 %
# N1: a comfort flip may not worsen the time-weighted PPD beyond this. One
# percentage point — smaller deltas are pseudo-accuracy (ADR-0054: PMV
# subtleties below +-0.3 carry no information).
PPD_TOL_PCT = 1.0

# ADR-0055 N1 risk tiers — "alle Shadow->live-Flips" is deliberately NOT one
# uniform bar (the ADR-0053 ambiguity). The tier decides which metric legs a
# flip must pass; opt-in/presence/safety guards always live in the wiring.
FLIP_TIER_ACTUATOR = "actuator"  # MPC/PI/TPI/valve writes: full CA gate
FLIP_TIER_COMFORT = "comfort"  # norm-clamped comfort shifts: CA gate + PPD
FLIP_TIER_REVERSIBLE = "reversible"  # compressor-free fan writes: no metric


@dataclass(frozen=True, slots=True)
class RegulationQuality:
    """EWMA accumulator of control quality (persist via to_dict/from_dict)."""

    # Optimistic seed (0 K deviation, 100 % in band): inert as a flip gate
    # only because ``meets_quality`` additionally requires
    # ``minutes >= warmup_min``.
    deviation_k: float = 0.0
    in_band: float = 1.0
    cycles_per_hour: float = 0.0
    minutes: float = 0.0
    last_mode: str = ""
    # ADR-0055 N1: time-weighted PPD over VALID-PMV ticks — the comfort-flip
    # gate component. Own maturity clock: PMV validity (ISO 7730 domain) and
    # the CA fairness mask diverge (e.g. bedroom met 0.7 -> pmv_valid False).
    ppd: float = PPD_SEED
    ppd_minutes: float = 0.0

    def observe(
        self,
        *,
        room: float,
        heat_sp: float,
        cool_sp: float,
        mode: str,
        dt_min: float,
        horizon_h: float = DEFAULT_HORIZON_H,
    ) -> RegulationQuality:
        """Fold one scored tick into the EWMA. Call only on unmasked comfort ticks."""
        dev = max(0.0, heat_sp - room, room - cool_sp)
        inb = 1.0 if heat_sp <= room <= cool_sp else 0.0
        moved = 1.0 if (self.last_mode != "" and mode != self.last_mode) else 0.0
        dt_h = max(dt_min, 1e-6) / 60.0
        alpha = 1.0 - math.exp(-dt_min / (horizon_h * 60.0))
        inst_rate = moved / dt_h
        return RegulationQuality(
            deviation_k=(1.0 - alpha) * self.deviation_k + alpha * dev,
            in_band=(1.0 - alpha) * self.in_band + alpha * inb,
            cycles_per_hour=(1.0 - alpha) * self.cycles_per_hour + alpha * inst_rate,
            minutes=self.minutes + dt_min,
            last_mode=mode,
            ppd=self.ppd,
            ppd_minutes=self.ppd_minutes,
        )

    def observe_ppd(
        self,
        *,
        ppd: float,
        dt_min: float,
        horizon_h: float = DEFAULT_HORIZON_H,
    ) -> RegulationQuality:
        """Fold one VALID-PMV tick's PPD into the EWMA (ADR-0055 N1).

        Call only on unmasked comfort ticks whose PMV passed the ISO 7730
        validity gate (ADR-0054 V3) — invalid samples would let a bedroom's
        out-of-domain met poison the comfort-flip criterion.
        """
        alpha = 1.0 - math.exp(-dt_min / (horizon_h * 60.0))
        return RegulationQuality(
            deviation_k=self.deviation_k,
            in_band=self.in_band,
            cycles_per_hour=self.cycles_per_hour,
            minutes=self.minutes,
            last_mode=self.last_mode,
            ppd=(1.0 - alpha) * self.ppd + alpha * ppd,
            ppd_minutes=self.ppd_minutes + dt_min,
        )

    @property
    def time_in_band_pct(self) -> float:
        return round(self.in_band * 100.0, 1)

    def to_dict(self) -> dict[str, float | str]:
        return {
            "deviation_k": round(self.deviation_k, 4),
            "in_band": round(self.in_band, 4),
            "cycles_per_hour": round(self.cycles_per_hour, 4),
            "minutes": round(self.minutes, 1),
            "last_mode": self.last_mode,
            "ppd": round(self.ppd, 4),  # N1 (defaulted: additive)
            "ppd_minutes": round(self.ppd_minutes, 1),
        }

    @classmethod
    def from_dict(cls, data: dict[str, float | str] | None) -> RegulationQuality:
        if not data:
            return cls()
        return cls(
            deviation_k=float(data.get("deviation_k", 0.0)),
            in_band=float(data.get("in_band", 1.0)),
            cycles_per_hour=float(data.get("cycles_per_hour", 0.0)),
            minutes=float(data.get("minutes", 0.0)),
            last_mode=str(data.get("last_mode", "")),
            ppd=float(data.get("ppd", PPD_SEED)),  # pre-N1 dicts: defaults
            ppd_minutes=float(data.get("ppd_minutes", 0.0)),
        )


def ca_tick_scorable(
    *,
    room: float,
    heat_sp: float,
    cool_sp: float,
    can_heat: bool,
    can_cool: bool,
) -> bool:
    """Capability fairness mask for the CA fold (ADR-0055 field calibration).

    A band violation the zone structurally CANNOT actuate against measures the
    weather, not the controller — a heat-only TRV zone in a summer hot spell
    would otherwise sit "out of band" for days and never clear ``band_min``
    (field finding 2026-08-08: Bad 46 % above the cool edge with no cooling
    capability).  Such ticks are not scored at all (same semantics as the
    frozen/window mask: the elapsed-minute anchor keeps running and the gap is
    capped by the caller).  In-band ticks and violations the zone CAN actuate
    against always score; the PPD leg is deliberately untouched — it measures
    experienced comfort, not controller capability.
    """
    if room > cool_sp and not can_cool:
        return False
    return not (room < heat_sp and not can_heat)


def meets_quality(
    q: RegulationQuality,
    *,
    identified: bool,
    dev_max: float = DEV_MAX_K,
    cycle_max: float = CYCLE_MAX_PER_H,
    band_min: float = BAND_MIN,
    warmup_min: float = WARMUP_MIN,
) -> bool:
    """Steady-state flip gate (ADR-0055 s5). Dwell/hysteresis lives in wiring."""
    return (
        identified
        and q.minutes >= warmup_min
        and q.deviation_k <= dev_max
        and q.cycles_per_hour <= cycle_max
        and q.in_band >= band_min
    )


def meets_comfort_quality(
    q: RegulationQuality,
    *,
    identified: bool,
    baseline_ppd: float | None = None,
    dev_max: float = DEV_MAX_K,
    cycle_max: float = CYCLE_MAX_PER_H,
    band_min: float = BAND_MIN,
    warmup_min: float = WARMUP_MIN,
    ppd_tol: float = PPD_TOL_PCT,
) -> bool:
    """The Tier-2 comfort-feature flip gate (ADR-0055 N1).

    A comfort feature's benefit shows in the PPD, not in the band deviation —
    and the PMV offset SHIFTS the very band the CA metric measures against
    (the Eigenband problem the ADR names itself).  Hence: the full CA gate,
    plus a MATURE time-weighted PPD, plus — once a pre-flip ``baseline_ppd``
    snapshot exists (the wiring stamps it at flip time) — the non-worsening
    check: the flip is kept only while PPD stays within tolerance of the
    baseline.  ``baseline_ppd=None`` is the ENTRY form (no baseline yet).
    """
    return (
        meets_quality(
            q,
            identified=identified,
            dev_max=dev_max,
            cycle_max=cycle_max,
            band_min=band_min,
            warmup_min=warmup_min,
        )
        and q.ppd_minutes >= warmup_min
        and (baseline_ppd is None or q.ppd <= baseline_ppd + ppd_tol)
    )


def flip_metric_ok(
    tier: str,
    q: RegulationQuality,
    *,
    identified: bool,
    baseline_ppd: float | None = None,
) -> bool:
    """Route a flip candidate to its tier's metric gate (ADR-0055 N1).

    Tier 3 (reversible, compressor-free — e.g. ``fan_mode=low`` circulation)
    passes the METRIC unconditionally: its acceptance lives entirely in the
    wiring (opt-in, presence gating, safety guards) and it must not wait a
    field season behind the actuator gate.  Unknown tiers fail CLOSED — a
    typo in the wiring may never soften a gate.
    """
    if tier == FLIP_TIER_REVERSIBLE:
        return True
    if tier == FLIP_TIER_COMFORT:
        return meets_comfort_quality(
            q, identified=identified, baseline_ppd=baseline_ppd
        )
    if tier == FLIP_TIER_ACTUATOR:
        return meets_quality(q, identified=identified)
    return False
