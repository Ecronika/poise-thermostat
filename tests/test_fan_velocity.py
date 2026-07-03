"""Tests for fan-state -> air-velocity estimation (ADR-0054 stage 3, shadow)."""

from __future__ import annotations

from custom_components.poise.comfort.fan_cooling import (
    STILL_AIR_MS,
    cooling_effect,
    fan_velocity,
)


def test_still_when_not_fan_capable() -> None:
    assert (
        fan_velocity(fan_mode="high", hvac_action="cooling", can_recirculate=False)
        == STILL_AIR_MS
    )


def test_still_when_not_actively_moving_air() -> None:
    assert fan_velocity(fan_mode="auto", hvac_action="idle") == STILL_AIR_MS
    assert fan_velocity(fan_mode="high", hvac_action="off") == STILL_AIR_MS
    assert fan_velocity(fan_mode="low", hvac_action=None) == STILL_AIR_MS


def test_by_stage_when_cooling() -> None:
    assert fan_velocity(fan_mode="low", hvac_action="cooling") == 0.25
    assert fan_velocity(fan_mode="medium", hvac_action="cooling") == 0.40
    assert fan_velocity(fan_mode="high", hvac_action="cooling") == 0.65
    assert fan_velocity(fan_mode="turbo", hvac_action="cooling") == 0.85
    assert fan_velocity(fan_mode="auto", hvac_action="cooling") == 0.35


def test_fan_only_dry_and_heating_move_air() -> None:
    assert fan_velocity(fan_mode="medium", hvac_action="fan") == 0.40
    assert fan_velocity(fan_mode="high", hvac_action="drying") == 0.65
    assert fan_velocity(fan_mode="high", hvac_action="heating") == 0.65


def test_unknown_stage_running_gets_conservative_default() -> None:
    assert fan_velocity(fan_mode="whoosh", hvac_action="cooling") == 0.30
    assert fan_velocity(fan_mode=None, hvac_action="cooling") == 0.30


def test_case_insensitive() -> None:
    assert fan_velocity(fan_mode="High", hvac_action="Cooling") == 0.65


def test_real_running_velocity_produces_nonzero_ce() -> None:
    v = fan_velocity(fan_mode="high", hvac_action="cooling")  # 0.65 m/s
    assert cooling_effect(v) > 1.0  # ~1.3 K, vs 0 for the still-air idle case
    assert cooling_effect(fan_velocity(fan_mode="auto", hvac_action="idle")) == 0.0
