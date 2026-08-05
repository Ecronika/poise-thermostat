"""Tests for the comfort-feedback statistic (ADR-0067 F1 — observe only)."""

from __future__ import annotations

from custom_components.poise.control.feedback import (
    FEEDBACK_CAP,
    feedback_mask_reason,
    record_feedback,
)

_OK = {
    "window_open": False,
    "override_active": False,
    "is_comfort": True,
    "occupied": True,
    "frozen": False,
    "pmv_valid": True,
    "pmv": 0.3,
    "t_rm": 20.0,
    "t_forecast_day": 24.0,
}


def _reason(**overrides: object) -> str | None:
    return feedback_mask_reason(**{**_OK, **overrides})  # type: ignore[arg-type]


def test_clean_feedback_is_not_masked() -> None:
    assert _reason() is None


def test_every_adr_mask_has_its_reason() -> None:
    # ADR-0067 §F1 mask list, one case each.
    assert _reason(window_open=True) == "window_open"
    assert _reason(override_active=True) == "override_active"
    assert _reason(is_comfort=False) == "setback_or_absent"
    assert _reason(occupied=False) == "setback_or_absent"
    assert _reason(frozen=True) == "sensor_frozen"
    assert _reason(pmv_valid=False) == "pmv_not_valid"  # bedroom profile (V3)
    assert _reason(t_forecast_day=32.0) == "extreme_day"  # |20-32| > 8 K
    assert _reason(pmv=None) == "no_pmv"
    assert _reason(pmv=1.4) == "pmv_out_of_range"
    assert _reason(pmv=-1.4) == "pmv_out_of_range"


def test_mask_precedence_is_first_match_in_adr_order() -> None:
    # window beats everything; the pmv checks come last.
    assert _reason(window_open=True, pmv=None, pmv_valid=False) == "window_open"
    assert _reason(pmv_valid=False, pmv=None) == "pmv_not_valid"


def test_extreme_day_boundary_and_degradation() -> None:
    # Exactly 8 K is still allowed; beyond masks — in BOTH directions.
    assert _reason(t_forecast_day=28.0) is None  # |20-28| = 8
    assert _reason(t_forecast_day=28.1) == "extreme_day"
    assert _reason(t_forecast_day=11.9) == "extreme_day"  # cold snap
    # Without forecast (or without t_rm) the mask degrades to inactive.
    assert _reason(t_forecast_day=None) is None
    assert _reason(t_rm=None) is None


def test_pmv_edge_is_inclusive() -> None:
    assert _reason(pmv=1.0) is None
    assert _reason(pmv=-1.0) is None


def test_record_feedback_shape_and_cap() -> None:
    stats: list[dict[str, object]] = []
    for i in range(FEEDBACK_CAP + 10):
        record_feedback(
            stats,
            direction="cold",
            now_ts=1000.0 + i,
            pmv=0.1,
            ppd=5.5,
            clo_used=0.52,
            met_used=1.2,
            clo_source="rm",
            phase="comfort",
            presence_level="present",
        )
    assert len(stats) == FEEDBACK_CAP  # capped, newest kept
    assert stats[-1]["ts"] == 1000.0 + FEEDBACK_CAP + 9
    assert stats[0]["ts"] == 1000.0 + 10  # oldest dropped
    assert stats[-1] == {
        "ts": 1000.0 + FEEDBACK_CAP + 9,
        "direction": "cold",
        "pmv": 0.1,
        "ppd": 5.5,
        "clo_used": 0.52,
        "met_used": 1.2,
        "clo_source": "rm",
        "phase": "comfort",
        "presence_level": "present",
    }
