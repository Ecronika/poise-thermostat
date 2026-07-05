"""Regression net for the ADR-0058 direction-neutral Eco relaxation in decide()."""

from __future__ import annotations

from custom_components.poise.comfort.dual_setpoint import decide
from custom_components.poise.comfort.en16798 import Category


def _d(**kw):
    base = dict(
        t_rm=25.0,
        room=30.0,
        t_out=30.0,
        category=Category.II,
        comfort_base=24.0,
        can_heat=False,
        can_cool=True,
        climate_mode="cool",
    )
    return decide(**{**base, **kw})


def test_away_relaxes_cooling_above_comfort() -> None:
    # the v0.149 bug: away cooled at/below comfort. With eco_widen + a device-max
    # ceiling, an empty house must cool LESS, not more.
    comfort = _d(occupied=True).cool_sp
    away = _d(occupied=False, eco_widen=6.0, cool_ceiling_override=32.0).cool_sp
    assert away > comfort


def test_eco_widen_zero_is_backward_compatible() -> None:
    # eco_widen default + no ceiling override == an explicit no-op (v0.149 behaviour)
    d1 = _d()
    d2 = _d(eco_widen=0.0, cool_ceiling_override=None)
    assert (d1.heat_sp, d1.cool_sp, d1.mode) == (d2.heat_sp, d2.cool_sp, d2.mode)


def test_eco_widen_is_symmetric() -> None:
    # widens BOTH edges: heat down and cool up vs the no-eco baseline
    base = _d(occupied=False, cool_ceiling_override=32.0)
    eco = _d(occupied=False, eco_widen=3.0, cool_ceiling_override=32.0)
    assert eco.cool_sp > base.cool_sp
    assert eco.heat_sp < base.heat_sp


def test_cool_ceiling_staging_room_eco_vs_away() -> None:
    # ROOM_ECO caps at cool_hard_cap (26); AWAY (device_max) relaxes further
    room_eco = _d(occupied=False, eco_widen=6.0, cool_ceiling_override=26.0).cool_sp
    away = _d(occupied=False, eco_widen=6.0, cool_ceiling_override=32.0).cool_sp
    assert away > room_eco


def test_dewpoint_floor_survives_the_change() -> None:
    # a low band still floors cool_sp at dewpoint + 2 (condensation guard intact)
    d = _d(comfort_base=20.0, dewpoint=24.0)
    assert d.cool_sp >= 26.0
