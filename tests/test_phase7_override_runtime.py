"""Phase-7 S1 pure tests for ``control.override_runtime`` (plan phase 7).

The command half of the hold/Boost lifecycle moved out of ``coordinator.py``
into hass-free functions over ``UserControlState`` returning ``CommandResult``
(finding 6).  Behavioural equivalence to the historical coordinator bodies is
pinned by the unchanged integration suites (test_override_lifecycle,
test_phase0_event_order, test_mode_adoption, test_setpoint_adoption); THIS
module exercises the pure functions directly: expiry paths (timer/schedule/
permanent/presence), the §1 switchpoint-accuracy flag, Boost freeze/re-arm
(VT#1961), the §5 statistic gates and cap, the Defekt-2 event gate and the
``CommandResult`` event contents — plus the clock-injection contract: the
injected ``now_utc_fn``/``minutes_to_switchpoint_fn``/``local_minute_fn``
callables are evaluated ONLY on the paths that historically read the clock.
"""

from __future__ import annotations

from typing import Any

from custom_components.poise.comfort.schedule import ComfortSchedule, ComfortWindow
from custom_components.poise.control import override_runtime as ovr
from custom_components.poise.control.override import (
    OverrideConfig,
    OverrideMode,
    mode_comfort_base,
)
from custom_components.poise.runtime.state import PresenceRuntime, UserControlState
from custom_components.poise.runtime.tick_result import CommandResult, OverrideEnded

FROST = 7.0
DEVMAX = 30.0


class _Clock:
    """Counting fake for the injected wall-clock callables."""

    def __init__(self, t: float) -> None:
        self.t = t
        self.calls = 0

    def now(self) -> float:
        self.calls += 1
        return self.t


def _no_clock() -> float:
    raise AssertionError("clock must not be read on this path")


def _no_minutes() -> float | None:
    raise AssertionError("switchpoint lookup must not run on this path")


def _no_stat(_: float) -> None:
    raise AssertionError("stat recorder must not run on this path")


def _set(
    user: UserControlState,
    value: float | None,
    *,
    reason: str | None = None,
    policy: str = "timer",
    timer_h: float = 2.0,
    max_h: float = 8.0,
    now: float = 1_000.0,
    mins: float | None = None,
    stats: list[float] | None = None,
) -> CommandResult:
    """``set_override`` with defaults; ``stats`` records the stat-hook calls."""
    return ovr.set_override(
        user,
        value,
        reason=reason,
        policy=policy,
        timer_h=timer_h,
        max_h=max_h,
        frost_floor=FROST,
        device_max=DEVMAX,
        now_utc_fn=lambda: now,
        minutes_to_switchpoint_fn=lambda: mins,
        record_stat_fn=(stats.append if stats is not None else (lambda _: None)),
    )


# --- trivial setters -----------------------------------------------------------


def test_set_enabled_mutates_and_marks_dirty() -> None:
    user = UserControlState()
    result = ovr.set_enabled(user, False)
    assert user.enabled is False
    assert result == CommandResult(events=(), dirty=True)
    assert ovr.set_enabled(user, True).dirty is True
    assert user.enabled is True


def test_set_climate_mode_and_window_bypass() -> None:
    user = UserControlState()
    assert ovr.set_climate_mode(user, "heat") == CommandResult(dirty=True)
    assert user.climate_mode == "heat"
    assert ovr.set_window_bypass(user, True) == CommandResult(dirty=True)
    assert user.window_bypass is True


# --- minutes_to_switchpoint ----------------------------------------------------


def test_minutes_to_switchpoint_always_comfort_is_none() -> None:
    assert ovr.minutes_to_switchpoint(ComfortSchedule.always_comfort(), 600) is None


def test_minutes_to_switchpoint_inside_window_counts_to_setback() -> None:
    sched = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])  # 06:00-22:00
    # 10:00 -> 12h to the 22:00 window end (the setback edge)
    assert ovr.minutes_to_switchpoint(sched, 600) == 720.0


