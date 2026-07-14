"""P1-4a: pure detection of a device-side setpoint change worth adopting as a
manual hold (``detect_external_setpoint``). The coordinator (glue) turns an
adopted value into a hold; this only decides *whether* the reported setpoint is a
genuine user change or an echo of Poise's own write."""

from __future__ import annotations

from custom_components.poise.control.override import detect_external_setpoint

EW = 120.0  # echo window (s)
DB = 0.5  # deadband = one device step
WROTE = 20.0  # what Poise last commanded (snapped to the device step)
TS = 1000.0  # monotonic stamp of that write


def _d(**kw: float | None) -> float | None:
    """Call the detector with sensible defaults (a settled echo) overridden per test."""
    base: dict[str, float | None] = {
        "device_sp": WROTE,
        "last_written_sp": WROTE,
        "last_write_ts": TS,
        "now": TS + 500.0,  # well past the echo window
        "echo_window_s": EW,
        "deadband": DB,
    }
    base.update(kw)
    return detect_external_setpoint(**base)  # type: ignore[arg-type]


def test_no_device_reading_is_ignored() -> None:
    assert _d(device_sp=None) is None


def test_no_baseline_is_ignored() -> None:
    # Poise has not established control yet -> cannot tell an echo from a change.
    assert _d(last_written_sp=None, device_sp=21.0) is None
    assert _d(last_write_ts=None, device_sp=21.0) is None


def test_within_echo_window_is_suppressed() -> None:
    # the device may still be reporting its pre-write value (Zigbee/poll lag).
    assert _d(device_sp=22.0, now=TS + 50.0) is None


def test_echo_of_our_own_write_is_ignored() -> None:
    assert _d(device_sp=WROTE) is None


def test_sub_deadband_requantisation_is_ignored() -> None:
    # the device snapped our command to a coarser step (0.3 K < 0.5 K deadband).
    assert _d(device_sp=20.3) is None


def test_genuine_change_outside_window_is_adopted() -> None:
    assert _d(device_sp=23.0) == 23.0
    assert _d(device_sp=18.0, last_written_sp=21.0) == 18.0  # downward too


def test_one_step_change_at_the_deadband_boundary_is_adopted() -> None:
    # a full one-step turn of the wheel (0.5 K == deadband) counts as external.
    assert _d(device_sp=20.5) == 20.5


def test_echo_window_boundary_is_no_longer_suppressed() -> None:
    assert _d(device_sp=23.0, now=TS + EW) == 23.0


def test_stable_device_offset_is_not_adopted() -> None:
    # The device settled our write at a fixed offset > deadband (own re-quantise /
    # min-max clamp) and reports it UNCHANGED tick over tick. Adopting it would
    # re-read Poise's own settled write as a manual hold once the echo window lapses
    # (the live "card-X resume springs back to manual" bug). A stable value (== the
    # previous reading) is never a fresh user action.
    assert _d(device_sp=23.0, prev_device_sp=23.0) is None
    # even a large persistent gap from our command is ignored while it is stable
    assert _d(device_sp=18.0, last_written_sp=21.0, prev_device_sp=18.0) is None


def test_moved_device_setpoint_is_adopted() -> None:
    # a genuine wheel turn MOVES the setpoint since the previous reading
    assert _d(device_sp=23.0, prev_device_sp=20.0) == 23.0
    assert _d(device_sp=18.0, last_written_sp=21.0, prev_device_sp=21.0) == 18.0


def test_in_window_third_value_is_adopted_immediately() -> None:
    # B1 fix (analysis 2026-07-14): inside the echo window a legit echo/lag can only
    # report our command (== last_written) or the pre-write value. A value differing
    # from BOTH by >= deadband is provably a fresh user change -> adopt in-window,
    # instead of swallowing it and reverting minutes later.
    assert (
        _d(device_sp=26.0, now=TS + 50.0, last_written_sp=24.0, pre_write_sp=24.0)
        == 26.0
    )
    assert (
        _d(device_sp=26.0, now=TS + 50.0, last_written_sp=24.0, pre_write_sp=22.0)
        == 26.0
    )


def test_in_window_pre_write_lag_is_suppressed() -> None:
    # the device still reports its pre-write value (poll lag) -> not a user change
    assert (
        _d(device_sp=22.0, now=TS + 50.0, last_written_sp=24.0, pre_write_sp=22.0)
        is None
    )


def test_in_window_without_pre_write_stays_conservative() -> None:
    # no pre-write reference -> cannot prove a third value -> suppress in-window
    assert (
        _d(device_sp=26.0, now=TS + 50.0, last_written_sp=24.0, pre_write_sp=None)
        is None
    )


def test_first_observation_without_prev_still_gated_by_baseline() -> None:
    # prev is None on the very first reading -> the move guard is skipped, but the
    # no-baseline / echo guards still apply, so cold start never false-adopts.
    assert _d(device_sp=23.0, prev_device_sp=None) == 23.0  # baseline present here
    assert _d(device_sp=23.0, prev_device_sp=None, last_written_sp=None) is None


def test_in_window_sub_step_requantise_is_echo_not_third_value() -> None:
    # RC review F1: a device that settles / re-quantises our command within one step
    # (21.5 -> 21.8 on a 0.5 K grid) must read as OUR echo, not a fresh user change,
    # even inside the window and even with a pre-write reference present. The
    # step-sized deadband (the caller passes max(WRITE_DEADBAND_C, step), not a bare
    # 0.2) is what keeps this an echo; lowering it re-opened phantom "manual" holds
    # on poll/sluggish devices whose echoes arrive under a fresh context.
    assert (
        _d(device_sp=21.8, now=TS + 50.0, last_written_sp=21.5, pre_write_sp=20.0)
        is None
    )
