from __future__ import annotations

import math

from custom_components.poise.estimation.heatup_rate import (
    HeatupAccumulator,
    sample_heatup_rate,
)


def _s(acc: HeatupAccumulator, room: float, mono: float, heating: bool = True):
    return sample_heatup_rate(acc, heating=heating, room=room, mono=mono)


def test_flat_quantized_ticks_go_in_the_denominator_not_a_spike() -> None:
    # The bug: on a 0.5 K-quantized sensor a slow rise reads flat for many ticks,
    # then jumps one quantum. Per-tick (quantum / one 60 s tick) = 30 K/h — 10x
    # the truth. Accumulating over the FULL interval divides 0.5 K by 600 s.
    acc = HeatupAccumulator()
    assert _s(acc, 20.0, 0.0) is None  # anchor
    for t in range(1, 10):  # 9 flat ticks, 60 s apart: rise 0 -> pending
        assert _s(acc, 20.0, t * 60.0) is None
    rate = _s(acc, 20.5, 600.0)  # quantum crossing after 10 min
    assert rate is not None
    assert math.isclose(rate, 3.0, abs_tol=1e-9)  # 0.5 K / (600/3600 h), not 30


def test_anchor_advances_after_emitting() -> None:
    acc = HeatupAccumulator()
    _s(acc, 20.0, 0.0)
    assert _s(acc, 20.5, 600.0) is not None  # emits, re-anchors at (20.5, 600)
    for t in (660.0, 720.0, 780.0):
        assert _s(acc, 20.5, t) is None  # flat again -> pending from new anchor
    rate = _s(acc, 20.9, 1080.0)  # +0.4 K over (1080-600)=480 s
    assert rate is not None
    assert math.isclose(rate, 0.4 / (480.0 / 3600.0), abs_tol=1e-9)  # = 3.0 K/h


def test_not_heating_resets_the_anchor() -> None:
    acc = HeatupAccumulator()
    _s(acc, 20.0, 0.0)
    assert sample_heatup_rate(acc, heating=False, room=20.5, mono=60.0) is None
    assert acc.anchor_room is None and acc.anchor_mono is None


def test_stale_burst_reanchors_without_emitting() -> None:
    acc = HeatupAccumulator()
    _s(acc, 20.0, 0.0)
    # next heating sample arrives 2 h later (> MAX_SPAN_H) — a gap, not a rate.
    assert _s(acc, 24.0, 2.0 * 3600.0) is None
    assert acc.anchor_room == 24.0  # re-anchored to the fresh sample


def test_subthreshold_rise_keeps_waiting() -> None:
    acc = HeatupAccumulator()
    _s(acc, 20.0, 0.0)
    assert _s(acc, 20.2, 300.0) is None  # 0.2 K < 0.3 K gate
    assert acc.anchor_room == 20.0  # anchor unchanged -> still accumulating


def test_negative_rise_reanchors_at_the_lower_point() -> None:
    acc = HeatupAccumulator()
    _s(acc, 20.0, 0.0)
    assert _s(acc, 19.8, 120.0) is None  # dip while nominally heating
    assert acc.anchor_room == 19.8  # re-anchored low, no negative rate recorded
