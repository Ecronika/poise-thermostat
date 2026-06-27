from __future__ import annotations

from custom_components.poise.comfort.dual_setpoint import decide
from custom_components.poise.comfort.en16798 import Category


def test_live_case_warm_room_idles_instead_of_heating() -> None:
    # The v0.6.0 regression: T_rm 15.7, room 23.5, heat-only TRV -> must NOT
    # heat to 24; 23.5 is inside the dead-band -> idle, hold below the room.
    d = decide(
        t_rm=15.7,
        room=23.5,
        comfort_base=21.0,
        can_heat=True,
        can_cool=False,
        t_out=15.7,
    )
    assert d.mode == "idle"
    assert d.write_setpoint < 23.5  # heat_sp -> TRV idles, no wasted energy
    assert d.heat_sp <= 22.0  # not driven to ~24


def test_cold_room_heats_to_base() -> None:
    d = decide(t_rm=4.0, room=18.0, comfort_base=21.0, can_heat=True, t_out=4.0)
    assert d.mode == "heat"
    assert d.target is not None and 20.0 <= d.target <= 22.0


def test_cool_only_device_in_cold_stays_idle() -> None:
    # cool-only AC, room above heat_sp but cold outside -> must NOT cool, NOT heat
    d = decide(
        t_rm=8.0,
        room=22.0,
        can_heat=False,
        can_cool=True,
        t_out=8.0,
    )
    assert d.mode == "idle"
    assert d.write_setpoint > 22.0  # cool_sp -> AC idles below it


def test_hot_room_with_cooling_cools_to_cool_sp() -> None:
    d = decide(
        t_rm=26.0,
        room=29.0,
        can_heat=False,
        can_cool=True,
        t_out=29.0,
    )
    assert d.mode == "cool"
    # M1: cooling now tracks the comfort centre (base 21 + neutral band), no
    # longer pinned to the absolute category upper.
    assert d.target is not None and 22.0 <= d.target <= 24.0


def test_heat_only_device_in_heat_does_not_cool() -> None:
    d = decide(
        t_rm=26.0,
        room=29.0,
        can_heat=True,
        can_cool=False,
        t_out=29.0,
    )
    assert d.mode == "idle"  # too warm to heat, cannot cool
    assert d.write_setpoint < 29.0


def test_efficiency_priority_widens_dead_band() -> None:
    comfort = decide(t_rm=12.0, room=21.0, t_out=12.0, priority=1.0)
    efficiency = decide(t_rm=12.0, room=21.0, t_out=12.0, priority=0.0)
    comfort_band = comfort.cool_sp - comfort.heat_sp
    efficiency_band = efficiency.cool_sp - efficiency.heat_sp
    assert efficiency_band > comfort_band


def test_mold_floor_raises_heat_setpoint() -> None:
    d = decide(t_rm=4.0, room=18.0, can_heat=True, t_out=-5.0, mold_min=22.0)
    assert d.heat_sp >= 22.0


def test_dewpoint_caps_cooling_setpoint() -> None:
    d = decide(t_rm=27.0, room=29.0, can_cool=True, t_out=29.0, dewpoint=23.0)
    assert d.cool_sp >= 25.0  # not cooled below dewpoint + 2


def test_band_never_inverts() -> None:
    d = decide(t_rm=15.0, room=22.0, t_out=15.0, category=Category.I)
    assert d.cool_sp >= d.heat_sp


def test_cooling_tracks_comfort_base() -> None:
    # M1: a higher comfort centre raises the cooling setpoint (clamped by the
    # EN-16798 upper limit), instead of being pinned to that upper limit.
    lo = decide(t_rm=26.0, room=29.0, comfort_base=21.0, can_cool=True, t_out=29.0)
    hi = decide(t_rm=26.0, room=29.0, comfort_base=24.0, can_cool=True, t_out=29.0)
    assert hi.cool_sp > lo.cool_sp


def test_efficiency_widen_never_breaches_category_lower() -> None:
    # M2: full-efficiency widening must not push the heating setpoint below the
    # category comfort lower (Cat II = 20 °C); only frost/mould may go lower.
    d = decide(t_rm=4.0, room=18.0, comfort_base=20.0, t_out=4.0, priority=0.0)
    assert d.heat_sp >= 20.0


def test_configurable_cool_lockout_threads_through() -> None:
    # ADR-0047: the cool-lockout option reaches decide_mode. An internal-gain
    # room cools despite cool outside when the lockout is disabled (None)...
    hot = decide(
        t_rm=20.0,
        room=29.0,
        can_heat=False,
        can_cool=True,
        t_out=8.0,
        cool_min_outdoor=None,
    )
    assert hot.mode == "cool"
    # ...and the default 16 keeps the cold-outside lockout (regression).
    gated = decide(t_rm=20.0, room=29.0, can_heat=False, can_cool=True, t_out=8.0)
    assert gated.mode == "idle"
