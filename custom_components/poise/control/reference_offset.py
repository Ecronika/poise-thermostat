"""Reference-frame offset between a self-regulating actuator's own sensor and the
room sensor (ADR-0056). Shadow-first: this estimates the offset and the
compensated setpoint; the coordinator surfaces them as diagnostics and does NOT
write them yet.

A split AC regulates on its own return-air sensor, which reads differently from
Poise's room sensor (measured ~1.2 K on the office unit, and sign-flipping over
the day). The AC drives its internal sensor to the written setpoint ``W``, so at
steady state the true room = ``W - offset`` with ``offset = actuator_internal -
room``. To land the ROOM at a room-referenced setpoint ``S`` we therefore write
``W = S + offset`` (symmetric for heat and cool — the device drives its own
sensor to ``W`` in both directions).

The catch (Versatile Thermostat's ``use_internal_temp`` warning, ADR-0056): a
noisy or sign-flipping actuator sensor makes the offset unreliable, and
compensating on it *amplifies* the error. So the estimate carries a stability
gate (``trusted``): the EWMA offset is trusted only once it has warmed up AND its
short-term deviation is small. When not trusted, compensation is suspended
(``W = S``). Pure and HA-free (ADR-0005/0011).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

DEFAULT_HORIZON_MIN = 30.0  # EWMA time constant for the offset
DEFAULT_CAP_K = 2.0  # |offset| never exceeds this
DEFAULT_NOISE_MAX_K = 0.6  # short-term deviation above which the offset is untrusted
DEFAULT_WARMUP_MIN = 30.0  # minimum observation time before the offset is trusted


@dataclass(frozen=True, slots=True)
class OffsetEstimate:
    """EWMA estimate of ``actuator_internal - room`` plus a trust gate (ADR-0056)."""

    offset: float  # EWMA-smoothed, capped (K)
    deviation: float  # EWMA of the raw step-to-step change — instability measure (K)
    minutes: float  # accumulated observation time
    trusted: bool  # stable enough to compensate on?
    raw: float  # last instantaneous offset (diagnostic)

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "deviation": self.deviation,
            "minutes": self.minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OffsetEstimate:
        off = float(data.get("offset", 0.0))
        return cls(
            offset=off,
            deviation=float(data.get("deviation", 0.0)),
            minutes=float(data.get("minutes", 0.0)),
            # Trust is re-derived on the next observation (conservative restore):
            # never compensate straight after a restart without a fresh sample.
            trusted=False,
            raw=off,
        )


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def update_offset(
    prev: OffsetEstimate | None,
    *,
    actuator_temp: float | None,
    room_temp: float | None,
    dt_min: float,
    conditioning: bool = True,
    horizon_min: float = DEFAULT_HORIZON_MIN,
    cap: float = DEFAULT_CAP_K,
    noise_max: float = DEFAULT_NOISE_MAX_K,
    warmup_min: float = DEFAULT_WARMUP_MIN,
) -> OffsetEstimate | None:
    """Fold one ``(actuator, room)`` sample into the EWMA offset estimate.

    ``dt_min`` is the real elapsed time since the last update (caller-supplied,
    monotonic — the EKF pattern). A missing actuator/room reading holds the prior
    estimate unchanged (no decay: the offset is a slow physical property of the
    sensor placement). The same hold applies while the actuator is not
    actively conditioning (``conditioning=False``): the internal sensor only
    carries the placement bias while the device drives air/heat past it, so idle
    ticks would pull the offset toward zero — they are skipped, and the warm-up
    therefore counts real conditioning time.
    The trust gate requires BOTH a warm-up and a low
    short-term deviation, so a noisy or sign-flipping sensor never enables
    compensation (ADR-0056).
    """
    if not conditioning or actuator_temp is None or room_temp is None:
        return prev
    raw = actuator_temp - room_temp
    if prev is None:
        return OffsetEstimate(
            offset=_clamp(raw, -cap, cap),
            deviation=0.0,
            minutes=max(0.0, dt_min),
            trusted=False,  # never trust a first sample
            raw=raw,
        )
    dt = max(0.0, dt_min)
    alpha = 1.0 - math.exp(-dt / horizon_min) if horizon_min > 0 else 1.0
    offset = _clamp((1.0 - alpha) * prev.offset + alpha * raw, -cap, cap)
    # instability = how jumpy the raw offset is (step-to-step). A large but STEADY
    # offset (stable sensor placement) stays trusted; a sign-flipping / noisy
    # sensor drives this up and suspends compensation (VTherm caveat, ADR-0056).
    deviation = (1.0 - alpha) * prev.deviation + alpha * abs(raw - prev.raw)
    minutes = prev.minutes + dt
    trusted = minutes >= warmup_min and deviation <= noise_max
    return OffsetEstimate(
        offset=offset,
        deviation=deviation,
        minutes=minutes,
        trusted=trusted,
        raw=raw,
    )


def compensated_setpoint(
    base_setpoint: float, estimate: OffsetEstimate | None, *, enabled: bool
) -> float:
    """The reference-frame-corrected write setpoint ``W = S + offset`` (ADR-0056).

    Returns ``base_setpoint`` unchanged unless compensation is enabled AND the
    estimate is present and trusted (the stability gate). Symmetric for heat and
    cool: the actuator drives its own sensor to ``W`` in both directions, so the
    same additive offset lands the room at ``base_setpoint``.
    """
    if not enabled or estimate is None or not estimate.trusted:
        return round(base_setpoint, 2)
    return round(base_setpoint + estimate.offset, 2)
