"""PI-compensated setpoint for sluggish TRVs (Versatile method).

Pushes a compensated setpoint to a slow setpoint-only TRV so it converges:
  offset = kp·err + ki·∫err + k_ext·(room-external),  clamped to +-offset_max.
"""

from __future__ import annotations


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


class PiCompensator:
    def __init__(
        self,
        kp: float = 0.2,
        ki: float = 0.8 / 288.0,
        k_ext: float = 1.0 / 25.0,
        offset_max: float = 2.0,
    ) -> None:
        self._kp = kp
        self._ki = ki
        self._k_ext = k_ext
        self._offset_max = offset_max
        self._acc = 0.0

    def compensate(self, target: float, room: float, external: float) -> float:
        """Return the compensated setpoint to push to the TRV."""
        error = target - room
        self._acc += error
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