def test_minutes_to_switchpoint_in_setback_counts_to_comfort() -> None:
    sched = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])
    # 23:00 -> 7h to the 06:00 comfort start
    assert ovr.minutes_to_switchpoint(sched, 1380) == 420.0


# --- set_override: set path ----------------------------------------------------


def test_set_override_timer_policy_announces_expiry() -> None:
    user = UserControlState()
    stats: list[float] = []
    result = _set(user, 24.0, now=1_000.0, timer_h=2.0, stats=stats)
    assert user.override == 24.0
    assert user.override_requested == 24.0
    assert user.override_set_wall == 1_000.0
    assert user.override_expires_at == 1_000.0 + 2.0 * 3600.0
    assert user.override_expiry_is_switchpoint is False  # timer, never switchpoint
    assert user.override_reason == "ui_setpoint"  # K3 default origin
    assert stats == [24.0]  # §5 hook ran once, with the clamped value
    assert result == CommandResult(events=(), dirty=True)


def test_set_override_clamps_and_keeps_requested() -> None:
    user = UserControlState()
    stats: list[float] = []
    _set(user, 50.0, stats=stats)
    assert user.override == DEVMAX  # C2 clamp to the safe envelope
    assert user.override_requested == 50.0  # pre-clamp ask survives for the Card
    assert stats == [DEVMAX]  # the stat sees the CLAMPED value
    _set(user, 1.0, stats=stats)
    assert user.override == FROST
    assert user.override_requested == 1.0


def test_set_override_schedule_policy_switchpoint_expiry_and_flag() -> None:
    user = UserControlState()
    result = _set(user, 22.0, policy="schedule", now=1_000.0, mins=90.0, max_h=8.0)
    assert user.override_expires_at == 1_000.0 + 90.0 * 60.0
    assert user.override_expiry_is_switchpoint is True  # §1 reason accuracy
    assert result.dirty is True and result.events == ()


def test_set_override_schedule_without_switchpoint_uses_timer_fallback() -> None:
    user = UserControlState()
    _set(user, 22.0, policy="schedule", now=1_000.0, mins=None, timer_h=3.0)
    assert user.override_expires_at == 1_000.0 + 3.0 * 3600.0
    assert user.override_expiry_is_switchpoint is False  # fallback, not a switchpoint


def test_set_override_schedule_max_h_cap_clears_switchpoint_flag() -> None:
    user = UserControlState()
    # switchpoint far beyond the cap: expiry = max_h cap, flag must be False
    _set(user, 22.0, policy="schedule", now=1_000.0, mins=10 * 60.0, max_h=8.0)
    assert user.override_expires_at == 1_000.0 + 8.0 * 3600.0
    assert user.override_expiry_is_switchpoint is False


def test_set_override_custom_reason_is_stored() -> None:
    user = UserControlState()
    _set(user, 23.0, reason="device_adopt_setpoint")
    assert user.override_reason == "device_adopt_setpoint"


# --- set_override: clear path (Defekt-2 event gate) ----------------------------


def test_clear_active_hold_fires_user_resume_and_drops_lifecycle() -> None:
    user = UserControlState()
    _set(user, 24.0)
    result = ovr.set_override(
        user,
        None,
        reason=None,
        policy="timer",
        timer_h=2.0,
        max_h=8.0,
        frost_floor=FROST,
        device_max=DEVMAX,
        now_utc_fn=_no_clock,  # a clear NEVER reads the clock (historical path)
        minutes_to_switchpoint_fn=_no_minutes,
        record_stat_fn=_no_stat,
    )
    assert user.override is None
    assert user.override_set_wall is None
    assert user.override_expires_at is None
    assert user.override_requested is None
    assert user.override_expiry_is_switchpoint is False
    assert user.override_reason is None
    assert result == CommandResult(events=(OverrideEnded("user_resume"),), dirty=True)


def test_clear_with_custom_reason_fires_that_reason() -> None:
    user = UserControlState()
    _set(user, 24.0)
    result = _set(user, None, reason="mode_change")
    assert result.events == (OverrideEnded("mode_change"),)


def test_clear_without_active_hold_fires_nothing() -> None:
    user = UserControlState()
    result = _set(user, None)
    assert result == CommandResult(events=(), dirty=True)  # Defekt-2: no false event


