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


def test_minutes_to_setback_reports_window_end() -> None:
    from custom_components.poise.comfort.schedule import ComfortSchedule, ComfortWindow

    sched = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])  # 06:00-22:00
    st = sched.state_at(600)  # 10:00, inside window
    assert st.is_comfort and st.minutes_to_setback == 720  # 22:00 - 10:00
    out = sched.state_at(60)  # 01:00, setback
    assert not out.is_comfort and out.minutes_to_setback == 0


def test_parse_hhmm_rejects_non_numeric() -> None:
    from custom_components.poise.comfort.schedule import parse_hhmm

    assert parse_hhmm("ab:cd") is None
    assert parse_hhmm("noon") is None
    assert parse_hhmm("25:00") is None


def test_overnight_window_is_comfort_across_midnight() -> None:
    from custom_components.poise.comfort.schedule import ComfortSchedule, ComfortWindow

    sched = ComfortSchedule.from_windows([ComfortWindow(1320, 360)])  # 22:00-06:00
    assert sched.state_at(1380).is_comfort  # 23:00 comfort
    assert sched.state_at(120).is_comfort  # 02:00 comfort
    assert not sched.state_at(720).is_comfort  # 12:00 setback
    # minutes_to_setback spans midnight: 23:00 -> 06:00 = 420 min
    assert sched.state_at(1380).minutes_to_setback == 420
    # early morning part: 02:00 -> 06:00 = 240 min
    assert sched.state_at(120).minutes_to_setback == 240
    # during setback at 12:00, next comfort start (22:00) is 600 min away
    assert sched.state_at(720).minutes_to_comfort == 600


def test_same_day_window_still_works() -> None:
    from custom_components.poise.comfort.schedule import ComfortSchedule, ComfortWindow

    sched = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])  # 06:00-22:00
    assert sched.state_at(600).is_comfort and sched.state_at(60).is_comfort is False
    assert sched.state_at(600).minutes_to_setback == 720
