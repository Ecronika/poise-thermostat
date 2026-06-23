"""PI-compensated setpoint for sluggish TRVs (Versatile method).

Pushes a compensated setpoint to a slow setpoint-only TRV so it converges:
  offset = kp·err + ki·∫(err·dt) + k_ext·(room-external),  clamped to +-offset_max.

The integral is time-aware (review F6): it accumulates ``error·dt_h`` and ``ki``
is expressed per hour, so the behaviour is independent of the tick rate (the old
``ki = 0.8/288`` silently assumed a 5-min tick; the real tick is 60 s). Mature
integrators do the same (VTherm PI-offset ``error·time_delta``, HASmartThermostat
PID ``error·dt``); the duty-style TPI law stays stateless and is unaffected.
"""

from __future__ import annotations

_NOMINAL_DT_H: float = 1.0 / 60.0  # one 60 s tick in hours (callers pass real dt_h)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


class PiCompensator:
    def __init__(
        self,
        kp: float = 0.2,
        ki: float = 0.1,  # per hour (integral time Ti = kp/ki = 2 h)
        k_ext: float = 1.0 / 25.0,
        offset_max: float = 2.0,
    ) -> None:
        self._kp = kp
        self._ki = ki
        self._k_ext = k_ext
        self._offset_max = offset_max
        self._acc = 0.0

    def compensate(
        self,
        target: float,
        room: float,
        external: float,
        dt_h: float = _NOMINAL_DT_H,
    ) -> float:
        """Return the compensated setpoint to push to the TRV (``dt_h`` in hours)."""
        error = target - room
        self._acc += error * dt_h
        # anti-windup: cap the integral so ki·acc stays within +-offset_max
        if self._ki > 0.0:
            acc_limit = self._offset_max / self._ki
            self._acc = _clamp(self._acc, -acc_limit, acc_limit)
        offset = (
            self._kp * error + self._ki * self._acc + self._k_ext * (room - external)
        )
        return target + _clamp(offset, -self._offset_max, self._offset_max)

    def reset(self) -> None:
        self._acc = 0.0