def test_nan_clears_active_hold_without_event() -> None:
    user = UserControlState()
    _set(user, 24.0)
    result = _set(user, float("nan"))  # non-finite -> sanitized to None
    assert user.override is None
    assert user.override_reason is None
    # value is not None -> the Defekt-2 gate suppresses the event
    assert result == CommandResult(events=(), dirty=True)


# --- set_mode_override (K2) ----------------------------------------------------


def test_set_mode_override_starts_hold_lifecycle_when_none_active() -> None:
    user = UserControlState()
    clock = _Clock(2_000.0)
    result = ovr.set_mode_override(
        user,
        "off",
        policy="timer",
        timer_h=2.0,
        max_h=8.0,
        now_utc_fn=clock.now,
        minutes_to_switchpoint_fn=lambda: None,
    )
    assert user.mode_override == "off"
    assert user.override_reason == "device_adopt_mode"  # K3 origin
    assert user.override_set_wall == 2_000.0
    assert user.override_expires_at == 2_000.0 + 2.0 * 3600.0
    assert clock.calls == 1
    assert result == CommandResult(events=(), dirty=True)


def test_set_mode_override_keeps_expiry_of_same_frame_setpoint_hold() -> None:
    user = UserControlState()
    _set(user, 24.0, now=1_000.0, timer_h=2.0)
    expires = user.override_expires_at
    result = ovr.set_mode_override(
        user,
        "heat",
        policy="timer",
        timer_h=2.0,
        max_h=8.0,
        now_utc_fn=_no_clock,  # frame rule: an active hold keeps its expiry
        minutes_to_switchpoint_fn=_no_minutes,
    )
    assert user.mode_override == "heat"
    assert user.override_reason == "device_adopt_mode"  # K3 re-stamped
    assert user.override_set_wall == 1_000.0
    assert user.override_expires_at == expires
    assert result.dirty is True


def test_set_mode_override_clear_leaves_reason_and_lifecycle_alone() -> None:
    user = UserControlState()
    _set(user, 24.0, now=1_000.0)
    result = ovr.set_mode_override(
        user,
        None,
        policy="timer",
        timer_h=2.0,
        max_h=8.0,
        now_utc_fn=_no_clock,
        minutes_to_switchpoint_fn=_no_minutes,
    )
    assert user.mode_override is None
    assert user.override_reason == "ui_setpoint"  # untouched by the clear
    assert user.override_set_wall == 1_000.0  # setpoint hold keeps running
    assert result == CommandResult(events=(), dirty=True)


# --- set_preset (ADR-0059 §2, VT#1961) -----------------------------------------


def test_set_preset_boost_freezes_prior_preset_and_arms_timer() -> None:
    user = UserControlState()
    ovr.set_preset(
        user, OverrideMode.COMFORT, boost_duration_min=60.0, now_utc_fn=_no_clock
    )
    clock = _Clock(5_000.0)
    result = ovr.set_preset(
        user, OverrideMode.BOOST, boost_duration_min=60.0, now_utc_fn=clock.now
    )
    assert user.preset is OverrideMode.BOOST
    assert user.boost_prev_preset is OverrideMode.COMFORT
    assert user.boost_expires_at == 5_000.0 + 60.0 * 60.0
    assert clock.calls == 1
    assert result == CommandResult(events=(), dirty=True)


def test_double_boost_rearms_but_keeps_frozen_preset() -> None:
    user = UserControlState()
    ovr.set_preset(
        user, OverrideMode.COMFORT, boost_duration_min=60.0, now_utc_fn=_no_clock
    )
    ovr.set_preset(
        user, OverrideMode.BOOST, boost_duration_min=60.0, now_utc_fn=lambda: 5_000.0
    )
    ovr.set_preset(
        user, OverrideMode.BOOST, boost_duration_min=60.0, now_utc_fn=lambda: 6_000.0
    )
    assert user.boost_prev_preset is OverrideMode.COMFORT  # VT#1961: never BOOST
    assert user.boost_expires_at == 6_000.0 + 3_600.0  # re-armed from the new now


