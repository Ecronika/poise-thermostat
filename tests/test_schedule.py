from __future__ import annotations

import pytest

from custom_components.poise.comfort.schedule import (
    ComfortSchedule,
    ComfortWindow,
    parse_hhmm,
)

H = 60
# 06:00 = 360, 08:00 = 480, 22:00 = 1320
_MORNING = ComfortWindow(360, 480)

# Weekday masks (bit 0 = Monday, ISO weekday - 1)
_MO = 0b0000001
_MO_FR = 0b0011111
_FR = 0b0010000
_SA = 0b0100000
_SO = 0b1000000


def _sched() -> ComfortSchedule:
    return ComfortSchedule.from_windows([_MORNING], setback_delta=3.0)


# ---------------------------------------------------------------------------
# daily model (pre-P2 cases, converted to the mandatory weekday argument;
# expected values unchanged except the sanctioned always-comfort None change)
# ---------------------------------------------------------------------------


def test_inside_window_is_comfort() -> None:
    s = _sched().state_at(400, 0)
    assert s.is_comfort
    assert s.minutes_to_comfort == 0
    assert s.setback_offset == 0.0


def test_before_window_counts_down_and_sets_back() -> None:
    s = _sched().state_at(300, 0)  # 05:00, one hour before 06:00
    assert not s.is_comfort
    assert s.minutes_to_comfort == 60
    assert s.setback_offset == -3.0


def test_after_window_wraps_to_next_day() -> None:
    s = _sched().state_at(600, 0)  # 10:00, next comfort is tomorrow 06:00
    assert s.minutes_to_comfort == (360 - 600) % 1440 == 1200


def test_minute_beyond_one_day_wraps() -> None:
    assert _sched().state_at(400 + 1440, 0).is_comfort


def test_empty_schedule_is_always_comfort() -> None:
    s = ComfortSchedule.always_comfort().state_at(0, 0)
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
    assert parse_hhmm("06:30") == 390
    assert parse_hhmm("06:30:00") == 390
    assert parse_hhmm("") is None
    assert parse_hhmm(None) is None
    assert parse_hhmm("24:00") is None
    assert parse_hhmm("garbage") is None


def test_minutes_to_setback_reports_window_end() -> None:
    sched = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])  # 06:00-22:00
    st = sched.state_at(600, 0)  # 10:00, inside window
    assert st.is_comfort and st.minutes_to_setback == 720  # 22:00 - 10:00
    out = sched.state_at(60, 0)  # 01:00, setback
    assert not out.is_comfort and out.minutes_to_setback == 0


def test_parse_hhmm_rejects_non_numeric() -> None:
    assert parse_hhmm("ab:cd") is None
    assert parse_hhmm("noon") is None
    assert parse_hhmm("25:00") is None


def test_overnight_window_is_comfort_across_midnight() -> None:
    sched = ComfortSchedule.from_windows([ComfortWindow(1320, 360)])  # 22:00-06:00
    assert sched.state_at(1380, 0).is_comfort  # 23:00 comfort
    assert sched.state_at(120, 0).is_comfort  # 02:00 comfort
    assert not sched.state_at(720, 0).is_comfort  # 12:00 setback
    # minutes_to_setback spans midnight: 23:00 -> 06:00 = 420 min
    assert sched.state_at(1380, 0).minutes_to_setback == 420
    # early morning part: 02:00 -> 06:00 = 240 min
    assert sched.state_at(120, 0).minutes_to_setback == 240
    # during setback at 12:00, next comfort start (22:00) is 600 min away
    assert sched.state_at(720, 0).minutes_to_comfort == 600


def test_same_day_window_still_works() -> None:
    sched = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])  # 06:00-22:00
    assert sched.state_at(600, 0).is_comfort and not sched.state_at(60, 0).is_comfort
    assert sched.state_at(600, 0).minutes_to_setback == 720


# ---------------------------------------------------------------------------
# P2.1: cyclic week timeline (day masks, set union, seam wrap)
# ---------------------------------------------------------------------------


def test_union_across_different_masks() -> None:
    # A Mo-Fr 06-10 + B Mo 08-12: Monday's union runs 06-12, Tuesday's 06-10.
    s = ComfortSchedule.from_windows(
        [
            ComfortWindow(6 * H, 10 * H, days=_MO_FR),
            ComfortWindow(8 * H, 12 * H, days=_MO),
        ],
        3.0,
    )
    assert s.state_at(9 * H, 0).minutes_to_setback == 180  # Monday 09:00 -> 12:00
    assert s.state_at(9 * H, 1).minutes_to_setback == 60  # Tuesday 09:00 -> 10:00


def test_weekday_mask_and_cross_day_distance() -> None:
    # Mo-Fr 06-22: Saturday 08:00 is setback; next comfort is Monday 06:00.
    s = ComfortSchedule.from_windows([ComfortWindow(6 * H, 22 * H, days=_MO_FR)], 3.0)
    st = s.state_at(8 * H, 5)
    assert not st.is_comfort
    assert st.minutes_to_comfort == 46 * H


