"""Sensorless open-window detection by temperature slope (ADR-0041, shadow stage).

Most rooms have no contact sensor. The coordinator already computes the room
temperature rate dT/dt in degC/hour (for the seasonless-rate prior); this pure
helper turns that slope into an open/closed verdict with hysteresis, a minimum
number of points, an aberrant-slope sanity filter and a max-duration auto-reset
(shape verified against Versatile Thermostat's ``window_auto``). It never
actuates — the coordinator only reports ``window_auto_detected`` and the sensor
path, if configured, wins (degradation ladder, ADR-0012). Slopes are negative
while the room is cooling, so an open window shows a steep negative slope.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class WindowAutoConfig:
    """Thresholds for slope-based window detection (slopes in degC/hour)."""

    open_threshold: float = 3.0  # open when smoothed drop is steeper than this
    close_fraction: float = 0.2  # close once slope recovers to within this * open
    max_duration_min: float = 30.0  # force-close after this long open (anti-stick)
    min_points: int = 3  # no verdict before this many samples
    ema_old_weight: float = 0.2  # EMA: w*old + (1-w)*new (VTherm 0.2/0.8)
    max_slope: float = 120.0  # |slope| above this is an artefact, ignored
    open_factor: float = 1.8  # adaptive open threshold = factor * natural cooling
    open_threshold_min: float = 2.0  # floor for the adaptive open threshold (degC/h)
    open_threshold_max: float = 12.0  # cap for the adaptive open threshold (degC/h)
    min_step: float = 0.05  # a move below this (half a 0.1 K quantum) reads as flat


@dataclass(frozen=True, slots=True)
class WindowAutoState:
    """Detector state carried across ticks; pure (coordinator owns/persists it)."""

    ema_slope: float = 0.0
    n_points: int = 0
    open: bool = False
    minutes_open: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ema_slope": self.ema_slope,
            "n_points": self.n_points,
            "open": self.open,
            "minutes_open": self.minutes_open,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WindowAutoState:
        return cls(
            ema_slope=float(data.get("ema_slope", 0.0)),
            n_points=int(data.get("n_points", 0)),
            open=bool(data.get("open", False)),
            minutes_open=float(data.get("minutes_open", 0.0)),
        )


_DEFAULT_CONFIG = WindowAutoConfig()


def adaptive_open_threshold(
    tau_hours: float,
    t_room: float,
    t_out: float,
    cfg: WindowAutoConfig = _DEFAULT_CONFIG,
) -> float:
    """Open threshold (degC/h) scaled to the room's natural free-running cooling.

    A window cools a room far faster than its envelope loss, whose magnitude is
    ``(t_room - t_out) / tau``. The threshold sits a factor above that natural
    rate, so a well-insulated room (large tau, gentle loss) flags a gentler drop
    while a leaky room or a cold day needs a steeper one — fewer misses and
    fewer false positives than a fixed user threshold (VTherm). Falls back to
    the fixed ``cfg.open_threshold`` when tau is unknown (model not identified).
    """
    if tau_hours <= 0.0:
        return cfg.open_threshold
    natural = max(0.0, t_room - t_out) / tau_hours
    return min(
        cfg.open_threshold_max,
        max(cfg.open_threshold_min, cfg.open_factor * natural),
    )


def quantized_slope(
    *,
    room: float,
    ref_room: float | None,
    ref_s: float | None,
    now_s: float,
    min_step: float = 0.05,
) -> tuple[float | None, float, float]:
    """Room cooling rate (degC/h) robust to sensor quantization (review V6).

    A 0.1 K-quantized sensor steps once every few minutes while drifting; measuring
    dT/dt per coordinator tick reads that single 0.1 K step as a steep drop (0.1 K
    over ~60 s ≈ 6 degC/h) and would falsely open the window. Instead the slope is
    measured over the interval since the room last moved a full quantum: a slow
    natural drift (a 0.1 K step every ~10 min) reads ≈0.6 degC/h (gentle, no open),
    while a real open window that steps every tick reads the true steep rate.

    Until the room has moved at least ``min_step`` the rate is the (decaying) value
    since the reference — 0 while genuinely flat — so a flat room contributes no
    cooling evidence and the reference is held; on a real move the slope is taken
    over the true elapsed interval and the reference re-anchors. Returns
    ``(slope_or_None, new_ref_room, new_ref_s)``; ``ref_room is None`` seeds the
    reference and yields ``None`` (no slope yet).
    """
    if ref_room is None or ref_s is None:
        return None, room, now_s
    dt_s = now_s - ref_s
    if dt_s <= 0.0:
        return None, ref_room, ref_s
    slope = (room - ref_room) / (dt_s / 3600.0)
    if abs(room - ref_room) >= min_step:
        return slope, room, now_s
    return slope, ref_room, ref_s


def step_window_auto(
    state: WindowAutoState,
    slope: float | None,
    dt_min: float,
    cfg: WindowAutoConfig = _DEFAULT_CONFIG,
) -> WindowAutoState:
    """Advance the detector one tick. ``slope`` is dT/dt in degC/hour (or None).

    Pure and deterministic: returns a new state. The max-duration auto-reset is
    honoured even on a missing or aberrant sample so a stuck-open verdict always
    clears.
    """
    minutes_open = state.minutes_open + dt_min if state.open else 0.0

    # Missing or aberrant slope: do not pollute the EMA, but still allow the
    # anti-stick max-duration close to fire.
    if slope is None or abs(slope) > cfg.max_slope:
        if state.open and minutes_open >= cfg.max_duration_min:
            return replace(state, open=False, minutes_open=0.0)
        return replace(state, minutes_open=minutes_open)

    if state.n_points == 0:
        ema = slope
    else:
        ema = cfg.ema_old_weight * state.ema_slope + (1.0 - cfg.ema_old_weight) * slope
    n_points = state.n_points + 1

    open_ = state.open
    if n_points >= cfg.min_points:
        if not open_:
            if ema < -cfg.open_threshold:
                open_ = True
                minutes_open = 0.0
        # Close once the slope has RECOVERED to within close_fraction of the open
        # threshold — not only when it turns positive. A flat/idle room hovers
        # just below 0 and would otherwise hang open until max_duration (a
        # live-observed summer false positive). Anti-stick max_duration still fires.
        elif (
            ema >= -cfg.close_fraction * cfg.open_threshold
            or minutes_open >= cfg.max_duration_min
        ):
            open_ = False
            minutes_open = 0.0

    return WindowAutoState(
        ema_slope=round(ema, 3),
        n_points=n_points,
        open=open_,
        minutes_open=minutes_open,
    )


def effective_window_open(*, sensor_open: bool, auto_open: bool, bypass: bool) -> bool:
    """Control-effective open state (ADR-0041 stage 2 actuation).

    A configured window sensor OR the sensorless slope detector opens the
    reaction; a user ``bypass`` forces it closed — the escape hatch against a
    false slope detection or a deliberate "heat with the window open" override
    (community: BT #1638/#1487). The reaction itself (drop to the frost/mould
    floor via the constraint solver) is unchanged from the sensor path.
    """
    if bypass:
        return False
    return sensor_open or auto_open
