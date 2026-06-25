"""Input conditioning & degradation ladder (ADR-0012, charter G14/G15).

Turns raw, possibly missing/faulty samples into a :class:`Reading` whose
``source`` tag records how far down the ladder we had to go:

    measured -> derived -> estimated -> default

The provenance is never hidden; every downstream value carries it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .const import TEMP_PLAUSIBLE_MAX_C, TEMP_PLAUSIBLE_MIN_C
from .contracts import Reading, Source


@dataclass(frozen=True, slots=True)
class RawSample:
    value: float | None
    ts: float
    available: bool = True


def ingest_temperature(
    samples: Sequence[RawSample],
    *,
    now: float,
    last_good: float | None = None,
    default: float = 20.0,
    plausible_min: float = TEMP_PLAUSIBLE_MIN_C,
    plausible_max: float = TEMP_PLAUSIBLE_MAX_C,
) -> Reading:
    """Fuse temperature samples down the degradation ladder.

    1. ``measured``  — mean of available, plausible sensors.
    2. ``derived``   — last good value (sensor dropped out).
    3. ``default``   — reasoned safe default (no history).
    """
    values: list[float] = []
    for sample in samples:
        value = sample.value
        if (
            sample.available
            and value is not None
            and plausible_min <= value <= plausible_max
        ):
            values.append(value)

    if values:
        fused = sum(values) / len(values)
        confidence = min(1.0, 0.6 + 0.1 * len(values))
        return Reading(fused, "°C", Source.MEASURED, confidence, now)
    if last_good is not None:
        return Reading(last_good, "°C", Source.DERIVED, 0.4, now, sensor_ok=False)
    return Reading(default, "°C", Source.DEFAULT, 0.1, now, sensor_ok=False)


def parse_finite(raw: Any) -> float | None:
    """Parse a numeric value, rejecting None / non-numeric AND non-finite.

    NaN/Inf parse fine via ``float()`` but compare False in every bracketing, so
    the constraint solver cannot clamp them out — they must be rejected at the
    trust boundary before they reach control (review C1/Ü2).
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (ValueError, TypeError):
        return None
    return v if math.isfinite(v) else None
