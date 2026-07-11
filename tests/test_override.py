"""Tests for the override/preset model: preset offsets, fixed auto-revert, and
the ADR-0059 manual-override lifecycle (hold policy, presence-end, timed Boost)."""

from __future__ import annotations

from custom_components.poise.control.override import (
    OverrideConfig,
    OverrideMode,
    hold_expired,
    manual_override_expired,
    mode_comfort_base,
    resolve_boost_expiry,
    resolve_hold_expiry,
)

CFG = OverrideConfig()
SET_AT = 1000.0
HOUR = 3600.0


# --- ADR-0042: preset offsets + fixed auto-revert (unchanged) -----------------


def test_modes_offset_the_comfort_base() -> None:
    assert mode_comfort_base(OverrideMode.COMFORT, 21.0) == 21.0
    assert mode_comfort_base(OverrideMode.NONE, 21.0) == 21.0
    assert mode_comfort_base(OverrideMode.ECO, 21.0) == 21.0 - CFG.eco_offset
    assert mode_comfort_base(OverrideMode.BOOST, 21.0) == 21.0 + CFG.boost_offset
    assert mode_comfort_base(OverrideMode.AWAY, 21.0) == 21.0 - CFG.away_offset


def test_modes_are_offsets_not_free_temps() -> None:
    # A higher user base shifts every mode up by the same offset (norm-anchored).
    eco21 = mode_comfort_base(OverrideMode.ECO, 21.0)
    eco24 = mode_comfort_base(OverrideMode.ECO, 24.0)
    assert eco24 - eco21 == 3.0


def test_manual_override_auto_revert_window() -> None:
    # Just before the 2 h window -> still active.
    assert manual_override_expired(SET_AT, SET_AT + 2 * HOUR - 1, CFG) is False
    # At/after the window -> expired (reverts).
    assert manual_override_expired(SET_AT, SET_AT + 2 * HOUR, CFG) is True


# --- ADR-0059 §1: resolve_hold_expiry (announced at set-time) -----------------


def test_schedule_ends_at_switchpoint_value_independently() -> None:
    # tado-16475 class: a "schedule" hold ends at the next switchpoint *time*,
    # never at a temperature delta. The expiry is a pure function of
    # minutes-to-switchpoint and does NOT depend on timer_h while a switchpoint
    # exists -> the same switchpoint yields the same expiry.
    exp = resolve_hold_expiry(
        policy="schedule",
        set_at=SET_AT,
        timer_h=2.0,
        max_h=8.0,
        minutes_to_switchpoint=45.0,
    )
    assert exp == SET_AT + 45.0 * 60.0
    exp_other_timer = resolve_hold_expiry(
        policy="schedule",
        set_at=SET_AT,
        timer_h=6.0,  # different timer, same switchpoint
        max_h=8.0,
        minutes_to_switchpoint=45.0,
    )
    assert exp_other_timer == exp


def test_schedule_without_switchpoint_falls_back_to_timer() -> None:
    # "schedule without a schedule": no (or non-positive) switchpoint -> the
    # timer duration is the safety net.
    for mts in (None, 0.0, -30.0):
        exp = resolve_hold_expiry(
            policy="schedule",
            set_at=SET_AT,
            timer_h=2.0,
            max_h=8.0,
            minutes_to_switchpoint=mts,
        )
        assert exp == SET_AT + 2.0 * HOUR


def test_schedule_max_h_cap_binds_on_long_windowless_stretch() -> None:
    # A far-away switchpoint (10 h) is capped by override_max_h (8 h).
    exp = resolve_hold_expiry(
        policy="schedule",
        set_at=SET_AT,
        timer_h=2.0,
        max_h=8.0,
        minutes_to_switchpoint=600.0,
    )
    assert exp == SET_AT + 8.0 * HOUR
    # A near switchpoint (1 h) is below the cap and used verbatim.
    exp_near = resolve_hold_expiry(
        policy="schedule",
        set_at=SET_AT,
        timer_h=2.0,
        max_h=8.0,
        minutes_to_switchpoint=60.0,
    )
    assert exp_near == SET_AT + 60.0 * 60.0
    # The cap also bounds the timer fallback (timer_h > max_h, no switchpoint).
    exp_capped_fallback = resolve_hold_expiry(
        policy="schedule",
        set_at=SET_AT,
        timer_h=12.0,
        max_h=8.0,
        minutes_to_switchpoint=None,
    )
    assert exp_capped_fallback == SET_AT + 8.0 * HOUR


def test_timer_policy_uses_fixed_duration() -> None:
    # timer ignores the switchpoint entirely (today's ADR-0042 behaviour).
    exp = resolve_hold_expiry(
        policy="timer",
        set_at=SET_AT,
        timer_h=2.0,
        max_h=8.0,
        minutes_to_switchpoint=45.0,
    )
    assert exp == SET_AT + 2.0 * HOUR


def test_permanent_policy_has_no_time_expiry() -> None:
    # permanent never auto-expires -> None (it ends only on presence).
    assert (
        resolve_hold_expiry(
            policy="permanent",
            set_at=SET_AT,
            timer_h=2.0,
            max_h=8.0,
            minutes_to_switchpoint=45.0,
        )
        is None
    )


def test_unknown_policy_is_treated_as_timer() -> None:
    exp = resolve_hold_expiry(
        policy="bogus",
        set_at=SET_AT,
        timer_h=2.0,
        max_h=8.0,
        minutes_to_switchpoint=45.0,
    )
    assert exp == SET_AT + 2.0 * HOUR


# --- ADR-0059 §1: hold_expired (tick-time decision) ---------------------------


def test_hold_expires_at_announced_wall_clock() -> None:
    expires_at = SET_AT + 2 * HOUR
    assert (
        hold_expired(
            expires_at=expires_at,
            now=expires_at - 1,
            presence_changed=False,
            end_on_presence=True,
        )
        is False
    )
    assert (
        hold_expired(
            expires_at=expires_at,
            now=expires_at,
            presence_changed=False,
            end_on_presence=True,
        )
        is True
    )


def test_hold_ends_on_presence_flip_either_direction() -> None:
    far = SET_AT + 8 * HOUR  # time has not elapsed -> only presence can end it
    # A house-gate flip (home->away OR away->home) both surface as
    # presence_changed=True and end the hold when the option is on.
    assert (
        hold_expired(
            expires_at=far,
            now=SET_AT,
            presence_changed=True,
            end_on_presence=True,
        )
        is True
    )
    # With the option OFF, a presence flip is ignored (tado-X: manual beats away).
    assert (
        hold_expired(
            expires_at=far,
            now=SET_AT,
            presence_changed=True,
            end_on_presence=False,
        )
        is False
    )


def test_permanent_hold_ends_only_on_presence() -> None:
    # expires_at None (permanent): no amount of elapsed time ends it...
    assert (
        hold_expired(
            expires_at=None,
            now=1e12,
            presence_changed=False,
            end_on_presence=True,
        )
        is False
    )
    # ...but a presence flip still does (when the option is on).
    assert (
        hold_expired(
            expires_at=None,
            now=1e12,
            presence_changed=True,
            end_on_presence=True,
        )
        is True
    )


# --- ADR-0059 §2: timed Boost -------------------------------------------------


def test_boost_expiry_is_set_at_plus_duration() -> None:
    assert resolve_boost_expiry(set_at=SET_AT, boost_duration_min=60.0) == (
        SET_AT + 60.0 * 60.0
    )
    assert resolve_boost_expiry(set_at=0.0, boost_duration_min=15.0) == 900.0
