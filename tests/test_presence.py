"""Tests for the pure hierarchical presence resolver (ADR-0058)."""

from __future__ import annotations

from custom_components.poise.comfort.presence import (
    PresenceConfig,
    PresenceLevel,
    any_present,
    resolve_presence,
    step_room_absence,
)

CFG = PresenceConfig()  # 30 min hold, 2 K eco


def _resolve(
    *,
    home: bool | None = True,
    room_absent_min: float = 0.0,
    is_comfort: bool = True,
    preheating: bool = False,
) -> PresenceLevel:
    return resolve_presence(
        home=home,
        room_absent_min=room_absent_min,
        is_comfort=is_comfort,
        preheating=preheating,
        cfg=CFG,
    )


# -- house gate (outermost) ------------------------------------------------


def test_home_false_is_away_even_with_preheat() -> None:
    # the home gate is outermost: preheat must NOT preheat an empty house
    assert _resolve(home=False) is PresenceLevel.AWAY
    assert _resolve(home=False, preheating=True) is PresenceLevel.AWAY
    assert _resolve(home=False, room_absent_min=99) is PresenceLevel.AWAY


def test_home_unavailable_or_unset_is_present() -> None:
    # None (not configured / unavailable) keeps the gate open -> fail-safe present
    assert _resolve(home=None) is PresenceLevel.COMFORT


# -- preheat overrides the room level (within the gate) --------------------


def test_preheat_overrides_room_eco() -> None:
    # room empty long, but preheating -> comfort (schedule is the promise)
    assert _resolve(preheating=True, room_absent_min=99) is PresenceLevel.COMFORT
    # even outside the comfort window, preheat within the gate is comfort
    assert _resolve(preheating=True, is_comfort=False) is PresenceLevel.COMFORT


# -- room Eco modulation ---------------------------------------------------


def test_room_eco_only_past_the_hold() -> None:
    assert _resolve(room_absent_min=35.0) is PresenceLevel.ROOM_ECO
    assert _resolve(room_absent_min=20.0) is PresenceLevel.COMFORT  # below hold
    assert _resolve(room_absent_min=0.0) is PresenceLevel.COMFORT  # present / restart


def test_room_eco_only_inside_comfort_window() -> None:
    # at night the schedule owns the setback; presence stays neutral
    assert _resolve(is_comfort=False, room_absent_min=99.0) is PresenceLevel.COMFORT


# -- asymmetric absence anchor (debounce) ----------------------------------


def test_absence_anchor_asymmetric_and_failsafe() -> None:
    # present (True) or unknown/no-sensor (None) -> clock cleared
    assert step_room_absence(500.0, present=True, now=900.0) is None
    assert step_room_absence(500.0, present=None, now=900.0) is None
    # absent -> starts the clock, then HOLDS it (does not restart each tick)
    assert step_room_absence(None, present=False, now=100.0) == 100.0
    assert step_room_absence(100.0, present=False, now=700.0) == 100.0
    # re-entry clears it immediately (asymmetric)
    assert step_room_absence(100.0, present=True, now=800.0) is None


def test_flicker_does_not_trip_eco_before_hold() -> None:
    # PIR flickers absent then present within the hold window -> never reaches Eco
    since = None
    since = step_room_absence(since, present=False, now=0.0)  # goes absent @0
    absent_min = (600.0 - (since or 0.0)) / 60.0  # 10 min later
    assert _resolve(room_absent_min=absent_min) is PresenceLevel.COMFORT  # 10 < 30
    since = step_room_absence(since, present=True, now=600.0)  # motion -> reset
    assert since is None


def test_restart_starts_present() -> None:
    # fresh restart: no anchor -> 0 absent minutes -> comfort (latch re-engages)
    assert step_room_absence(None, present=True, now=0.0) is None
    assert _resolve(room_absent_min=0.0) is PresenceLevel.COMFORT


# -- OR-reduction across multiple entities (multiple=True, ADR-0007) -------


def test_any_present_or_reduces_tristates() -> None:
    # no entities configured -> None (fail-safe present == today's behaviour)
    assert any_present([]) is None
    # any one present wins over an absent sibling
    assert any_present([True, False]) is True
    assert any_present([False, False, True]) is True
    # all resolvable and all absent -> False (empty house / empty room)
    assert any_present([False, False]) is False
    # an unresolved sibling with none present -> None (a dead tracker never
    # closes the gate)
    assert any_present([False, None]) is None
    assert any_present([None]) is None
    # a present one still wins over an unresolved sibling
    assert any_present([None, True]) is True
