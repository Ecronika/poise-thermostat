from __future__ import annotations

from custom_components.poise.multi.lifecycle import (
    DeviceLifecycle,
    LifecyclePolicy,
    compressor_conditioning,
    compressor_running,
    from_dict,
    is_external_override,
    min_off_remaining,
    min_on_remaining,
    mode_hold_remaining,
    mode_nudge_block_reason,
    observe,
    policy_for,
    starts_in_last_hour,
    to_dict,
    to_runtime,
)
from custom_components.poise.multi.model import (
    Axis,
    DeviceCapability,
    DeviceHealth,
    Direction,
    ZoneDevice,
)

_POL = LifecyclePolicy(min_on_s=120.0, min_off_s=600.0, min_mode_hold_s=300.0)


def _ac(**kw: object) -> ZoneDevice:
    return ZoneDevice(
        entity_id="climate.ac",
        adapter="ClimateAdapter",
        capabilities=(
            DeviceCapability(Axis.THERMAL, Direction.COOL, mode_command="cool"),
        ),
        **kw,  # type: ignore[arg-type]
    )


# --- observe / transitions -------------------------------------------------


def test_observe_start_then_stop() -> None:
    on = observe(DeviceLifecycle(), conditioning=True, mode="heat", now=1000.0)
    assert on.is_on and on.last_on_wall == 1000.0
    assert on.starts_window == (1000.0,)
    assert on.last_mode == "heat" and on.mode_changed_wall == 1000.0

    off = observe(on, conditioning=False, mode="heat", now=1100.0)
    assert not off.is_on and off.last_off_wall == 1100.0
    assert off.last_on_wall == 1000.0  # preserved
    assert off.mode_changed_wall == 1000.0  # mode unchanged -> not bumped


def test_mode_change_bumps_hold() -> None:
    s = observe(
        DeviceLifecycle(last_mode="heat"), conditioning=True, mode="cool", now=50.0
    )
    assert s.last_mode == "cool" and s.mode_changed_wall == 50.0


# --- timers ----------------------------------------------------------------


def test_min_off_counts_down_then_clears() -> None:
    s = DeviceLifecycle(is_on=False, last_off_wall=1100.0)
    assert min_off_remaining(s, 1300.0, _POL) == 400.0
    assert min_off_remaining(s, 1800.0, _POL) == 0.0


def test_min_off_zero_while_running() -> None:
    s = DeviceLifecycle(is_on=True, last_on_wall=1000.0, last_off_wall=900.0)
    assert min_off_remaining(s, 1200.0, _POL) == 0.0


def test_min_on_counts_down() -> None:
    s = DeviceLifecycle(is_on=True, last_on_wall=1000.0)
    assert min_on_remaining(s, 1050.0, _POL) == 70.0
    assert min_on_remaining(s, 1200.0, _POL) == 0.0


def test_mode_hold_counts_down() -> None:
    s = DeviceLifecycle(mode_changed_wall=1000.0)
    assert mode_hold_remaining(s, 1100.0, _POL) == 200.0
    assert mode_hold_remaining(s, 1400.0, _POL) == 0.0


def test_starts_window_prunes_past_hour() -> None:
    s = DeviceLifecycle(starts_window=(0.0, 100.0, 3700.0))
    assert starts_in_last_hour(s, 3700.0) == 2  # the 0.0 start is >3600 s back
    assert starts_in_last_hour(s, 8000.0) == 0  # all older than 3600 s


# --- to_runtime ------------------------------------------------------------


def test_runtime_idle_is_all_clear() -> None:
    rt = to_runtime(DeviceLifecycle(), 1000.0, _POL)
    assert rt.health is DeviceHealth.OK
    assert not (rt.min_off_active or rt.mode_hold_active or rt.external_override)


def test_runtime_min_off_blocks() -> None:
    s = DeviceLifecycle(is_on=False, last_off_wall=1100.0)
    assert to_runtime(s, 1300.0, _POL).min_off_active is True


def test_runtime_max_starts_blocks() -> None:
    pol = LifecyclePolicy(min_off_s=0.0, max_starts_per_h=3)
    s = DeviceLifecycle(
        is_on=False, last_off_wall=1200.0, starts_window=(1000.0, 1100.0, 1200.0)
    )
    assert to_runtime(s, 1300.0, pol).min_off_active is True


def test_runtime_health_propagates() -> None:
    s = DeviceLifecycle(health=DeviceHealth.UNAVAILABLE.value)
    assert to_runtime(s, 1000.0, _POL).health is DeviceHealth.UNAVAILABLE


# --- external override (dormant until P3 writes) ---------------------------


def test_override_false_without_prior_command() -> None:
    assert is_external_override(DeviceLifecycle(), {"hvac_mode": "cool"}) is False


def test_override_false_when_echo_matches() -> None:
    s = DeviceLifecycle(expected_echo={"hvac_mode": "heat"})
    assert is_external_override(s, {"hvac_mode": "heat"}) is False


