"""Bias-free heat-up rate sampler for the seasonless prior (ADR-0004/0009).

The seasonless estimator wants dT/dt at the start of a heat-up (≈ beta_h). Naively
sampling it per tick as ``(room - prev_room) / dt`` and keeping only ``rate > 0``
is badly biased on a **quantized** sensor: during a slow rise most ticks read the
same value (rate 0, dropped) and only the occasional quantum up-crossing survives,
whose magnitude is the quantum over a single short tick -> a large spike. Pooling
those spikes overestimates the true rate (and inflates the beta_h seed).

Fix: anchor at the start of a heating burst and emit a rate only once the room has
risen by at least ``MIN_RISE_K``, dividing that real rise by the FULL elapsed
interval — the flat ticks are now counted in the denominator, so the estimate is
unbiased regardless of the sensor quantum. Pure stdlib, no state beyond the anchor.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_RISE_K: float = 0.3  # require a few quanta of real rise before emitting
MAX_SPAN_H: float = 1.0  # a burst older than this is stale -> re-anchor, drop


@dataclass
class HeatupAccumulator:
    """Anchor for the current rising heat-up burst (transient, not persisted)."""

    anchor_room: float | None = None
    anchor_mono: float | None = None

    def reset(self) -> None:
        self.anchor_room = None
        self.anchor_mono = None


def sample_heatup_rate(
    acc: HeatupAccumulator,
    *,
    heating: bool,
    room: float,
    mono: float,
    min_rise_k: float = MIN_RISE_K,
    max_span_h: float = MAX_SPAN_H,
) -> float | None:
    """Return an unbiased heat-up rate [K/h] to record, or None; mutates ``acc``.

    ``heating`` gates the whole thing (the rate is only meaningful while a heating
    demand drove the elapsed interval). ``mono`` is a monotonic clock in seconds.
    A rate is emitted once the accumulated rise clears ``min_rise_k``; the anchor
    then advances to the current sample so the next interval starts fresh.
    """
    if not heating:
        acc.reset()
        return None

    if acc.anchor_room is None or acc.anchor_mono is None:
        acc.anchor_room = room
        acc.anchor_mono = mono
        return None

    elapsed_h = (mono - acc.anchor_mono) / 3600.0
    if elapsed_h <= 0.0 or elapsed_h > max_span_h:
        # clock glitch or a stale gap (missed ticks): re-anchor, emit nothing.
        acc.anchor_room = room
        acc.anchor_mono = mono
        return None

    rise = room - acc.anchor_room
    if rise < 0.0:
        # room fell while nominally heating (quantization dip / disturbance):
        # re-anchor at the lower point rather than accumulate a negative rise.
        acc.anchor_room = room
        acc.anchor_mono = mono
        return None
    if rise < min_rise_k:
        # not enough real rise yet — keep the anchor and wait (the flat ticks in
        # between are exactly what makes the eventual denominator unbiased).
        return None

    rate = rise / elapsed_h
    acc.anchor_room = room
    acc.anchor_mono = mono
    return rate
