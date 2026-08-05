"""Comfort-feedback statistic (ADR-0067 F1) — observe only, nothing acts.

The explicit "too warm / too cold" channel: every accepted feedback lands in a
capped rolling log on ``UserControlState`` (the L1 pattern of ADR-0059 §5);
masked feedback is DISCARDED, never counted — a press during an open window,
an active hold, a setback/absent phase, frozen sensors, an invalid PMV
(bedroom profile, V3), an anticipation extreme day or far outside neutral
says something about the *situation*, not about the household's clothing
assumption.  Suggestions (F2) are a later, gated stage; this module has no
behaviour and feeds nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .suggestion import suggestion_suppressed

FEEDBACK_CAP = 50
# ADR-0067 F2: the deliberately conservative suggestion gate.
CLO_SUGGEST_MIN_EVENTS = 5
CLO_SUGGEST_WINDOW_DAYS = 30.0
CLO_SUGGEST_STEP = 0.1  # per-suggestion step; total config offset |x| <= 0.3

_DAY_S = 86400.0
# The anticipation-extreme-day mask (research 2026-08 §9): while the forecast
# blend is fighting a warned heat/cold episode, feedback reflects the episode.
EXTREME_DAY_DELTA_K = 8.0
# Outside roughly neutral PMV the *regulation* (band, actuator) is the story,
# not the clothing assumption.
PMV_FEEDBACK_RANGE = 1.0


def feedback_mask_reason(
    *,
    window_open: bool,
    override_active: bool,
    is_comfort: bool,
    occupied: bool,
    frozen: bool,
    pmv_valid: bool,
    pmv: float | None,
    t_rm: float | None,
    t_forecast_day: float | None,
) -> str | None:
    """First matching ADR-0067 §F1 mask, or ``None`` when the feedback counts."""
    if window_open:
        return "window_open"
    if override_active:
        return "override_active"
    if not is_comfort or not occupied:
        return "setback_or_absent"
    if frozen:
        return "sensor_frozen"
    if not pmv_valid:
        return "pmv_not_valid"
    if (
        t_rm is not None
        and t_forecast_day is not None
        and abs(t_rm - t_forecast_day) > EXTREME_DAY_DELTA_K
    ):
        return "extreme_day"
    if pmv is None:
        return "no_pmv"
    if abs(pmv) > PMV_FEEDBACK_RANGE:
        return "pmv_out_of_range"
    return None


def record_feedback(
    stats: list[dict[str, Any]],
    *,
    direction: str,
    now_ts: float,
    pmv: float | None,
    ppd: float | None,
    clo_used: float | None,
    met_used: float | None,
    clo_source: str | None,
    phase: str,
    presence_level: str,
) -> None:
    """Append one ACCEPTED feedback (the caller already passed the mask).

    In-place with a tail cap, exactly like the L1 override statistic
    (``override_runtime`` — keep the last :data:`FEEDBACK_CAP`).
    """
    stats.append(
        {
            "ts": now_ts,
            "direction": direction,
            "pmv": pmv,
            "ppd": ppd,
            "clo_used": clo_used,
            "met_used": met_used,
            "clo_source": clo_source,
            "phase": phase,
            "presence_level": presence_level,
        }
    )
    del stats[:-FEEDBACK_CAP]


@dataclass(frozen=True, slots=True)
class CloSuggestion:
    """One detected feedback pattern (ADR-0067 F2).

    ``direction`` is the sign of the proposed clo change: "too warm" feedback
    means the model UNDERestimates the insulation (+1, raise -> cooler
    target); "too cold" means it OVERestimates (-1, lower -> warmer target).
    """

    direction: int  # +1 raise clo | -1 lower clo
    evidence: int

    @property
    def key(self) -> str:
        """Stable pattern identity for the 30-day cool-down."""
        return f"clo_offset:{self.direction:+d}"


def detect_feedback_pattern(
    stats: list[dict[str, Any]],
    *,
    now_ts: float,
) -> CloSuggestion | None:
    """The F2 pattern predicate: >= 5 same-direction clean feedbacks in 30 d.

    Every event in the statistic is mask-clean by construction (F1 discards
    masked presses); malformed events are skipped, never raising.
    """
    cutoff = now_ts - CLO_SUGGEST_WINDOW_DAYS * _DAY_S
    buckets: dict[int, list[float]] = {}
    for ev in stats:
        ts = ev.get("ts")
        direction = {"warm": 1, "cold": -1}.get(str(ev.get("direction")))
        if direction is None or not isinstance(ts, (int, float)):
            continue
        if float(ts) < cutoff:
            continue
        buckets.setdefault(direction, []).append(float(ts))
    candidates = [
        (len(tss), max(tss), direction)
        for direction, tss in buckets.items()
        if len(tss) >= CLO_SUGGEST_MIN_EVENTS
    ]
    if not candidates:
        return None
    count, _latest, direction = max(candidates)
    return CloSuggestion(direction=direction, evidence=count)


def clo_suggestion_reason(
    suggestion: CloSuggestion | None,
    *,
    l2_pending: bool,
    override_direction: int | None,
    rejected_key: str | None,
    rejected_at: float | None,
    now_ts: float,
) -> str:
    """Why the clo suggestion is NOT emitted ("" = emittable), ADR-0067 §4.

    Precedence: no pattern -> the L2 collision rule (never two competing
    readings) -> the override-statistic consistency check ("too cold"
    feedback while overrides nudge DOWN contradicts itself; the consistent
    override direction is the OPPOSITE of the clo direction) -> the 30-day
    rejection cool-down.
    """
    if suggestion is None:
        return "no_pattern"
    if l2_pending:
        return "l2_pending"
    if override_direction is not None and override_direction == suggestion.direction:
        return "inconsistent_signals"
    if suggestion_suppressed(suggestion.key, rejected_key, rejected_at, now_ts):
        return "rejected"
    return ""
