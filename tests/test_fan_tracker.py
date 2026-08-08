"""Tests for the ADR-0068 U6 fan-channel echo discipline (pure)."""

from __future__ import annotations

from custom_components.poise.const import SETPOINT_ADOPT_ECHO_WINDOW_S
from custom_components.poise.control.external_override import (
    note_device_fan,
    observe_fan_foreign,
)
from custom_components.poise.runtime.state import ExternalOverrideRuntime

NOW = 5_000.0


def _ext(**over: object) -> ExternalOverrideRuntime:
    ext = ExternalOverrideRuntime()
    for key, value in over.items():
        setattr(ext, key, value)
    return ext


def test_no_signal_own_context_and_own_command_echo_are_never_foreign() -> None:
    ext = _ext(last_commanded_fan="low", last_fan_cmd_ts=NOW - 1000.0)
    assert observe_fan_foreign(ext, device_fan=None, own_change=False, now=NOW) is False
    # State change under our own HA context id: the tagged write echo.
    assert (
        observe_fan_foreign(ext, device_fan="turbo", own_change=True, now=NOW) is False
    )
    # The stage we last commanded, echoing late: own command echo.
    assert (
        observe_fan_foreign(ext, device_fan="low", own_change=False, now=NOW) is False
    )


def test_no_baseline_means_nothing_to_duel() -> None:
    # Poise never commanded a stage -> a device/firmware change is not a
    # write duel; the FSM entry guards own that case.
    ext = _ext(prev_device_fan="auto")
    assert (
        observe_fan_foreign(ext, device_fan="high", own_change=False, now=NOW) is False
    )


def test_echo_window_and_stability_suppress_foreign() -> None:
    ext = _ext(
        last_commanded_fan="low",
        last_fan_cmd_ts=NOW - SETPOINT_ADOPT_ECHO_WINDOW_S / 2.0,
        prev_device_fan="auto",
    )
    # Inside the echo window a differing readback is the device settling.
    assert (
        observe_fan_foreign(ext, device_fan="high", own_change=False, now=NOW) is False
    )
    # Outside the window: unchanged vs the move-guard reference -> no change.
    ext2 = _ext(
        last_commanded_fan="low",
        last_fan_cmd_ts=NOW - SETPOINT_ADOPT_ECHO_WINDOW_S * 2.0,
        prev_device_fan="high",
    )
    assert (
        observe_fan_foreign(ext2, device_fan="high", own_change=False, now=NOW) is False
    )


def test_real_user_stage_change_is_foreign() -> None:
    ext = _ext(
        last_commanded_fan="low",
        last_fan_cmd_ts=NOW - SETPOINT_ADOPT_ECHO_WINDOW_S * 2.0,
        prev_device_fan="low",
    )
    assert (
        observe_fan_foreign(ext, device_fan="turbo", own_change=False, now=NOW) is True
    )


def test_note_device_fan_freezes_the_reference_inside_the_echo_window() -> None:
    # Mirrors freeze_mode_reference: an in-window observation of the user's
    # (or the device's settling) stage never poisons the move guard.
    ext = _ext(
        last_commanded_fan="low",
        last_fan_cmd_ts=NOW - 1.0,
        prev_device_fan="auto",
    )
    note_device_fan(ext, device_fan="high", now=NOW)
    assert ext.prev_device_fan == "auto"  # frozen
    ext.last_fan_cmd_ts = NOW - SETPOINT_ADOPT_ECHO_WINDOW_S * 2.0
    note_device_fan(ext, device_fan="high", now=NOW)
    assert ext.prev_device_fan == "high"  # window closed -> reference moves
    # Without any command stamp the reference always follows.
    ext2 = _ext()
    note_device_fan(ext2, device_fan="medium", now=NOW)
    assert ext2.prev_device_fan == "medium"
