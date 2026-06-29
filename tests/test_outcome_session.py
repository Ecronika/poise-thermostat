"""ADR-0044 session lifecycle (pure): start / peak / end + ts-vs-obs tagging."""

from __future__ import annotations

from custom_components.poise.control.outcome_scoring import (
    OutcomeSession,
    observe_session,
)


def test_session_starts_when_below_target_and_heating() -> None:
    s, fin = observe_session(
        OutcomeSession(),
        temp=18.0,
        target=21.0,
        heating=True,
        controlling=True,
        dt_min=1.0,
        expected_minutes=30.0,
    )
    assert s.active is True and s.start_temp == 18.0 and s.controller == "ts"
    assert fin is None


def test_no_start_when_not_heating() -> None:
    s, fin = observe_session(
        OutcomeSession(),
        temp=18.0,
        target=21.0,
        heating=False,
        controlling=True,
        dt_min=1.0,
        expected_minutes=30.0,
    )
    assert s.active is False and fin is None


def test_reached_scores_and_resets() -> None:
    s = OutcomeSession(
        active=True,
        start_temp=18.0,
        peak_temp=20.0,
        target=21.0,
        elapsed_min=10.0,
        expected_minutes=30.0,
        controller="ts",
    )
    s2, fin = observe_session(
        s,
        temp=21.0,
        target=21.0,
        heating=True,
        controlling=True,
        dt_min=2.0,
        expected_minutes=30.0,
    )
    assert s2.active is False
    assert fin is not None and 0.0 <= fin.score <= 1.0 and fin.controller == "ts"


def test_too_short_session_discarded() -> None:
    s = OutcomeSession(
        active=True,
        start_temp=18.0,
        peak_temp=18.0,
        target=21.0,
        elapsed_min=1.0,
        expected_minutes=30.0,
        controller="ts",
    )
    # reaches target after ~1.5 min total -> below min_session_min (3) -> discard
    s2, fin = observe_session(
        s,
        temp=21.0,
        target=21.0,
        heating=True,
        controlling=True,
        dt_min=0.5,
        expected_minutes=30.0,
    )
    assert s2.active is False and fin is None


def test_interrupt_ends_session_when_heating_stops() -> None:
    s = OutcomeSession(
        active=True,
        start_temp=18.0,
        peak_temp=19.5,
        target=21.0,
        elapsed_min=10.0,
        expected_minutes=30.0,
        controller="ts",
    )
    s2, fin = observe_session(
        s,
        temp=19.0,
        target=21.0,
        heating=False,
        controlling=True,
        dt_min=2.0,
        expected_minutes=30.0,
    )
    assert s2.active is False and fin is not None


def test_observed_session_tagged_obs() -> None:
    s, _ = observe_session(
        OutcomeSession(),
        temp=18.0,
        target=21.0,
        heating=True,
        controlling=False,
        dt_min=1.0,
        expected_minutes=30.0,
    )
    assert s.controller == "obs"
