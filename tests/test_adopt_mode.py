"""K2: pure detection of a device-side hvac_mode change worth adopting as a manual
mode-hold (``detect_external_mode``). The coordinator (glue) turns an adopted mode
into a hold; this only decides *whether* the reported mode is a genuine user change
or an echo of Poise's own nudge. Categorical (no deadband)."""

from __future__ import annotations

from custom_components.poise.control.override import detect_external_mode

EW = 120.0  # echo window (s)
TS = 1000.0  # monotonic stamp of the last mode command
SUPPORTED = ("off", "heat", "cool", "dry", "fan_only")


def _m(**kw: object) -> str | None:
    """Call the mode detector with sensible defaults (a genuine cool change) overridden
    per test: Poise commanded heat, the device now reports cool, past the window."""
    base: dict[str, object] = {
        "device_mode": "cool",
        "desired_mode": "heat",
        "last_commanded_mode": "heat",
        "last_cmd_ts": TS,
        "now": TS + 500.0,  # well past the echo window
        "echo_window_s": EW,
        "supported_modes": SUPPORTED,
        "prev_mode": "heat",  # device moved heat -> cool
    }
    base.update(kw)
    return detect_external_mode(**base)  # type: ignore[arg-type]


def test_no_usable_reading_is_ignored() -> None:
    assert _m(device_mode=None) is None
    assert _m(device_mode="unknown") is None
    assert _m(device_mode="unavailable") is None


def test_mode_already_matching_desired_is_ignored() -> None:
    # the device is already where Poise wants it -> nothing external to adopt
    assert _m(device_mode="heat", desired_mode="heat") is None


def test_unsupported_mode_is_not_adopted() -> None:
    # a mode the device does not actually list must never be held
    assert _m(device_mode="auto") is None
    assert _m(device_mode="dry", supported_modes=("off", "heat", "cool")) is None


def test_heat_cool_is_not_adopted_in_v1() -> None:
    # dual-setpoint mode is out of scope for v1 (B7), even if the device supports it
    assert (
        _m(device_mode="heat_cool", supported_modes=(*SUPPORTED, "heat_cool")) is None
    )


def test_no_baseline_is_ignored() -> None:
    # Poise has not commanded a mode yet -> cannot tell an echo from a change
    assert _m(last_commanded_mode=None) is None
    assert _m(last_cmd_ts=None) is None


def test_echo_of_our_own_command_is_ignored() -> None:
    # device reports the mode Poise last commanded (heat) while desired has moved to
    # cool -> our own nudge echo, not a user change; Poise will re-nudge to cool.
    assert (
        _m(device_mode="heat", desired_mode="cool", last_commanded_mode="heat") is None
    )


def test_within_echo_window_is_suppressed() -> None:
    # a differing report soon after our command may be a lagging echo of an earlier
    # command -> conservative suppression; adopted on the first tick past the window.
    assert _m(device_mode="cool", now=TS + 50.0) is None


def test_stable_mode_is_not_adopted() -> None:
    # a mode unchanged since the previous reading is not a fresh user action
    assert _m(device_mode="cool", prev_mode="cool") is None


def test_genuine_mode_change_is_adopted() -> None:
    # user turned the split AC from heat to cool via the remote, past the window
    assert _m(device_mode="cool") == "cool"


def test_user_off_is_adopted() -> None:
    # a user switching the device off is adopted (the coordinator holds it "off",
    # keeping frost/mould rescue active -- the existing disabled-branch machinery)
    assert _m(device_mode="off") == "off"


def test_user_fan_only_is_adopted() -> None:
    assert _m(device_mode="fan_only") == "fan_only"


def test_first_observation_without_prev_still_gated() -> None:
    # prev is None on the first reading -> the move guard is skipped, but the echo /
    # baseline / window guards still apply, so a cold start never false-adopts.
    assert _m(device_mode="cool", prev_mode=None) == "cool"  # past window, real change
    assert _m(device_mode="cool", prev_mode=None, last_commanded_mode=None) is None