def test_stateless_preset_drops_boost_timer_and_frozen_preset() -> None:
    user = UserControlState()
    ovr.set_preset(
        user, OverrideMode.BOOST, boost_duration_min=60.0, now_utc_fn=lambda: 5_000.0
    )
    result = ovr.set_preset(
        user, OverrideMode.ECO, boost_duration_min=60.0, now_utc_fn=_no_clock
    )
    assert user.preset is OverrideMode.ECO
    assert user.boost_expires_at is None
    assert user.boost_prev_preset is None
    assert result.dirty is True


# --- end_hold ------------------------------------------------------------------


def test_end_hold_clears_all_hold_state_and_reports_event() -> None:
    user = UserControlState()
    _set(user, 24.0)
    user.mode_override = "off"
    result = ovr.end_hold(user, "frost_rescue")
    assert user.override is None
    assert user.mode_override is None  # K2: shared end
    assert user.override_set_wall is None
    assert user.override_expires_at is None
    assert user.override_requested is None
    assert user.override_reason is None
    assert user.override_expiry_is_switchpoint is False
    assert result == CommandResult(events=(OverrideEnded("frost_rescue"),), dirty=True)


# --- expire_timed_states -------------------------------------------------------


def _expire(
    user: UserControlState,
    presence: PresenceRuntime,
    home: bool | None,
    *,
    now: float,
    end_on_presence: bool = False,
) -> CommandResult:
    return ovr.expire_timed_states(
        user,
        presence,
        home,
        end_on_presence=end_on_presence,
        boost_duration_min=60.0,
        now_utc_fn=lambda: now,
    )


def test_expired_timer_hold_ends_with_expired_timer_reason() -> None:
    user = UserControlState()
    _set(user, 24.0, now=1_000.0, timer_h=2.0)
    result = _expire(user, PresenceRuntime(), True, now=1_000.0 + 2.0 * 3600.0)
    assert user.override is None
    assert result == CommandResult(events=(OverrideEnded("expired_timer"),), dirty=True)


def test_expired_switchpoint_hold_reports_schedule_point() -> None:
    user = UserControlState()
    _set(user, 24.0, policy="schedule", now=1_000.0, mins=30.0)
    assert user.override_expiry_is_switchpoint is True
    result = _expire(user, PresenceRuntime(), None, now=1_000.0 + 30.0 * 60.0)
    assert result.events == (OverrideEnded("schedule_point"),)


def test_presence_flip_ends_hold_with_presence_change_reason() -> None:
    user = UserControlState()
    _set(user, 24.0, policy="schedule", now=1_000.0, mins=30.0)
    presence = PresenceRuntime()
    presence.prev_home = True
    # flip beats the (not yet reached) wall expiry AND the switchpoint flag
    result = _expire(user, presence, False, now=1_100.0, end_on_presence=True)
    assert presence.prev_home is False  # flip tracking advanced
    assert result.events == (OverrideEnded("presence_change"),)


def test_presence_flip_without_option_keeps_hold() -> None:
    user = UserControlState()
    _set(user, 24.0, now=1_000.0, timer_h=2.0)
    presence = PresenceRuntime()
    presence.prev_home = True
    result = _expire(user, presence, False, now=1_100.0, end_on_presence=False)
    assert user.override == 24.0
    assert result == CommandResult(events=(), dirty=False)
    assert presence.prev_home is False


def test_permanent_hold_ends_only_on_presence_trigger() -> None:
    user = UserControlState()
    _set(user, 24.0, policy="permanent", now=1_000.0)
    assert user.override_expires_at is None
    presence = PresenceRuntime()
    presence.prev_home = True
    assert _expire(user, presence, True, now=9e9).events == ()  # time never ends it
    result = _expire(user, presence, False, now=9e9, end_on_presence=True)
    assert result.events == (OverrideEnded("presence_change"),)


