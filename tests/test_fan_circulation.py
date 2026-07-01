from __future__ import annotations

from custom_components.poise.comfort.fan_circulation import (
    FAN_ONLY_LOW,
    fan_circulation,
)


def _call(
    *,
    occupied: bool | None = True,
    in_deadband: bool = True,
    active_mode: str = "idle",
    window_open: bool = False,
    can_recirculate: bool = True,
    policy: str = FAN_ONLY_LOW,
    presence_optin: bool = False,
) -> tuple[str, str]:
    r = fan_circulation(
        occupied=occupied,
        in_deadband=in_deadband,
        active_mode=active_mode,
        window_open=window_open,
        can_recirculate=can_recirculate,
        policy=policy,
        presence_optin=presence_optin,
    )
    return r.action, r.reason


def test_fan_low_when_occupied_idle_capable_enabled() -> None:
    assert _call() == ("fan_low", "occupied_idle")


def test_disabled_policy_is_none() -> None:
    assert _call(policy="off") == ("none", "disabled")


def test_no_capability_is_none() -> None:
    assert _call(can_recirculate=False) == ("none", "no_fan_capability")


def test_window_open_suppresses() -> None:
    assert _call(window_open=True) == ("none", "window_open")


def test_active_mode_suppresses() -> None:
    for m in ("heat", "cool", "dry"):
        assert _call(active_mode=m) == ("none", "active_mode")


def test_not_in_deadband_is_none() -> None:
    assert _call(in_deadband=False) == ("none", "not_idle")


def test_unoccupied_is_none() -> None:
    assert _call(occupied=False) == ("none", "unoccupied_or_no_presence")


def test_no_presence_without_optin_is_none() -> None:
    assert _call(occupied=None) == ("none", "unoccupied_or_no_presence")


def test_no_presence_with_optin_is_fan_low() -> None:
    assert _call(occupied=None, presence_optin=True) == (
        "fan_low",
        "idle_no_presence_optin",
    )
