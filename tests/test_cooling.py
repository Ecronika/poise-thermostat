from __future__ import annotations

from custom_components.poise.control.cooling import DualSetpoint, decide_mode

_SP = DualSetpoint(heat=21.0, cool=25.0)


def test_heats_when_cold_inside_and_not_mild_outside() -> None:
    assert decide_mode(19.0, _SP, outdoor=5.0) == "heat"


def test_cools_when_warm_inside_and_warm_outside() -> None:
    assert decide_mode(27.0, _SP, outdoor=28.0) == "cool"


def test_deadband_between_setpoints_is_idle() -> None:
    assert decide_mode(23.0, _SP, outdoor=18.0) == "idle"


def test_outdoor_lockouts() -> None:
    # too mild to heat
    assert decide_mode(19.0, _SP, outdoor=25.0) == "idle"
    # too cold to cool
    assert decide_mode(27.0, _SP, outdoor=10.0) == "idle"


def test_mode_restrictions() -> None:
    assert decide_mode(27.0, _SP, outdoor=28.0, climate_mode="heat_only") == "idle"
    assert decide_mode(19.0, _SP, outdoor=5.0, climate_mode="cool_only") == "idle"


def test_inverted_band_does_not_silently_heat() -> None:
    # M6: a contradictory band (heat target above cool target) must idle, not heat.
    bad = DualSetpoint(heat=25.0, cool=21.0)
    assert decide_mode(23.0, bad, outdoor=20.0) == "idle"


def test_configurable_cool_lockout() -> None:
    # ADR-0047: the cool lockout is configurable per zone.
    # default 16: too cold outside to cool
    assert decide_mode(27.0, _SP, outdoor=10.0) == "idle"
    # lowered floor: an internal-gain room cools at 10 °C outside
    assert decide_mode(27.0, _SP, outdoor=10.0, cool_min_outdoor=5.0) == "cool"
    # disabled (None): cools regardless of outside temperature
    assert decide_mode(27.0, _SP, outdoor=-5.0, cool_min_outdoor=None) == "cool"


def test_configurable_lockout_is_direction_separated() -> None:
    # default 22: too mild outside to heat
    assert decide_mode(19.0, _SP, outdoor=25.0) == "idle"
    # raised heat ceiling: heats at 25 °C outside
    assert decide_mode(19.0, _SP, outdoor=25.0, heat_max_outdoor=30.0) == "heat"
    # disabling the COOL lockout must not enable heating (direction-separated)
    assert decide_mode(19.0, _SP, outdoor=25.0, cool_min_outdoor=None) == "idle"


def test_heat_lockout_above_configured_ceiling_idles() -> None:
    # F12.4: heating is locked out above the configured outdoor ceiling. With the
    # ceiling at 0 °C, a cold room at 5 °C outside cannot heat -> idle.
    assert decide_mode(19.0, _SP, outdoor=5.0, heat_max_outdoor=0.0) == "idle"
    # disabling the ceiling (None) re-enables heating at the same conditions.
    assert decide_mode(19.0, _SP, outdoor=5.0, heat_max_outdoor=None) == "heat"


def test_locked_out_cold_reversible_still_parks_heat_at_frost_floor() -> None:
    # F12.4: even when the outdoor gate locks heating out (decide_mode -> idle), a
    # cold reversible device idle-parks toward heat at >= the frost floor, so a
    # further drop is still caught rather than left to free-fall.
    from custom_components.poise.const import FROST_FLOOR_C
    from custom_components.poise.control.tick_resolve import idle_park

    sp = DualSetpoint(heat=17.5, cool=26.7)
    assert decide_mode(16.0, sp, outdoor=25.0, heat_max_outdoor=22.0) == "idle"
    mode, target = idle_park(
        room=16.0, heat_sp=17.5, cool_sp=26.7, can_heat=True, can_cool=True
    )
    assert mode == "heat" and target >= FROST_FLOOR_C
