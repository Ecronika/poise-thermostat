"""ADR-0060-§3 tuning-round instrument: replay the suggestion detectors.

The §3 round asks for the false-positive rate of the L2/F2 patterns on REAL
household data.  The tick trace (ADR-0011) does not carry user interventions,
so the data source is the zone's **diagnostics dump** — it contains the
persisted L1 override statistic and (since ADR-0067 F1) the feedback
statistic.  This module slides ``now`` across those statistics, runs the
PRODUCTION detectors (`control.suggestion` / `control.feedback`) plus the §4
conflict rule at every step, and records each **rise edge** of a would-be
suggestion.  Every recorded event is then a human question: was this a
suggestion you would have wanted?  Anything else is a false positive.

Run it against a dump (HA → Poise device → *Download diagnostics*):

    python -m tests.harness.suggestion_replay path/to/diagnostics.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

from custom_components.poise.control.feedback import (
    CloSuggestion,
    detect_feedback_pattern,
)
from custom_components.poise.control.suggestion import (
    OverrideSuggestion,
    detect_override_pattern,
    resolve_suggestion_conflict,
)

_DEFAULT_STEP_S = 3600.0  # hourly replay resolution — well below the tick, far
# above the daily granularity the detectors actually resolve.
_TAIL_DAYS_S = 31.0 * 86400.0  # replay until the last event drained (30 d + 1)


@dataclass(frozen=True, slots=True)
class SuggestionEvent:
    """One rise edge of a would-be suggestion during the replay."""

    at_ts: float
    family: str  # "override" | "clo"
    key: str
    evidence: int


def _event_ts(stats: list[dict[str, Any]]) -> list[float]:
    return [float(ev["ts"]) for ev in stats if isinstance(ev.get("ts"), (int, float))]


def replay_suggestion_timeline(
    override_stats: list[dict[str, Any]],
    feedback_stats: list[dict[str, Any]],
    *,
    step_s: float = _DEFAULT_STEP_S,
    since_ts: float | None = None,
) -> list[SuggestionEvent]:
    """Slide ``now`` across the statistics and record suggestion rise edges.

    Uses the production detectors and the §4 conflict resolution with slot
    memory (an open family keeps its slot), exactly like the orchestrator —
    but WITHOUT the rejection cool-down: the tuning round wants the raw
    would-be rate, not the post-decision one.  ``since_ts`` is the §3
    season-gate floor from the dump (mismatch-era override events never
    count); it applies to the override family only — the clo family's button
    signal is structurally a comfort statement and stays ungated.
    """
    all_ts = _event_ts(override_stats) + _event_ts(feedback_stats)
    if not all_ts:
        return []
    now = min(all_ts)
    end = max(all_ts) + _TAIL_DAYS_S
    events: list[SuggestionEvent] = []
    open_family: str | None = None
    prev_l2_key: str | None = None
    prev_clo_key: str | None = None
    while now <= end:
        # Time-slice: the production detectors never see future events — the
        # replay must not either, or every pattern fires at the first step.
        ov_now = [
            e
            for e in override_stats
            if isinstance(e.get("ts"), (int, float)) and float(e["ts"]) <= now
        ]
        fb_now = [
            e
            for e in feedback_stats
            if isinstance(e.get("ts"), (int, float)) and float(e["ts"]) <= now
        ]
        l2: OverrideSuggestion | None = detect_override_pattern(
            ov_now, now_ts=now, since_ts=since_ts
        )
        clo: CloSuggestion | None = detect_feedback_pattern(fb_now, now_ts=now)
        emit_l2, emit_clo, open_family = resolve_suggestion_conflict(
            l2_pending=l2 is not None,
            clo_pending=clo is not None,
            open_family=open_family,
        )
        l2_key = l2.key if (l2 is not None and emit_l2) else None
        clo_key = clo.key if (clo is not None and emit_clo) else None
        if l2 is not None and l2_key is not None and l2_key != prev_l2_key:
            events.append(
                SuggestionEvent(
                    at_ts=now, family="override", key=l2_key, evidence=l2.evidence
                )
            )
        if clo is not None and clo_key is not None and clo_key != prev_clo_key:
            events.append(
                SuggestionEvent(
                    at_ts=now, family="clo", key=clo_key, evidence=clo.evidence
                )
            )
        prev_l2_key = l2_key
        prev_clo_key = clo_key
        now += step_s
    return events


def _integration_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the real HA download envelope, if present.

    The HA download wraps the integration payload in an envelope
    (``home_assistant``/``integration_manifest``/``data``) — the statistics
    then live one level down.
    """
    if "override_stats" not in payload and isinstance(payload.get("data"), dict):
        inner = payload["data"]
        return inner if isinstance(inner, dict) else payload
    return payload


def load_statistics_from_diagnostics(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract the two statistics from a Poise diagnostics dump.

    Accepts both the raw integration payload AND the enveloped HA download.
    Tolerant of pre-F1 dumps (no ``feedback_stats`` section) and of garbage
    (non-list sections decode to empty, mirroring the store codec).
    """
    payload = _integration_payload(payload)
    ov = payload.get("override_stats")
    fb = payload.get("feedback_stats")
    return (
        [e for e in ov if isinstance(e, dict)] if isinstance(ov, list) else [],
        [e for e in fb if isinstance(e, dict)] if isinstance(fb, list) else [],
    )


def season_floor_from_diagnostics(payload: dict[str, Any]) -> float | None:
    """The §3 season-gate floor stamp, if the dump carries one.

    Dumps from before the gate landed have no stamp — those replay UNGATED,
    and for fixed-mode zones the CLI flags that the gate is not modeled
    (hint history unknown); the live-tick ``season_hint`` alone cannot cover
    the replay window in either direction.
    """
    ts = _integration_payload(payload).get("season_hint_last_active_ts")
    return float(ts) if isinstance(ts, (int, float)) else None


def main(argv: list[str]) -> int:
    """CLI: replay one or more diagnostics dumps and print the timeline."""
    if not argv:
        print(__doc__)
        return 2
    total = 0
    for path in argv:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        ov, fb = load_statistics_from_diagnostics(payload)
        floor = season_floor_from_diagnostics(payload)
        inner = _integration_payload(payload)
        config = inner.get("config")
        mode = config.get("climate_mode") if isinstance(config, dict) else None
        events = replay_suggestion_timeline(ov, fb, since_ts=floor)
        total += len(events)
        print(f"{path}: {len(ov)} override events, {len(fb)} feedback events")
        if floor is not None:
            raw = replay_suggestion_timeline(ov, fb)
            print(
                f"  season-gate floor @ ts={floor:.0f} applied"
                f" ({len(raw)} raw edge(s) without it)"
            )
        elif mode in ("heat_only", "cool_only"):
            print(
                f"  NOTE: fixed-mode zone ({mode}), dump carries no gate stamp"
                " — season gate NOT modeled (hint history unknown); review"
                " edges with season context in mind"
            )
        for e in events:
            print(
                f"  rise @ ts={e.at_ts:.0f}  family={e.family}"
                f"  key={e.key}  evidence={e.evidence}"
            )
        if not events:
            print("  (no would-be suggestion — nothing to review)")
    print(f"TOTAL rise edges: {total} — review each one: unwanted = false positive")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    raise SystemExit(main(sys.argv[1:]))
