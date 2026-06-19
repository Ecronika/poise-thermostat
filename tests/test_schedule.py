from __future__ import annotations

from custom_components.poise.comfort.schedule import (
    ComfortSchedule,
    ComfortWindow,
)

# 06:00 = 360, 08:00 = 480, 22:00 = 1320
_MORNING = ComfortWindow(360, 480)


def _sched() -> ComfortSchedule:
    return ComfortSchedule.from_windows([_MORNING], setback_delta=3.0)


def test_inside_window_is_comfort() -> None:
    s = _sched().state_at(400)
    assert s.is_comfort
    assert s.minutes_to_comfort == 0
    assert s.setback_offset == 0.0


def test_before_window_counts_down_and_sets_back() -> None:
    s = _sched().state_at(300)  # 05:00, one hour before 06:00
    assert not s.is_comfort
    assert s.minutes_to_comfort == 60
    assert s.setback_offset == -3.0


def test_after_window_wraps_to_next_day() -> None:
    s = _sched().state_at(600)  # 10:00, next comfort is tomorrow 06:00
    assert s.minutes_to_comfort == (360 - 600) % 1440 == 1200


def test_minute_beyond_one_day_wraps() -> None:
    assert _sched().state_at(400 + 1440).is_comfort


def test_empty_schedule_is_always_comfort() -> None:
    s = ComfortSchedule.always_comfort().state_at(0)
    assert s.is_comfort
    assert s.setback_offset == 0.0


def test_overlapping_windows_merge() -> None:
    s = ComfortSchedule.from_windows([ComfortWindow(360, 480), ComfortWindow(450, 600)])
    assert s.windows == (ComfortWindow(360, 600),)


def test_invalid_windows_dropped_and_clamped() -> None:
    s = ComfortSchedule.from_windows(
        [ComfortWindow(500, 500), ComfortWindow(-10, 99999)]
    )
    assert s.windows == (ComfortWindow(0, 1440),)


def test_parse_hhmm_variants() -> None:
    from custom_components.poise.comfort.schedule import parse_hhmm

    assert parse_hhmm("06:30") == 390
    assert parse_hhmm("06:30:00") == 390
    assert parse_hhmm("") is None
    assert parse_hhmm(None) is None
    assert parse_hhmm("24:00") is None
    assert parse_hhmm("garbage") is None
