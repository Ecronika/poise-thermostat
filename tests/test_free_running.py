"""ADR-0023 §1 free-running adaptive band widening (pure)."""

from __future__ import annotations

from custom_components.poise.comfort.free_running import free_running_widen


def test_floating_room_widens_band_with_trm() -> None:
    # T_rm 12 -> adaptive lower 0.33*12+18.8-4 = 18.76, upper 25.76
    r = free_running_widen(heat_op=20.0, cool_op=23.0, room=21.5, t_rm=12.0)
    assert r.active is True
    assert r.heat_op < 20.0  # heat edge lowered toward the adaptive lower
    assert abs(r.heat_op - 18.76) < 0.05
    assert r.cool_op > 23.0  # cool edge raised toward the adaptive upper


def test_never_raises_heat_edge() -> None:
    # T_rm 28 -> adaptive lower 24.04 > fixed 20: must NOT raise the heat edge
    r = free_running_widen(heat_op=20.0, cool_op=23.0, room=21.0, t_rm=28.0)
    assert r.heat_op == 20.0  # min(20, 24.04) -> 20, never up
    assert r.cool_op > 23.0  # but cool edge still widens up (to ~31)


def test_active_cooling_demand_not_widened() -> None:
    # room above the fixed cool edge -> cooling demanded -> NOT free-running,
    # so the fixed cool band is preserved and cooling is never suppressed
    r = free_running_widen(heat_op=20.0, cool_op=23.0, room=27.0, t_rm=28.0)
    assert r.active is False
    assert r.cool_op == 23.0


def test_active_heating_demand_not_widened() -> None:
    r = free_running_widen(heat_op=20.0, cool_op=23.0, room=18.0, t_rm=12.0)
    assert r.active is False
    assert r.heat_op == 20.0


def test_extrapolated_trm_inactive() -> None:
    # T_rm outside [10, 30] -> adaptive model invalid -> no widening
    hot = free_running_widen(heat_op=20.0, cool_op=23.0, room=21.0, t_rm=34.0)
    assert hot.active is False
    cold = free_running_widen(heat_op=20.0, cool_op=23.0, room=21.0, t_rm=5.0)
    assert cold.active is False
