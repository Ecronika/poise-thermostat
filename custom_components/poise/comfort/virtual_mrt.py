"""Virtual mean-radiant temperature (EN ISO 7726 / DIN 4108-2, ADR-0010/0017/0026).

When no globe/MRT sensor exists, estimate MRT from always-available signals:
the exterior envelope (cold walls in winter, warm in summer) pulls MRT toward
the outdoor temperature, and solar radiation adds a perceived radiant bump.
This is the shadow estimate (ADR-0026) feeding the operative-temperature
transform; a measured MRT sensor overrides it.

No double counting with the EKF solar disturbance ``beta_s`` (ADR-0010 point 5):
``beta_s`` books the *convective* solar gain into the air balance, while the
solar term here is the *radiant* perception — separate physical quantities.

Constants are conservative and harness-tunable (ADR-0017). ``ENV_COUPLING`` is
grounded in the Smart Setpoint blueprint example (−5 °C outdoor → ~+2 K air to
compensate cold walls, i.e. an effective coupling ~0.08).
"""

from __future__ import annotations

ENV_COUPLING: float = 0.08  # radiant coupling to the exterior envelope
SOLAR_MRT_GAIN_K: float = 1.5  # perceived radiant bump at full normalised sun [K]


def virtual_mrt(
    t_air: float,
    t_out: float,
    q_solar: float = 0.0,
    *,
    env_coupling: float = ENV_COUPLING,
    solar_gain: float = SOLAR_MRT_GAIN_K,
) -> float:
    """Estimated mean radiant temperature [°C].

    ``t_mrt = (1 - k)·t_air + k·t_out + solar_gain·q_solar`` — a blend toward the
    exterior envelope plus a solar radiant bump. Reduces to ``t_air`` when the
    envelope coupling is zero and there is no sun.
    """
    k = min(max(env_coupling, 0.0), 1.0)
    return (1.0 - k) * t_air + k * t_out + solar_gain * max(0.0, q_solar)