def test_override_true_when_state_diverges() -> None:
    s = DeviceLifecycle(expected_echo={"hvac_mode": "heat"})
    assert is_external_override(s, {"hvac_mode": "cool"}) is True


# --- persistence (wall-clock, restart) -------------------------------------


def test_roundtrip_preserves_state() -> None:
    s = DeviceLifecycle(
        is_on=True,
        last_on_wall=1000.0,
        last_off_wall=900.0,
        last_mode="cool",
        mode_changed_wall=1000.0,
        starts_window=(1000.0,),
        expected_echo={"hvac_mode": "cool"},
        health=DeviceHealth.OK.value,
    )
    r = from_dict(to_dict(s), now=1200.0)
    assert r == s


def test_restore_keeps_remaining_lock_from_wall_clock() -> None:
    # stopped 300 s before restart -> 300 s of a 600 s min-off still owed
    r = from_dict({"last_off_wall": 700.0}, now=1000.0)
    assert min_off_remaining(r, 1000.0, _POL) == 300.0


def test_restore_clamps_future_timestamp_conservatively() -> None:
    # a stop "in the future" (clock jumped) -> clamp to now -> full min-off owed
    r = from_dict({"last_off_wall": 99999.0}, now=1000.0)
    assert r.last_off_wall == 1000.0
    assert min_off_remaining(r, 1000.0, _POL) == 600.0


def test_restore_prunes_stale_starts() -> None:
    r = from_dict({"starts_window": [0.0, 100.0, 5000.0]}, now=5000.0)
    assert r.starts_window == (5000.0,)


# --- per-device policy -----------------------------------------------------


def test_policy_for_reads_device_limits() -> None:
    dev = _ac(min_on_s=99.0, min_off_s=888.0, min_mode_hold_s=77.0, max_starts_per_h=4)
    pol = policy_for(dev)
    assert pol.min_on_s == 99.0
    assert pol.min_off_s == 888.0
    assert pol.min_mode_hold_s == 77.0
    assert pol.max_starts_per_h == 4


# --- compressor protection gate (ADR-0046 §8, single-AC dry nudge) ----------


def test_compressor_conditioning_only_cool_and_dry() -> None:
    assert compressor_conditioning("cool") is True
    assert compressor_conditioning("dry") is True
    assert compressor_conditioning("heat") is False
    assert compressor_conditioning("fan_only") is False
    assert compressor_conditioning("off") is False
    assert compressor_conditioning(None) is False


def test_compressor_running_prefers_action_else_intent() -> None:
    assert compressor_running("cooling", "idle") is True
    assert compressor_running("drying", None) is True
    # a device that reports its action wins over intent
    assert compressor_running("idle", "cool") is False
    # a silent AC (no hvac_action) falls back to Poise's intended mode
    assert compressor_running(None, "cool") is True
    assert compressor_running(None, "dry") is True
    assert compressor_running(None, "idle") is False
    assert compressor_running(None, None) is False


def test_gate_blocks_compressor_start_within_min_off() -> None:
    r = mode_nudge_block_reason(
        desired="cool",
        current="off",
        min_off_remaining_s=120.0,
        mode_hold_remaining_s=0.0,
        is_safety=False,
    )
    assert r is not None and "min-off" in r


def test_gate_allows_start_when_min_off_elapsed() -> None:
    r = mode_nudge_block_reason(
        desired="dry",
        current="idle",
        min_off_remaining_s=0.0,
        mode_hold_remaining_s=0.0,
        is_safety=False,
    )
    assert r is None


def test_gate_blocks_cool_dry_flip_within_mode_hold() -> None:
    r = mode_nudge_block_reason(
        desired="dry",
        current="cool",
        min_off_remaining_s=0.0,
        mode_hold_remaining_s=200.0,
        is_safety=False,
    )
    assert r is not None and "mode-hold" in r


def test_gate_no_block_on_same_mode() -> None:
    r = mode_nudge_block_reason(
        desired="cool",
        current="cool",
        min_off_remaining_s=999.0,
        mode_hold_remaining_s=999.0,
        is_safety=False,
    )
    assert r is None


def test_gate_never_blocks_a_stop() -> None:
    # leaving cool -> idle must never be suppressed, even deep in a lock
    r = mode_nudge_block_reason(
        desired="idle",
        current="cool",
        min_off_remaining_s=999.0,
        mode_hold_remaining_s=999.0,
        is_safety=False,
    )
    assert r is None


def test_gate_safety_is_exempt() -> None:
    r = mode_nudge_block_reason(
        desired="cool",
        current="off",
        min_off_remaining_s=999.0,
        mode_hold_remaining_s=999.0,
        is_safety=True,
    )
    assert r is None


def test_gate_heat_start_is_not_a_cool_compressor_start() -> None:
    # entering heat is not a cool/dry start -> the cool-compressor gate is silent
    r = mode_nudge_block_reason(
        desired="heat",
        current="off",
        min_off_remaining_s=999.0,
        mode_hold_remaining_s=999.0,
        is_safety=False,
    )
    assert r is None
