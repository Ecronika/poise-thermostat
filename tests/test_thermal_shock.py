"""ADR-0051 heat-day cooling band — adaptive cool setpoint (pure)."""

from __future__ import annotations

from custom_components.poise.comfort.thermal_shock import adaptive_cool_setpoint


def test_mild_day_no_raise() -> None:
    r = adaptive_cool_setpoint(cool_sp_en=26.0, t_out_smooth=24.0, t_rm=18.0)
    assert r.cool_sp_eff == 26.0
    assert r.raised is False


def test_office_cap_holds_on_hot_day() -> None:
    # default hard_cap 26 binds -> setpoint stays 26 even at 41 °C outdoor
    r = adaptive_cool_setpoint(cool_sp_en=26.0, t_out_smooth=41.0, t_rm=28.0)
    assert r.cool_sp_eff == 26.0
    assert r.raised is False
    assert "capped" in r.reason


def test_opt_in_float_raises_under_en_upper() -> None:
    # hard_cap 30 (employer opt-in): rises toward outdoor-7, clamped <= EN upper
    r = adaptive_cool_setpoint(
        cool_sp_en=26.0, t_out_smooth=35.0, t_rm=24.0, hard_cap=30.0
    )
    # shock floor 35-7=28; EN upper(24,II)=29.72; cap=min(30,30,29.72)
    assert r.raised is True
    assert abs(r.cool_sp_eff - 28.0) < 0.05
    assert r.cool_sp_eff <= r.upper_clamp + 1e-9


def test_en_upper_is_the_binding_clamp() -> None:
    # generous device + cap, but the EN adaptive upper limits the raise
    r = adaptive_cool_setpoint(
        cool_sp_en=26.0,
        t_out_smooth=41.0,
        t_rm=20.0,
        device_max=40.0,
        hard_cap=40.0,
    )
    # EN upper(20,II)=0.33*20+18.8+3=28.4 -> eff clamped to 28.4
    assert abs(r.cool_sp_eff - 28.4) < 0.05
    assert abs(r.en_upper - 28.4) < 0.05
    assert r.raised is True


def test_delta_zero_disables() -> None:
    r = adaptive_cool_setpoint(
        cool_sp_en=26.0, t_out_smooth=41.0, t_rm=28.0, hard_cap=40.0, delta_k=0.0
    )
    assert r.cool_sp_eff == 26.0
    assert r.raised is False
    assert r.reason == "off"


def test_never_below_en_setpoint() -> None:
    # very low outdoor -> shock floor far below; eff stays at cool_sp_en
    r = adaptive_cool_setpoint(
        cool_sp_en=27.0, t_out_smooth=10.0, t_rm=12.0, hard_cap=40.0
    )
    assert r.cool_sp_eff == 27.0
    assert r.raised is False
