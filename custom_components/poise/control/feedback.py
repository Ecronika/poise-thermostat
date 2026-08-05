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
