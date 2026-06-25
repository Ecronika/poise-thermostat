"""Tests for outcome scoring — the ts-vs-obs self-validation (ADR-0044)."""

from __future__ import annotations

from custom_components.poise.control.outcome_scoring import (
    OutcomeStats,
    outcome_score,
    session_end_reason,
)


def test_perfect_session_scores_high() -> None:
    # reached, on time, no overshoot, no environmental help -> ~1.0.
    s = outcome_score(
        reason="reached",
        start_temp=18.0,
        end_temp=21.0,
        peak_temp=21.0,
        target=21.0,
        minutes_taken=30.0,
        expected_minutes=30.0,
    )
    assert s >= 0.99


def test_timeout_not_reached_scores_lower() -> None:
    s = outcome_score(
        reason="timeout",
        start_temp=18.0,
        end_temp=19.5,
        peak_temp=19.5,
        target=21.0,
        minutes_taken=90.0,
        expected_minutes=30.0,
    )
    assert s < 0.6  # only half the gap closed, and slow


def test_overshoot_cuts_accuracy() -> None:
    clean = outcome_score(
        reason="reached",
        start_temp=18.0,
        end_temp=21.0,
        peak_temp=21.0,
        target=21.0,
        minutes_taken=30.0,
        expected_minutes=30.0,
    )
    over = outcome_score(
        reason="reached",
        start_temp=18.0,
        end_temp=21.0,
        peak_temp=23.0,
        target=21.0,
        minutes_taken=30.0,
        expected_minutes=30.0,
    )
    assert over < clean  # 2 K overshoot -> accuracy drops


def test_environmental_discount_devalues_free_heat() -> None:
    no_help = outcome_score(
        reason="reached",
        start_temp=18.0,
        end_temp=21.0,
        peak_temp=21.0,
        target=21.0,
        minutes_taken=30.0,
        expected_minutes=30.0,
        q_solar=0.0,
        outdoor=5.0,
    )
    sunny_mild = outcome_score(
        reason="reached",
        start_temp=18.0,
        end_temp=21.0,
        peak_temp=21.0,
        target=21.0,
        minutes_taken=30.0,
        expected_minutes=30.0,
        q_solar=1.0,
        outdoor=22.0,
    )
    assert sunny_mild < no_help  # the sun/warmth did some of the work


def test_slow_session_lowers_speed() -> None:
    fast = outcome_score(
        reason="reached",
        start_temp=18.0,
        end_temp=21.0,
        peak_temp=21.0,
        target=21.0,
        minutes_taken=20.0,
        expected_minutes=30.0,
    )
    slow = outcome_score(
        reason="reached",
        start_temp=18.0,
        end_temp=21.0,
        peak_temp=21.0,
        target=21.0,
        minutes_taken=75.0,
        expected_minutes=30.0,
    )
    assert slow < fast


def test_session_end_reason_transitions() -> None:
    assert session_end_reason(20.8, 21.0, 40.0, True) == "reached"  # within reach_delta
    assert session_end_reason(19.0, 21.0, 95.0, True) == "timeout"
    assert session_end_reason(19.0, 21.0, 40.0, False) == "interrupt"
    assert session_end_reason(19.0, 21.0, 40.0, True) is None  # still heating


def test_stats_ab_split_and_roundtrip() -> None:
    st = OutcomeStats()
    st = st.observe(0.9, "ts").observe(0.7, "ts").observe(0.4, "obs")
    assert st.ts_avg == 0.8 and st.obs_avg == 0.4 and st.last_score == 0.4
    again = OutcomeStats.from_dict(st.to_dict())
    assert again == st
