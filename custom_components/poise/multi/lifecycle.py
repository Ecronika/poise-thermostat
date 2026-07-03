"""Per-device lifecycle: anti-short-cycle, health, override + wall-clock
persistence (ADR-0046 §8/§9, Phase 2).

Pure + HA-free. Tracks each device's observed on/off transitions and mode changes
on a **wall-clock** basis (never monotonic — ADR-0006/0007 — so it survives a HA
restart) and derives the resolver's :class:`DeviceRuntime` (min-off / mode-hold /
health / external-override gates). P2 is still shadow: this gates nothing live
yet; it makes the seam observable and restart-safe for the P3 opt-in.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .model import (
    DEFAULT_MIN_MODE_HOLD_S,
    DEFAULT_MIN_OFF_S,
    DEFAULT_MIN_ON_S,
    DeviceHealth,
    ZoneDevice,
)
from .resolvers import DeviceRuntime

_STARTS_WINDOW_S = 3600.0
# A restored timestamp this far in the future (vs now) means the system clock
# jumped backwards; clamp it to ``now`` so a lock stays engaged rather than
# reading as long-elapsed and allowing an immediate compressor start.
_CLOCK_SKEW_TOLERANCE_S = 120.0


@dataclass(frozen=True, slots=True)
class LifecyclePolicy:
    """Per-device anti-short-cycle limits (ADR-0046 §8)."""

    min_on_s: float = DEFAULT_MIN_ON_S
    min_off_s: float = DEFAULT_MIN_OFF_S
    min_mode_hold_s: float = DEFAULT_MIN_MODE_HOLD_S
    max_starts_per_h: int | None = None


def policy_for(dev: ZoneDevice) -> LifecyclePolicy:
    """Read the per-device limits already carried on the :class:`ZoneDevice`
    (single source of truth — the device config, not a second literal).
    """
    return LifecyclePolicy(
        min_on_s=dev.min_on_s,
        min_off_s=dev.min_off_s,
        min_mode_hold_s=dev.min_mode_hold_s,
        max_starts_per_h=dev.max_starts_per_h,
    )


@dataclass(frozen=True, slots=True)
class DeviceLifecycle:
    """Wall-clock lifecycle state for one device; persisted across restarts."""

    is_on: bool = False
    last_on_wall: float | None = None
    last_off_wall: float | None = None
    last_mode: str | None = None
    mode_changed_wall: float | None = None
    starts_window: tuple[float, ...] = ()
    expected_echo: Mapping[str, Any] = field(default_factory=dict)
    health: str = DeviceHealth.OK.value


def _prune(starts: tuple[float, ...], now: float) -> tuple[float, ...]:
    return tuple(t for t in starts if now - t <= _STARTS_WINDOW_S)


def _clamp_future(t: float, now: float) -> float:
    return now if t > now + _CLOCK_SKEW_TOLERANCE_S else t


def observe(
    state: DeviceLifecycle,
    *,
    conditioning: bool,
    mode: str | None,
    now: float,
    health: str = DeviceHealth.OK.value,
) -> DeviceLifecycle:
    """Fold one fresh device observation (this tick) into the lifecycle."""
    last_on = state.last_on_wall
    last_off = state.last_off_wall
    starts = state.starts_window
    if conditioning and not state.is_on:  # off -> on (a start)
        last_on = now
        starts = (*_prune(starts, now), now)
    elif not conditioning and state.is_on:  # on -> off (a stop)
        last_off = now
    mode_changed = state.mode_changed_wall
    last_mode = state.last_mode
    if mode is not None and mode != state.last_mode:
        mode_changed = now
        last_mode = mode
    return DeviceLifecycle(
        is_on=conditioning,
        last_on_wall=last_on,
        last_off_wall=last_off,
        last_mode=last_mode,
        mode_changed_wall=mode_changed,
        starts_window=_prune(starts, now),
        expected_echo=state.expected_echo,
        health=health,
    )


def min_off_remaining(
    state: DeviceLifecycle, now: float, policy: LifecyclePolicy
) -> float:
    """Seconds the device must stay off before a fresh start is allowed."""
    if state.is_on or state.last_off_wall is None:
        return 0.0
    return max(0.0, policy.min_off_s - (now - state.last_off_wall))


def min_on_remaining(
    state: DeviceLifecycle, now: float, policy: LifecyclePolicy
) -> float:
    """Seconds the device must stay on before a stop is allowed."""
    if not state.is_on or state.last_on_wall is None:
        return 0.0
    return max(0.0, policy.min_on_s - (now - state.last_on_wall))


def mode_hold_remaining(
    state: DeviceLifecycle, now: float, policy: LifecyclePolicy
) -> float:
    """Seconds before a heat<->cool mode change is allowed again."""
    if state.mode_changed_wall is None:
        return 0.0
    return max(0.0, policy.min_mode_hold_s - (now - state.mode_changed_wall))


def starts_in_last_hour(state: DeviceLifecycle, now: float) -> int:
    return len(_prune(state.starts_window, now))


def _max_starts_blocked(
    state: DeviceLifecycle, now: float, policy: LifecyclePolicy
) -> bool:
    cap = policy.max_starts_per_h
    return cap is not None and starts_in_last_hour(state, now) >= cap


def to_runtime(
    state: DeviceLifecycle,
    now: float,
    policy: LifecyclePolicy,
    *,
    observed_echo: Mapping[str, Any] | None = None,
) -> DeviceRuntime:
    """Derive the resolver's gate state from the lifecycle (ADR-0046 §4/§8)."""
    cycle_blocked = min_off_remaining(state, now, policy) > 0.0 or _max_starts_blocked(
        state, now, policy
    )
    override = (
        is_external_override(state, observed_echo)
        if observed_echo is not None
        else False
    )
    return DeviceRuntime(
        health=DeviceHealth(state.health),
        min_off_active=cycle_blocked,
        mode_hold_active=mode_hold_remaining(state, now, policy) > 0.0,
        external_override=override,
    )


