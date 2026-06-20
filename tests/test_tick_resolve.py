from __future__ import annotations

from custom_components.poise.control.tick_resolve import (
    resolve_write_target,
    select_mrt,
    select_q_solar,
    select_t_rm,
)


def test_select_t_rm_precedence() -> None:
    assert select_t_rm(17.5, 20.0, 5.0) == (17.5, "sensor")
    assert select_t_rm(None, 20.0, 5.0) == (20.0, "internal")
    assert select_t_rm(None, None, 5.0) == (5.0, "outdoor")
    assert select_t_rm(None, None, None) == (None, None)


def test_select_q_solar_precedence() -> None:
    # measured irradiance overrides clear-sky
    used, src, internal = select_q_solar(30.0, 500.0)
    assert src == "sensor" and used == 0.5 and 0.0 < internal <= 1.0
    # no sensor -> internal clear-sky
    used, src, internal = select_q_solar(90.0, None)
    assert src == "internal" and used == internal == 1.0
    # night, no sensor
    assert select_q_solar(None, None) == (0.0, "none", 0.0)


def test_select_mrt() -> None:
    assert select_mrt(26.0, 25.0) == (26.0, "sensor")
    assert select_mrt(None, 25.0) == (25.0, "internal")


def test_write_target_comfort_path() -> None:
    wt = resolve_write_target(
        window_open=False,
        override=None,
        heat_sp=21.0,
        cool_sp=26.0,
        write_setpoint=21.0,
        comfort_mode="heat",
        frost_floor=7.0,
        mold_min=None,
        device_max=30.0,
    )
    assert wt.target == 21.0 and wt.mode == "heat" and wt.norm_binding is None


def test_write_target_window_uses_floor() -> None:
    wt = resolve_write_target(
        window_open=True,
        override=None,
        heat_sp=21.0,
        cool_sp=26.0,
        write_setpoint=21.0,
        comfort_mode="heat",
        frost_floor=7.0,
        mold_min=16.0,
        device_max=30.0,
    )
    assert wt.target == 16.0 and wt.mode == "off"  # mould floor


def test_write_target_override_clamped_into_band_and_norm() -> None:
    # override above cool band -> clamped to cool_sp
    wt = resolve_write_target(
        window_open=False,
        override=40.0,
        heat_sp=20.0,
        cool_sp=24.0,
        write_setpoint=20.0,
        comfort_mode="heat",
        frost_floor=7.0,
        mold_min=None,
        device_max=30.0,
    )
    assert wt.target == 24.0 and wt.mode == "manual"


def test_write_target_norm_cap_applies_when_heating() -> None:
    wt = resolve_write_target(
        window_open=False,
        override=None,
        heat_sp=28.0,
        cool_sp=29.0,
        write_setpoint=28.0,
        comfort_mode="heat",
        frost_floor=7.0,
        mold_min=None,
        device_max=30.0,
    )
    assert wt.target == 26.0 and wt.norm_binding == "norm_cap"  # ASR 26


def test_write_target_norm_skipped_when_cooling() -> None:
    wt = resolve_write_target(
        window_open=False,
        override=None,
        heat_sp=20.0,
        cool_sp=26.5,
        write_setpoint=26.5,
        comfort_mode="cool",
        frost_floor=7.0,
        mold_min=None,
        device_max=30.0,
    )
    assert wt.target == 26.5 and wt.norm_binding is None  # cooling not capped


def test_write_target_device_max() -> None:
    wt = resolve_write_target(
        window_open=False,
        override=None,
        heat_sp=22.0,
        cool_sp=28.0,
        write_setpoint=22.0,
        comfort_mode="cool",
        frost_floor=7.0,
        mold_min=None,
        device_max=21.0,
    )
    assert wt.target == 21.0  # device max clamps below
