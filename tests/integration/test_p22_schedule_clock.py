"""P2.2 glue test: the coordinator's atomic out-of-tick schedule clock.

``coordinator._local_schedule_time_now()`` replaces the former
``_local_minute_now()`` -- it must read ``dt_util.now()`` exactly ONCE and
derive ``(weekday, minute)`` from that SAME instant, so a midnight rollover
between two separate reads can never pair one day's weekday with the other
day's minute-of-day. This needs a real ``homeassistant.util.dt`` import
(``coordinator.py`` is HA-glue), so it lives here rather than in the pure
suite (plan P2.2, disposition Rev. 2.2 §0.4 p.5 "out-of-tick clock atomar").

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from custom_components.poise import coordinator as coordinator_mod


def _at(dt: datetime) -> tuple[int, int]:
    with patch(
        "custom_components.poise.coordinator.dt_util.now", return_value=dt
    ) as mocked_now:
        result = coordinator_mod._local_schedule_time_now()
        assert mocked_now.call_count == 1  # ONE clock read per call
    return result


def test_sunday_late_night_pairs_sunday_weekday_and_minute() -> None:
    # Sunday 23:59 -> weekday 6 (Sunday), minute 1439 -- never Monday's 0.
    assert _at(datetime(2026, 8, 23, 23, 59)) == (6, 1439)


def test_monday_midnight_pairs_monday_weekday_and_minute() -> None:
    # Monday 00:00 -> weekday 0 (Monday), minute 0 -- never Sunday's 1439.
    assert _at(datetime(2026, 8, 24, 0, 0)) == (0, 0)


def test_local_schedule_time_now_reads_the_clock_exactly_once() -> None:
    """The atomicity guarantee: one ``dt_util.now()`` call produces the whole
    pair -- there is no second read that could observe a different instant."""
    with patch(
        "custom_components.poise.coordinator.dt_util.now",
        return_value=datetime(2026, 8, 20, 14, 5),
    ) as mocked_now:
        weekday, minute = coordinator_mod._local_schedule_time_now()
        assert mocked_now.call_count == 1
    assert weekday == 3  # Thursday
    assert minute == 14 * 60 + 5
