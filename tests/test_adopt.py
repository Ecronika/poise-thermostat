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
