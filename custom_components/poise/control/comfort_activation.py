"""ADR-0069 tier-2 activation lifecycle, pure.

A tier-2 comfort building block (fan-CE credit, PMV offset) is released by a
PERSISTED latch — never by a per-tick predicate: ``shadow → eligible → live →
suspended``.  Four normative rules (ADR-0069 § Entscheidung 5):

* **Dwell is qualified observation time** — it grows only on ticks where
  readiness AND the entry gate actually hold (never wall-clock: three days of
  downtime add nothing) and freezes on non-qualifying ticks.
* **Schmitt hysteresis** — entry stamps the baseline after a FULL dwell; live
  holds until the time-weighted PPD exceeds ``baseline + PPD_EXIT_TOL_PCT``
  (strictly wider than the 1-pp N1 entry tolerance); any drop-out requires a
  full re-dwell and a fresh baseline.
* **The baseline carries a validity signature** — model parameters AND the
  ordered set of active predecessor features; a mismatch suspends.
* **First activations are serialized** (``may_dwell``): one feature dwells at
  a time, in ``TIER2_ORDER``, each baselining on a live-stable predecessor —
  with an explicit escape when the predecessor is impossible in this zone.

The explicit cascade (``cascade_after_invalidation``) enforces the dependency
rule even where the caller invalidates a predecessor out-of-band; the
signature's predecessor component catches the organic case.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

STATE_SHADOW = "shadow"
STATE_ELIGIBLE = "eligible"
STATE_LIVE = "live"
STATE_SUSPENDED = "suspended"
_STATES = (STATE_SHADOW, STATE_ELIGIBLE, STATE_LIVE, STATE_SUSPENDED)

# Qualified minutes the entry gate must hold before a flip (default; the
# metric maturity itself is the 3-day N1 warm-up — this dwell is the flip
# STABILITY requirement on top).
DWELL_TARGET_MIN = 24.0 * 60.0
# Schmitt exit: strictly wider than the 1-pp entry tolerance (ADR-0055 N1),
# so the latch cannot chatter at the boundary.
PPD_EXIT_TOL_PCT = 2.0

# Serialized first-activation order (ADR-0069 Umsetzungsreihenfolge 7/8).
TIER2_ORDER = ("fan_ce", "pmv_offset")


@dataclass(frozen=True, slots=True)
class TierActivation:
    """One building block's persisted activation latch."""

    state: str = STATE_SHADOW
    dwell_min: float = 0.0
    baseline_ppd: float | None = None
    baseline_signature: str | None = None
    generation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "dwell_min": round(self.dwell_min, 1),
            "baseline_ppd": self.baseline_ppd,
            "baseline_signature": self.baseline_signature,
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TierActivation:
        if not isinstance(data, dict):
            return cls()
        state = data.get("state")
        ppd = data.get("baseline_ppd")
        sig = data.get("baseline_signature")
        dwell = data.get("dwell_min")
        gen = data.get("generation")
        return cls(
            state=state if state in _STATES else STATE_SHADOW,
            dwell_min=float(dwell) if isinstance(dwell, (int, float)) else 0.0,
            baseline_ppd=float(ppd) if isinstance(ppd, (int, float)) else None,
            baseline_signature=sig if isinstance(sig, str) else None,
            generation=int(gen) if isinstance(gen, int) else 0,
        )


@dataclass(frozen=True, slots=True)
class ComfortActivation:
    """Per-zone container of the tier-2 latches + the generation counter."""

    fan_ce: TierActivation = field(default_factory=TierActivation)
    pmv_offset: TierActivation = field(default_factory=TierActivation)
    generation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fan_ce": self.fan_ce.to_dict(),
            "pmv_offset": self.pmv_offset.to_dict(),
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ComfortActivation:
        if not isinstance(data, dict):
            return cls()
        gen = data.get("generation")
        return cls(
            fan_ce=TierActivation.from_dict(data.get("fan_ce")),
            pmv_offset=TierActivation.from_dict(data.get("pmv_offset")),
            generation=int(gen) if isinstance(gen, int) else 0,
        )


def activation_signature(
    *,
    room_profile: str,
    clo_offset: float,
    model_rev: str,
    predecessors: tuple[str, ...],
) -> str:
    """The baseline validity signature: model config + active predecessors.

    A changed room profile, household clo offset or PMV model revision makes
    an old PPD baseline incomparable — as does a changed set of live
    predecessor features (*baseline B = system state with A active*).
    """
    return f"{model_rev}|{room_profile}|{clo_offset:+.2f}|{','.join(predecessors)}"


