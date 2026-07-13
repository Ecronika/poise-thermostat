"""Pure state matrix for ``resolve_hvac_action`` (display contract, V2).

Covers the reported defect (manual cooling/heating override must not read idle)
plus the real-actuator-preferred semantics: the device's own action wins when
present, Poise's arbitrated intent is the fallback, never the raw "manual" tag.
"""

from __future__ import annotations

import pytest

from custom_components.poise.devices.hvac_modes import resolve_hvac_action


def _act(**kw):
    base = dict(enabled=True, final_mode="idle", actuator_action=None)
    base.update(kw)
    return resolve_hvac_action(**base)


def test_disabled_is_off() -> None:
    assert _act(enabled=False, final_mode="cool", actuator_action="cooling") == "off"


# --- device reports a real action -> it wins (V2 ground truth) --------------


@pytest.mark.parametrize(
    "device",
    ["heating", "cooling", "drying", "fan", "idle", "preheating", "defrosting"],
)
def test_device_action_is_ground_truth(device: str) -> None:
    # even when Poise's intent says something else, the device wins
    assert _act(final_mode="idle", actuator_action=device) == device


def test_guard_held_compressor_reads_idle_not_cooling() -> None:
    # intent is cool, but the device still reports idle (guard hasn't switched)
    assert _act(final_mode="cool", actuator_action="idle") == "idle"


def test_saturated_valve_reads_idle_despite_heat_intent() -> None:
    assert _act(final_mode="heat", actuator_action="idle") == "idle"


def test_device_action_is_case_insensitive() -> None:
    assert _act(final_mode="idle", actuator_action="COOLING") == "cooling"


# --- device reports nothing usable -> arbitrated intent (never "manual") -----


def test_override_cool_with_silent_device_reads_cooling() -> None:
    # the reported defect: manual override cools, device reports no action
    assert _act(final_mode="cool", actuator_action=None) == "cooling"


def test_override_heat_with_silent_device_reads_heating() -> None:
    assert _act(final_mode="heat", actuator_action=None) == "heating"


def test_dry_in_deadband_reads_drying() -> None:
    assert _act(final_mode="dry", actuator_action=None) == "drying"


def test_fan_only_park_reads_fan() -> None:
    assert _act(final_mode="idle", idle_park_mode="fan_only") == "fan"


def test_idle_park_in_heat_reads_idle() -> None:
    assert _act(final_mode="idle", idle_park_mode="heat") == "idle"


def test_window_off_reads_idle() -> None:
    assert _act(final_mode="off", actuator_action=None) == "idle"


def test_device_off_falls_back_to_intent() -> None:
    # "off" is not a usable action signal -> fall back to intent
    assert _act(final_mode="cool", actuator_action="off") == "cooling"
    assert _act(final_mode="idle", actuator_action="off") == "idle"
