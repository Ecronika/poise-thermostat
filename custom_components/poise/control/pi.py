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

    def evaluate(
        self,
        target: float,
        room: float,
        external: float,
        dt_h: float = _NOMINAL_DT_H,
    ) -> tuple[float, float]:
        """Pure: return ``(compensated_setpoint, new_acc)`` WITHOUT mutating state.

        The integrator value is returned, not stored, so a *shadow* evaluation has
        no side effect on the persisted integrator (review P6/F-1); the caller
        persists ``new_acc`` once per tick. ``external`` is the **outdoor**
        temperature for the feed-forward term — passing ``room`` kills the
        ``k_ext`` term, which is its whole purpose.
        """
        error = target - room
        new_acc = self._acc + error * dt_h
        # anti-windup: cap the integral so ki·acc stays within +-offset_max
        if self._ki > 0.0:
            acc_limit = self._offset_max / self._ki
            new_acc = _clamp(new_acc, -acc_limit, acc_limit)
        offset = self._kp * error + self._ki * new_acc + self._k_ext * (room - external)
        return target + _clamp(offset, -self._offset_max, self._offset_max), new_acc

    def compensate(
        self,
        target: float,
        room: float,
        external: float,
        dt_h: float = _NOMINAL_DT_H,
    ) -> float:
        """Compensated setpoint for the live path; advances the integrator."""
        setpoint, self._acc = self.evaluate(target, room, external, dt_h)
        return setpoint

    @property
    def acc(self) -> float:
        return self._acc

    @acc.setter
    def acc(self, value: float) -> None:
        self._acc = value

    def reset(self) -> None:
        self._acc = 0.0

    def apply_profile(self, *, kp: float, ki: float, offset_max: float) -> None:
        """Retune in place for a device-dynamics profile (ADR-0052) — keeps the
        integrator accumulator, so a profile refresh causes no transient reset.
        """
        self._kp = kp
        self._ki = ki
        self._offset_max = offset_max