def step_tier(
    act: TierActivation,
    *,
    ready: bool,
    entry_ok: bool,
    ppd: float,
    signature: str,
    dt_min: float,
    allowed: bool,
    next_generation: int,
    dwell_target_min: float = DWELL_TARGET_MIN,
    exit_tol: float = PPD_EXIT_TOL_PCT,
    impossible: bool = False,
) -> TierActivation:
    """Advance one latch by one scored tick.

    ``ready`` is the block's control-readiness (``pmv_control_ready`` etc.),
    ``entry_ok`` the N1 metric gate (``flip_metric_ok``), ``allowed`` the
    serialization verdict (``may_dwell``).  ``signature`` is the CURRENT
    validity signature — a live latch whose stamp differs suspends.
    ``impossible`` marks STRUCTURAL impossibility (e.g. no ``fan_only``
    capability for fan_ce): the latch retires to shadow — it must neither
    dwell nor block the serialization (P1 field finding: a mere
    ``ready=False`` would freeze a stale persisted ``eligible`` in place and
    deadlock the successor forever).  A live exit still cascades via the
    caller's live→non-live detection.
    """
    if impossible:
        if act.state == STATE_SHADOW:
            return act
        return TierActivation(state=STATE_SHADOW, generation=act.generation)
    if act.state == STATE_LIVE:
        worsened = act.baseline_ppd is not None and ppd > act.baseline_ppd + exit_tol
        if not ready or act.baseline_signature != signature or worsened:
            return TierActivation(state=STATE_SUSPENDED, generation=act.generation)
        return act
    if act.state in (STATE_SHADOW, STATE_SUSPENDED):
        if ready and allowed:
            return TierActivation(state=STATE_ELIGIBLE, generation=act.generation)
        return act
    # eligible: qualified dwell — grows only when everything holds, else frozen.
    if not (ready and entry_ok and allowed):
        return act
    dwell = act.dwell_min + dt_min
    if dwell >= dwell_target_min:
        return TierActivation(
            state=STATE_LIVE,
            dwell_min=dwell,
            baseline_ppd=ppd,
            baseline_signature=signature,
            generation=next_generation,
        )
    return replace(act, dwell_min=dwell)


def latch_dwelt(prev: TierActivation, nxt: TierActivation) -> bool:
    """Display-only: did this tick add qualified dwell time to an eligible latch?

    Feeds the card's maturing-progress hint ("reift · X/24 h"): a frozen dwell
    (non-qualifying tick) renders as paused. Never used for control decisions.
    """
    return nxt.state == STATE_ELIGIBLE and nxt.dwell_min > prev.dwell_min


def may_dwell(
    container: ComfortActivation,
    feature: str,
    *,
    predecessor_impossible: bool = False,
) -> bool:
    """Serialization: one dwelling feature at a time, in TIER2_ORDER.

    A later feature starts only on a LIVE predecessor — or when the
    predecessor is structurally impossible in this zone (no ``fan_only``
    capability), so the serialization can never deadlock the successor.
    """
    idx = TIER2_ORDER.index(feature)
    for other in TIER2_ORDER:
        if other != feature and getattr(container, other).state == STATE_ELIGIBLE:
            return False
    if idx > 0 and not predecessor_impossible:
        pred = getattr(container, TIER2_ORDER[idx - 1])
        if pred.state != STATE_LIVE:
            return False
    return True


def cascade_after_invalidation(
    container: ComfortActivation, *, invalidated_generation: int
) -> ComfortActivation:
    """ADR-0069 cascade: dependents of an invalidated feature re-baseline.

    Every feature activated AFTER the invalidated one (higher generation)
    drops to ``suspended`` with its baseline cleared — it measured itself
    against a system state that no longer exists.  The invalidated feature
    itself is the caller's business.
    """

    def _drop(a: TierActivation) -> TierActivation:
        if a.generation > invalidated_generation and a.state in (
            STATE_LIVE,
            STATE_ELIGIBLE,
        ):
            return TierActivation(state=STATE_SUSPENDED, generation=a.generation)
        return a

    return ComfortActivation(
        fan_ce=_drop(container.fan_ce),
        pmv_offset=_drop(container.pmv_offset),
        generation=container.generation,
    )
