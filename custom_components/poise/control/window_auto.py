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
    close_threshold: float = 0.0  # close when smoothed slope recovers to this
    max_duration_min: float = 30.0  # force-close after this long open (anti-stick)
    min_points: int = 3  # no verdict before this many samples
    ema_old_weight: float = 0.2  # EMA: w*old + (1-w)*new (VTherm 0.2/0.8)
    max_slope: float = 120.0  # |slope| above this is an artefact, ignored
    open_factor: float = 1.8  # adaptive open threshold = factor * natural cooling
    open_threshold_min: float = 2.0  # floor for the adaptive open threshold (degC/h)
    open_threshold_max: float = 12.0  # cap for the adaptive open threshold (degC/h)


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
        elif ema >= cfg.close_threshold or minutes_open >= cfg.max_duration_min:
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
