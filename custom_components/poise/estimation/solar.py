"""Analytic clear-sky solar proxy + measured-irradiance normalisation (ADR-0010).

Solar enters the model exactly once as the learned EKF disturbance ``beta_s``,
with a *normalised* input ``q_solar`` in [0, 1] (RoomMind pattern: GHI/1000 so
``beta_s`` stays size-comparable). The internal estimate is a clear-sky proxy
from the solar elevation angle (irradiance on a horizontal surface scales with
the sine of the solar altitude); a measured global-horizontal-irradiance sensor,
if configured, overrides it (shadow-estimator principle, ADR-0026). Pure module.
"""

from __future__ import annotations

import math

GHI_REFERENCE_WM2: float = 1000.0  # ~1 sun; normalises GHI to ~[0, 1] (ADR-0010)


def clear_sky_normalized(elevation_deg: float) -> float:
    """Normalised clear-sky solar proxy in [0, 1] from solar elevation [deg].

    Below the horizon it is zero; otherwise ``sin(elevation)`` (clamped). This is
    the always-on internal estimate used when no irradiance sensor exists.
    """
    if elevation_deg <= 0.0:
        return 0.0
    return min(1.0, math.sin(math.radians(elevation_deg)))


def normalize_irradiance(ghi_wm2: float, reference: float = GHI_REFERENCE_WM2) -> float:
    """Normalise measured global horizontal irradiance [W/m²] to [0, 1]."""
    if ghi_wm2 <= 0.0 or reference <= 0.0:
        return 0.0
    return min(1.0, ghi_wm2 / reference)
