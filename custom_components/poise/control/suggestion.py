"""L2 override-suggestion detection (ADR-0060) — pure, observe-and-propose.

Reads the persisted L1 override statistic (ADR-0059 §5) and detects the ADR's
deliberately conservative multi-day pattern: at least three same-direction
nudges of at least 0.5 K within the same schedule phase inside 14 days.  The
mapping into a suggestion follows the ADR's two readings: a comfort-phase
pattern proposes a comfort-base shift (step capped at 0.5 K), an upward
setback-phase pattern proposes starting the comfort window 30 min earlier
("Vorzieh" wish).  A downward setback pattern has no ADR mapping and stays
silent.  Detection never changes anything — the visible repair-flow suggestion
and the config write live in the glue; a rejection suppresses exactly this
pattern key for 30 days.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUGGEST_MIN_EVENTS = 3
SUGGEST_MIN_DELTA_K = 0.5
SUGGEST_WINDOW_DAYS = 14.0
SUGGEST_STEP_K = 0.5  # proposal step cap (ADR-0060 §1)
SUGGEST_EARLIER_MIN = 30  # comfort-window advance proposal
SUGGEST_REJECT_DAYS = 30.0  # rejection suppresses the same pattern

_DAY_S = 86400.0
_PHASES = ("comfort", "setback")


@dataclass(frozen=True, slots=True)
class OverrideSuggestion:
    """One detected pattern, mapped to its ADR-0060 proposal."""

    kind: str  # "comfort_base" | "comfort_earlier"
    direction: int  # +1 | -1
    step_k: float | None  # comfort_base: the capped base shift
    step_min: int | None  # comfort_earlier: window advance [min]
    evidence: int  # qualifying events inside the window
    phase: str  # the schedule phase the pattern lives in

    @property
    def key(self) -> str:
        """Stable pattern identity for the 30-day rejection suppression."""
        return f"{self.kind}:{self.direction:+d}"


def detect_override_pattern(
    stats: list[dict[str, Any]],
    *,
    now_ts: float,
) -> OverrideSuggestion | None:
    """The ADR-0060 §1 pattern predicate over the L1 statistic.

    Malformed events (old shapes, missing/garbage keys) are skipped, never
    raising — the statistic is store-restored data.
    """
    cutoff = now_ts - SUGGEST_WINDOW_DAYS * _DAY_S
    buckets: dict[tuple[str, int], list[float]] = {}
    for ev in stats:
        ts = ev.get("ts")
        delta = ev.get("delta")
        direction = ev.get("direction")
        phase = ev.get("phase")
        if not isinstance(ts, (int, float)) or float(ts) < cutoff:
            continue
        if not isinstance(delta, (int, float)) or abs(delta) < SUGGEST_MIN_DELTA_K:
            continue
        if direction not in (1, -1) or phase not in _PHASES:
            continue
        buckets.setdefault((str(phase), int(direction)), []).append(float(ts))
    candidates = [
        (len(tss), max(tss), phase, direction)
        for (phase, direction), tss in buckets.items()
        if len(tss) >= SUGGEST_MIN_EVENTS
        # A downward setback pattern has no ADR mapping (deeper setback is
        # not proposed) — filtered before selection, not silently mapped.
        and not (phase == "setback" and direction == -1)
    ]
    if not candidates:
        return None
    count, _latest, phase, direction = max(candidates)
    if phase == "comfort":
        return OverrideSuggestion(
            kind="comfort_base",
            direction=direction,
            step_k=SUGGEST_STEP_K,
            step_min=None,
            evidence=count,
            phase=phase,
        )
    return OverrideSuggestion(
        kind="comfort_earlier",
        direction=direction,
        step_k=None,
        step_min=SUGGEST_EARLIER_MIN,
        evidence=count,
        phase=phase,
    )


def resolve_suggestion_conflict(
    *,
    l2_pending: bool,
    clo_pending: bool,
    open_family: str | None,
) -> tuple[bool, bool, str | None]:
    """ADR-0067 §4: never two competing readings at once.

    Returns ``(emit_l2, emit_clo, new_open_family)``.  An already-open family
    keeps its slot while its pattern persists (the "und umgekehrt" of §4 —
    an unanswered clo suggestion is not displaced by a later L2 pattern); on
    a fresh tie the override reading wins (actual interventions are the
    stronger evidence).  A vanished pattern releases the slot.
    """
    if l2_pending and clo_pending:
        winner = open_family if open_family in ("override", "clo") else "override"
    elif l2_pending:
        winner = "override"
    elif clo_pending:
        winner = "clo"
    else:
        return (False, False, None)
    return (winner == "override", winner == "clo", winner)


SEASON_HINT_HYSTERESIS_K = 1.0


def season_mode_hint(
    *,
    climate_mode: str,
    t_rm: float | None,
    heat_max_outdoor: float,
    cool_min_outdoor: float,
    prev_hint: str | None,
) -> str | None:
    """ADR-0060 §2: advisory hint for a persistently season-wrong fixed mode.

    The zone's own lockout thresholds (ADR-0023: never heat above
    ``heat_max_outdoor``, never cool below ``cool_min_outdoor``) define
    "season-wrong", and T_rm's multi-day running-mean memory IS the
    "persistently" condition — no extra dwell timer.  The 1-K hysteresis only
    keeps the advisory from flapping while T_rm hovers at a threshold.
    Purely advisory: the glue raises a NON-fixable repair issue, nothing ever
    switches the mode.
    """
    if t_rm is None:
        return None
    if climate_mode == "heat_only":
        raised = prev_hint == "heat_only_in_cooling"
        threshold = heat_max_outdoor - (SEASON_HINT_HYSTERESIS_K if raised else 0.0)
        return "heat_only_in_cooling" if t_rm >= threshold else None
    if climate_mode == "cool_only":
        raised = prev_hint == "cool_only_in_heating"
        threshold = cool_min_outdoor + (SEASON_HINT_HYSTERESIS_K if raised else 0.0)
        return "cool_only_in_heating" if t_rm <= threshold else None
    return None


def suggestion_suppressed(
    key: str,
    rejected_key: str | None,
    rejected_at: float | None,
    now_ts: float,
) -> bool:
    """True while a rejection of exactly this pattern key is still fresh."""
    return (
        rejected_key == key
        and rejected_at is not None
        and (now_ts - rejected_at) < SUGGEST_REJECT_DAYS * _DAY_S
    )