def test_sunday_overnight_covers_both_sides_of_the_seam() -> None:
    # SO 22-06 wraps the week seam into Monday morning.
    s = ComfortSchedule.from_windows([ComfortWindow(22 * H, 6 * H, days=_SO)], 3.0)
    assert s.state_at(23 * H, 6).is_comfort  # Sunday 23:00
    monday = s.state_at(5 * H, 0)  # Monday 05:00
    assert monday.is_comfort and monday.minutes_to_setback == 60
    assert not s.state_at(23 * H, 0).is_comfort  # Monday 23:00


def test_sunday_overnight_seam_distance_is_wrap_correct() -> None:
    # Review blocker: Sunday 23:00 inside SO 22-06 is 7 h from the Monday
    # 06:00 end -- the wrap interval must not truncate at the seam (420, not 60).
    s = ComfortSchedule.from_windows([ComfortWindow(22 * H, 6 * H, days=_SO)], 3.0)
    assert s.state_at(23 * H, 6).minutes_to_setback == 7 * H


def test_multiple_overnight_windows_union() -> None:
    # FR|SA 22-02 + SA 23-01: Saturday night's union ends Sunday 02:00.
    s = ComfortSchedule.from_windows(
        [
            ComfortWindow(22 * H, 2 * H, days=_FR | _SA),
            ComfortWindow(23 * H, 1 * H, days=_SA),
        ],
        3.0,
    )
    assert s.state_at(0, 6).minutes_to_setback == 120  # Sunday 00:00 -> 02:00
    # Sunday 03:00: next comfort is Friday 22:00 (5 days 19 hours away).
    assert s.state_at(3 * H, 6).minutes_to_comfort == 5 * 1440 + 19 * H


def test_all_days_default_is_weekday_equivalent() -> None:
    # Pins the interim-weekday safety (P2.2): with the default ALL_DAYS mask,
    # every weekday yields the identical state -- passing weekday=0 at the
    # production call sites is provably behavior-equivalent until P2.3.
    s = ComfortSchedule.from_windows([ComfortWindow(360, 1320)], 3.0)
    for minute in (0, 300, 360, 600, 1319, 1320, 1439):
        expected = s.state_at(minute, 0)
        for weekday in range(1, 7):
            assert s.state_at(minute, weekday) == expected


def test_full_week_window_equals_always_comfort() -> None:
    s = ComfortSchedule.from_windows([ComfortWindow(0, 1440)], 3.0)
    st = s.state_at(12 * H, 3)
    assert st.is_comfort
    assert st.minutes_to_comfort is None
    assert st.minutes_to_setback is None
    assert st.setback_offset == 0.0


def test_always_setback_has_no_fictional_switchpoint() -> None:
    s = ComfortSchedule.from_windows([ComfortWindow(6 * H, 22 * H, days=0)], 3.0)
    st = s.state_at(12 * H, 2)
    assert not st.is_comfort
    assert st.setback_offset == -3.0
    assert st.minutes_to_comfort is None  # KEIN 7-Tage-Sentinel
    assert st.minutes_to_setback is None


def test_always_comfort_has_no_transitions() -> None:
    # Sanctioned BEHAVIOR change (plan §0.5 p.5, §6): always-comfort used to
    # report 0/0; a transition that does not exist is now None -- 0 fed the
    # forecast horizon and the switchpoint logic as if it were a real edge.
    s = ComfortSchedule.from_windows([], 3.0)
    st = s.state_at(12 * H, 2)
    assert st.is_comfort
    assert st.minutes_to_comfort is None and st.minutes_to_setback is None


def test_empty_window_is_dropped_and_not_always_setback() -> None:
    # start == end is EMPTY (never a 24-h window) and does not count as
    # "configured" -- as the only window it degrades to "no schedule".
    s = ComfortSchedule.from_windows([ComfortWindow(500, 500)], 3.0)
    assert s.windows == ()
    st = s.state_at(12 * H, 4)
    assert st.is_comfort
    assert st.minutes_to_comfort is None and st.minutes_to_setback is None


# ---------------------------------------------------------------------------
# P2.2 carry-over polish: zero-width phantom interval filter
# ---------------------------------------------------------------------------


def test_clamped_start_at_midnight_boundary_leaves_no_phantom_interval() -> None:
    # Review carry-over (plan §4 P2.2 step 7): a window clamped to
    # start_min == DAY_MINUTES (1440) with an overnight end_min == 0 expands,
    # per active day, to a ZERO-WIDTH raw interval (s == e) -- constructed
    # directly (bypassing _normalize's clamp) to force the exact boundary.
    # Unfiltered, that phantom interval would still contribute a "start" to
    # the to-next-comfort distance; filtered, the week union is empty and the
    # schedule behaves as configured-but-inactive (always-setback), with NO
    # phantom minutes_to_comfort countdown.
    s = ComfortSchedule(windows=(ComfortWindow(1440, 0),))
    st = s.state_at(12 * H, 3)
    assert not st.is_comfort
    assert st.minutes_to_comfort is None  # no phantom countdown
    assert st.minutes_to_setback is None


def test_minute_wrap_kept_and_weekday_validated() -> None:
    s = _sched()
    assert s.state_at(8 * H + 1440, 0) == s.state_at(8 * H, 0)
    with pytest.raises(ValueError):
        s.state_at(8 * H, 7)
    with pytest.raises(ValueError):
        s.state_at(8 * H, -1)
