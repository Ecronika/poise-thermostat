"""ADR-0023 §1 free-running adaptive band widening (pure)."""

from __future__ import annotations

from custom_components.poise.comfort.en16798 import Category
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


def test_adaptive_cool_edge_raises_in_warm_free_running() -> None:
    from custom_components.poise.comfort.free_running import adaptive_cool_edge

    # Cat I, T_rm 21 -> adaptive upper 0.33*21+18.8+2 = 27.7; cap 26 -> edge 26 > 23
    edge, raised = adaptive_cool_edge(
        fixed_cool_op=23.0,
        t_rm=21.0,
        category=Category.I,
        cap=26.0,
        enabled=True,
        can_cool=True,
    )
    assert raised is True
    assert edge == 26.0


def test_adaptive_cool_edge_capped_at_asr_no_oversuppression() -> None:
    from custom_components.poise.comfort.free_running import adaptive_cool_edge

    # very warm T_rm 30 -> adaptive upper ~31.7 -> capped at the ASR ceiling 26
    edge, raised = adaptive_cool_edge(
        fixed_cool_op=23.0,
        t_rm=30.0,
        category=Category.II,
        cap=26.0,
        enabled=True,
        can_cool=True,
    )
    assert edge == 26.0
    assert raised is True


def test_adaptive_cool_edge_disabled_is_noop() -> None:
    from custom_components.poise.comfort.free_running import adaptive_cool_edge

    edge, raised = adaptive_cool_edge(
        fixed_cool_op=23.0,
        t_rm=21.0,
        category=Category.I,
        cap=26.0,
        enabled=False,
        can_cool=True,
    )
    assert edge == 23.0
    assert raised is False


def test_adaptive_cool_edge_needs_cooling_capability() -> None:
    from custom_components.poise.comfort.free_running import adaptive_cool_edge

    _, raised = adaptive_cool_edge(
        fixed_cool_op=23.0,
        t_rm=21.0,
        category=Category.I,
        cap=26.0,
        enabled=True,
        can_cool=False,
    )
    assert raised is False


def test_adaptive_cool_edge_extrapolated_keeps_fixed() -> None:
    from custom_components.poise.comfort.free_running import adaptive_cool_edge

    # T_rm 5 is outside the [10, 30] validity range -> keep the fixed edge
    edge, raised = adaptive_cool_edge(
        fixed_cool_op=23.0,
        t_rm=5.0,
        category=Category.II,
        cap=26.0,
        enabled=True,
        can_cool=True,
    )
    assert edge == 23.0
    assert raised is False


def test_adaptive_cool_edge_never_lowers_below_fixed() -> None:
    from custom_components.poise.comfort.free_running import adaptive_cool_edge

    # a mis-set low cap (22) must never pull the edge below the design band (23)
    edge, raised = adaptive_cool_edge(
        fixed_cool_op=23.0,
        t_rm=21.0,
        category=Category.I,
        cap=22.0,
        enabled=True,
        can_cool=True,
    )
    assert edge == 23.0
    assert raised is False
