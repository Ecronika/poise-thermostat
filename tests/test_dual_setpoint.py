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


def test_unoccupied_setback_is_not_clamped_to_comfort_band() -> None:
    # review V3: a night/away setback (comfort_base lowered to 18) must survive.
    # Occupied: the EN Cat II lower (20) is enforced. Unoccupied: it is waived so
    # the setback is honoured instead of being silently clamped back up to 20.
    occupied = decide(t_rm=4.0, room=18.0, comfort_base=18.0, can_heat=True, t_out=4.0)
    setback = decide(
        t_rm=4.0,
        room=18.0,
        comfort_base=18.0,
        can_heat=True,
        t_out=4.0,
        occupied=False,
    )
    assert occupied.heat_sp == 20.0  # occupied: comfort band enforced
    assert setback.heat_sp == 18.0  # unoccupied: setback honoured, not clamped up


def test_unoccupied_setback_still_frost_protected() -> None:
    # a deep setback below the frost floor is still clamped up to the floor.
    d = decide(
        t_rm=2.0,
        room=6.0,
        comfort_base=5.0,
        can_heat=True,
        t_out=2.0,
        occupied=False,
    )
    assert d.heat_sp == 7.0  # frost floor holds even when unoccupied


def test_unoccupied_setback_still_mould_protected() -> None:
    # the mould floor is re-applied air-side, so it survives the relaxed clamp.
    d = decide(
        t_rm=2.0,
        room=12.0,
        comfort_base=10.0,
        can_heat=True,
        t_out=2.0,
        mold_min=16.0,
        occupied=False,
    )
    assert d.heat_sp == 16.0  # mould floor holds even when unoccupied


def test_adaptive_cool_lifts_summer_cooling_edge() -> None:
    """Büro-Technik over-cooling fix: warm running mean + cool-capable device.
    Without the adaptive edge the cool setpoint sits at the fixed Cat-I summer
    floor (23) and a mild-warm room is cooled; with it the edge lifts toward the
    EN adaptive upper (capped at ASR 26), so the room is within comfort -> idle."""
    fixed = decide(
        t_rm=21.0,
        room=24.5,
        category=Category.I,
        comfort_base=21.0,
        can_heat=False,
        can_cool=True,
        t_out=24.0,
    )
    adaptive = decide(
        t_rm=21.0,
        room=24.5,
        category=Category.I,
        comfort_base=21.0,
        can_heat=False,
        can_cool=True,
        t_out=24.0,
        adaptive_cool=True,
    )
    assert fixed.mode == "cool"  # fixed band over-cools the mild-warm room
    assert fixed.cool_sp == 23.0
    assert adaptive.cool_sp == 26.0  # lifted to the ASR-capped adaptive upper
    assert adaptive.mode == "idle"  # room is inside the adaptive band -> no cooling