def is_external_override(
    state: DeviceLifecycle, observed_echo: Mapping[str, Any]
) -> bool:
    """True if the device's observed state diverges from our last command's echo
    (someone else changed it). No prior command (empty echo) -> not an override
    (ADR-0046 §9; dormant until P3 actually writes).
    """
    if not state.expected_echo:
        return False
    return any(observed_echo.get(k) != v for k, v in state.expected_echo.items())


def to_dict(state: DeviceLifecycle) -> dict[str, Any]:
    return {
        "is_on": state.is_on,
        "last_on_wall": state.last_on_wall,
        "last_off_wall": state.last_off_wall,
        "last_mode": state.last_mode,
        "mode_changed_wall": state.mode_changed_wall,
        "starts_window": list(state.starts_window),
        "expected_echo": dict(state.expected_echo),
        "health": state.health,
    }


def from_dict(d: Mapping[str, Any], *, now: float) -> DeviceLifecycle:
    """Restore on startup with a conservative wall-clock policy: a future
    timestamp (clock jumped) is clamped to ``now`` so a min-off/mode-hold lock
    stays engaged instead of reading as long-elapsed (ADR-0046 §8).
    """

    def _ts(key: str) -> float | None:
        v = d.get(key)
        return None if v is None else _clamp_future(float(v), now)

    raw_starts = d.get("starts_window") or []
    starts = tuple(_clamp_future(float(t), now) for t in raw_starts)
    return DeviceLifecycle(
        is_on=bool(d.get("is_on", False)),
        last_on_wall=_ts("last_on_wall"),
        last_off_wall=_ts("last_off_wall"),
        last_mode=d.get("last_mode"),
        mode_changed_wall=_ts("mode_changed_wall"),
        starts_window=_prune(starts, now),
        expected_echo=dict(d.get("expected_echo") or {}),
        health=str(d.get("health", DeviceHealth.OK.value)),
    )


_CONDITIONING_MODES = ("cool", "dry")
_ACTIVE_ACTIONS = ("cooling", "drying", "heating")


def compressor_conditioning(mode: str | None) -> bool:
    """True if the hvac_mode runs the compressor for cooling/drying (cool|dry)."""
    return mode in _CONDITIONING_MODES


def compressor_running(hvac_action: str | None, intended_mode: str | None) -> bool:
    """Whether the compressor is (intended to be) running: prefer the device's
    real ``hvac_action``; fall back to Poise's intended mode when the device
    reports none (mirrors the EKF cool-drive fallback for silent ACs, ADR-0024).
    """
    if hvac_action is not None:
        return hvac_action in _ACTIVE_ACTIONS
    return intended_mode in ("cool", "dry", "heat")


def mode_nudge_block_reason(
    *,
    desired: str,
    current: str | None,
    min_off_remaining_s: float,
    mode_hold_remaining_s: float,
    is_safety: bool,
) -> str | None:
    """Anti-short-cycle gate for a single-AC hvac_mode nudge (ADR-0046 §8).

    Returns a suppression reason when the nudge should be held back to protect
    the compressor, else ``None``. It only ever blocks *starting* the compressor
    (entering cool/dry) or *flipping* between the two conditioning modes; it
    never forces continued running (no min-on) and never blocks a safety action
    or a stop (``want`` False).
    """
    if is_safety:
        return None
    want = compressor_conditioning(desired)
    have = compressor_conditioning(current)
    if want and not have and min_off_remaining_s > 0.0:
        return f"min-off {min_off_remaining_s:.0f}s"
    if want and have and desired != current and mode_hold_remaining_s > 0.0:
        return f"mode-hold {mode_hold_remaining_s:.0f}s"
    return None