def test_mode_hold_without_setpoint_hold_expires_on_same_trigger() -> None:
    user = UserControlState()
    clock = _Clock(1_000.0)
    ovr.set_mode_override(
        user,
        "off",
        policy="timer",
        timer_h=2.0,
        max_h=8.0,
        now_utc_fn=clock.now,
        minutes_to_switchpoint_fn=lambda: None,
    )
    result = _expire(user, PresenceRuntime(), None, now=1_000.0 + 2.0 * 3600.0)
    assert user.mode_override is None  # K2: same expiry triggers
    assert result.events == (OverrideEnded("expired_timer"),)


def test_expired_boost_restores_frozen_preset() -> None:
    user = UserControlState()
    ovr.set_preset(
        user, OverrideMode.ECO, boost_duration_min=60.0, now_utc_fn=_no_clock
    )
    ovr.set_preset(
        user, OverrideMode.BOOST, boost_duration_min=60.0, now_utc_fn=lambda: 1_000.0
    )
    result = _expire(user, PresenceRuntime(), None, now=1_000.0 + 3_600.0)
    assert user.preset is OverrideMode.ECO  # frozen preset restored
    assert user.boost_expires_at is None  # Boost is stateless again
    assert user.boost_prev_preset is None
    assert result == CommandResult(events=(), dirty=True)  # restore marks dirty


def test_expire_noop_updates_prev_home_without_dirty() -> None:
    user = UserControlState()
    presence = PresenceRuntime()
    result = _expire(user, presence, True, now=1_000.0)
    assert presence.prev_home is True  # tracking always advances
    assert result == CommandResult(events=(), dirty=False)


# --- record_override_stat (§5) -------------------------------------------------


def _record(
    user: UserControlState,
    clamped: float,
    *,
    presence_level: str = "comfort",
    window_open: bool = False,
    comfort_base: float = 21.0,
    minute: int = 600,
    now: float = 1_234.0,
    schedule: ComfortSchedule | None = None,
) -> None:
    ovr.record_override_stat(
        user,
        clamped,
        presence_level=presence_level,
        window_open=window_open,
        comfort_base=comfort_base,
        override_cfg=OverrideConfig(),
        schedule=schedule or ComfortSchedule.always_comfort(),
        local_minute_fn=lambda: minute,
        now_utc_fn=lambda: now,
    )


def test_stat_gates_skip_away_and_window_without_clock_reads() -> None:
    user = UserControlState()
    user.preset = OverrideMode.AWAY
    ovr.record_override_stat(
        user,
        24.0,
        presence_level="comfort",
        window_open=False,
        comfort_base=21.0,
        override_cfg=OverrideConfig(),
        schedule=ComfortSchedule.always_comfort(),
        local_minute_fn=lambda: (_ for _ in ()).throw(AssertionError("gated")),
        now_utc_fn=_no_clock,
    )
    user.preset = OverrideMode.NONE
    _record(user, 24.0, presence_level="away")  # presence-level gate
    _record(user, 24.0, window_open=True)  # window gate
    assert user.override_stats == []


def test_stat_appends_direction_delta_phase_and_level() -> None:
    user = UserControlState()
    user.preset = OverrideMode.ECO  # base = comfort_base - eco_offset = 19.0
    _record(user, 24.0, comfort_base=21.0, minute=600, now=1_234.0)
    expected_base = mode_comfort_base(OverrideMode.ECO, 21.0, OverrideConfig())
    assert user.override_stats == [
        {
            "ts": 1_234.0,
            "direction": 1,
            "delta": round(24.0 - expected_base, 2),
            "phase": "comfort",
            "presence_level": "comfort",
        }
    ]
    sched = ComfortSchedule.from_windows([ComfortWindow(360, 1320)])
    _record(user, 17.0, minute=1_380, schedule=sched)  # 23:00 -> setback
    entry: dict[str, Any] = user.override_stats[-1]
    assert entry["direction"] == -1
    assert entry["phase"] == "setback"


def test_stat_log_caps_at_last_50() -> None:
    user = UserControlState()
    for i in range(55):
        _record(user, 20.0 + i * 0.01, now=float(i))
    assert len(user.override_stats) == 50
    assert user.override_stats[0]["ts"] == 5.0  # the oldest five were dropped
    assert user.override_stats[-1]["ts"] == 54.0
