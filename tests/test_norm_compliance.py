from __future__ import annotations

from custom_components.poise.comfort.norm_compliance import (
    ASR_MAX_ROOM_C,
    clamp_to_norm,
)


def test_within_envelope_no_binding() -> None:
    r = clamp_to_norm(21.0, floor=7.0)
    assert r.value == 21.0
    assert r.binding is None


def test_below_floor_clamps_up() -> None:
    r = clamp_to_norm(5.0, floor=7.0)
    assert r.value == 7.0
    assert r.binding == "norm_floor"


def test_above_asr_cap_clamps_down() -> None:
    r = clamp_to_norm(28.0, floor=7.0)
    assert r.value == ASR_MAX_ROOM_C == 26.0
    assert r.binding == "norm_cap"


def test_mould_floor_passed_in_wins_over_frost() -> None:
    # caller passes a higher mould floor; setpoint below it is lifted
    r = clamp_to_norm(15.0, floor=16.5)
    assert r.value == 16.5
    assert r.binding == "norm_floor"


def test_inverted_envelope_floor_wins() -> None:
    r = clamp_to_norm(24.0, floor=27.0, cap=26.0)
    assert r.value == 27.0
    assert r.binding == "norm_floor"


def test_custom_cap() -> None:
    r = clamp_to_norm(25.0, floor=7.0, cap=24.0)
    assert r.value == 24.0
    assert r.binding == "norm_cap"
