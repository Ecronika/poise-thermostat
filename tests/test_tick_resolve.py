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


# --- write throttle (ADR-0012, review P1.2) ---

from custom_components.poise.control.tick_resolve import should_write  # noqa: E402


def test_should_write_first_time() -> None:
    assert should_write(None, 21.0, mode_changed=False, deadband=0.2) is True


def test_should_write_on_mode_change() -> None:
    assert should_write(21.0, 21.0, mode_changed=True, deadband=0.2) is True


def test_should_write_on_significant_change() -> None:
    assert should_write(21.0, 21.2, mode_changed=False, deadband=0.2) is True


def test_skip_write_on_tiny_change() -> None:
    assert should_write(21.0, 21.1, mode_changed=False, deadband=0.2) is False
    assert should_write(21.0, 21.0, mode_changed=False, deadband=0.2) is False


def test_reasserts_when_actuator_changed_externally() -> None:
    # actuator was reset to 5 °C by an external automation; target still 22.6
    # -> Poise must re-write (regression guard, live finding 2026-06-21)
    assert should_write(5.0, 22.6, mode_changed=False, deadband=0.2) is True


def test_skips_when_actuator_already_at_target() -> None:
    assert should_write(22.6, 22.6, mode_changed=False, deadband=0.2) is False


def test_writes_when_actuator_setpoint_unknown() -> None:
    assert should_write(None, 22.6, mode_changed=False, deadband=0.2) is True


def test_snap_to_step_coarse_device() -> None:
    from custom_components.poise.control.tick_resolve import snap_to_step

    assert snap_to_step(21.3, 0.5) == 21.5  # coarse TRV rounds up
    assert snap_to_step(21.1, 0.5) == 21.0
    assert snap_to_step(21.3, 0.1) == 21.3  # fine device unchanged
    assert snap_to_step(21.3, 0.0) == 21.3  # guard: no step -> passthrough


def test_throttle_no_rewrite_loop_on_coarse_trv() -> None:
    from custom_components.poise.control.tick_resolve import should_write, snap_to_step

    # Poise wants 21.3, a 0.5-step TRV echoes 21.5; snapped compare must NOT rewrite
    snapped = snap_to_step(21.3, 0.5)  # 21.5
    assert should_write(21.5, snapped, mode_changed=False, deadband=0.2) is False


def test_heat_drive_uses_actuator_running_state() -> None:
    from custom_components.poise.control.tick_resolve import heat_drive_signal

    assert heat_drive_signal("heating", fallback_heating=False) == 1.0  # real heat
    assert heat_drive_signal("idle", fallback_heating=True) == 0.0  # valve idle wins
    assert heat_drive_signal("off", fallback_heating=True) == 0.0


def test_heat_drive_falls_back_without_action() -> None:
    from custom_components.poise.control.tick_resolve import heat_drive_signal

    assert heat_drive_signal(None, fallback_heating=True) == 1.0
    assert heat_drive_signal("", fallback_heating=False) == 0.0


def test_needs_mode_nudge_on_drift() -> None:
    from custom_components.poise.control.tick_resolve import needs_mode_nudge

    # nudge away from the device's own auto/off into the mode that matches our write
    assert needs_mode_nudge("auto", "heat", supported=True) is True
    assert needs_mode_nudge("off", "heat", supported=True) is True
    assert needs_mode_nudge("off", "cool", supported=True) is True  # H1: cool too
    assert needs_mode_nudge("heat", "heat", supported=True) is False  # already correct
    assert needs_mode_nudge("cool", "cool", supported=True) is False  # already correct
    # H1 residual: a device autonomously in the OPPOSITE active mode is corrected
    assert needs_mode_nudge("heat", "cool", supported=True) is True  # heat→cool switch
    assert needs_mode_nudge("cool", "heat", supported=True) is True  # cool→heat switch
    # V1 regression: an auto/off-only TRV (no real "heat" mode) must NOT be nudged
    assert needs_mode_nudge("auto", "cool", supported=False) is False
    assert needs_mode_nudge("off", "heat", supported=False) is False
    assert needs_mode_nudge("heat", "cool", supported=False) is False
    # ADR-0050 S2c: a special mode (dry) is asserted when absent AND left when
    # no longer wanted; a stuck dry keeps dehumidifying.
    assert needs_mode_nudge("cool", "dry", supported=True) is True  # cool -> dry
    assert needs_mode_nudge("heat", "dry", supported=True) is True  # heat -> dry
    assert needs_mode_nudge("dry", "dry", supported=True) is False  # already drying
    assert needs_mode_nudge("dry", "heat", supported=True) is True  # leave dry
    assert needs_mode_nudge("dry", "cool", supported=True) is True  # leave dry
    assert needs_mode_nudge("cool", "dry", supported=False) is False  # unsupported
    assert needs_mode_nudge(None, "dry", supported=True) is False  # unknown → hold


def test_device_max_never_undercuts_health_floor() -> None:
    """M2: a misreported device max below the health floor must not defeat it."""
    wt = resolve_write_target(
        window_open=False,
        override=None,
        heat_sp=20.0,
        cool_sp=26.0,
        write_setpoint=5.0,
        comfort_mode="heat",
        frost_floor=7.0,
        mold_min=None,
        device_max=3.0,  # absurd / misreported, below the frost floor
    )
    # frost protection still wins — not clamped down to the bogus device max
    assert wt.target >= 7.0
    assert wt.norm_binding == "norm_floor"

    # the cooling path is unchanged: a real device max still caps the cool target
    cool = resolve_write_target(
        window_open=False,
        override=None,
        heat_sp=20.0,
        cool_sp=24.0,
        write_setpoint=24.0,
        comfort_mode="cool",
        frost_floor=7.0,
        mold_min=None,
        device_max=22.0,
    )
    assert cool.target <= 22.0
