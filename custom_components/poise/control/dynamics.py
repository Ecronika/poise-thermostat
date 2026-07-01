"""Per-HVAC-type actuator dynamics profiles (ADR-0052).

A 2-hour PI integral time is right for a sluggish radiator but makes a split AC
— which swings the room in minutes — oscillate. Each actuator gets a dynamics
profile (integral time, output clamp, MPC block/horizon) chosen from its kind:
a fast air system gets minute-scale tuning, a hydronic radiator keeps the slow
tuning, very-slow underfloor goes slower still. Pure and unit-tested; the
coordinator selects the profile from the actuator's capabilities (+ optional
override) and retunes the PI/MPC. ``slow_hydronic`` is byte-for-byte today's
tuning, so radiators never regress.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DeviceDynamics(Enum):
    FAST_AIR = "fast_air"  # split AC / air-to-air heat pump (minutes)
    SLOW_HYDRONIC = "slow_hydronic"  # radiator / TRV (today's tuning)
    VERY_SLOW = "very_slow"  # underfloor / storage (hours)


@dataclass(frozen=True, slots=True)
class DynamicsProfile:
    kind: DeviceDynamics
    pi_kp: float
    pi_ki: float  # per hour; integral time Ti = pi_kp / pi_ki
    offset_max: float  # PI output clamp [K]; also bounds the integrator (anti-windup)
    mpc_dt_h: float  # MPC block length [h]
    mpc_horizon_blocks: int
    regulation_period_s: float  # min seconds between setpoint nudges (fast path)
    self_regulating: bool  # has its own thermostat -> nudge, not a slow loop

    @property
    def integral_time_h(self) -> float:
        return self.pi_kp / self.pi_ki if self.pi_ki > 0.0 else 0.0


# fast air: Ti ~ 10 min, tight output clamp so a cold blast can't bank a big
# offset; short MPC blocks so overshoot is charged within the horizon.
_FAST_AIR = DynamicsProfile(
    kind=DeviceDynamics.FAST_AIR,
    pi_kp=0.2,
    pi_ki=1.2,  # Ti = 0.2 / 1.2 = 10 min
    offset_max=0.8,
    mpc_dt_h=2.0 / 60.0,
    mpc_horizon_blocks=15,  # 30 min
    regulation_period_s=300.0,
    self_regulating=True,
)
# slow hydronic = today's exact tuning (radiators/TRVs) -> no regression.
_SLOW_HYDRONIC = DynamicsProfile(
    kind=DeviceDynamics.SLOW_HYDRONIC,
    pi_kp=0.2,
    pi_ki=0.1,  # Ti = 2 h
    offset_max=2.0,
    mpc_dt_h=5.0 / 60.0,
    mpc_horizon_blocks=12,  # 1 h
    regulation_period_s=0.0,
    self_regulating=False,
)
_VERY_SLOW = DynamicsProfile(
    kind=DeviceDynamics.VERY_SLOW,
    pi_kp=0.2,
    pi_ki=0.05,  # Ti = 4 h
    offset_max=2.0,
    mpc_dt_h=10.0 / 60.0,
    mpc_horizon_blocks=18,  # 3 h
    regulation_period_s=0.0,
    self_regulating=False,
)

PROFILES: dict[DeviceDynamics, DynamicsProfile] = {
    DeviceDynamics.FAST_AIR: _FAST_AIR,
    DeviceDynamics.SLOW_HYDRONIC: _SLOW_HYDRONIC,
    DeviceDynamics.VERY_SLOW: _VERY_SLOW,
}


def classify_dynamics(
    *,
    domain: str,
    can_cool: bool,
    can_fan: bool,
    override: str | None = None,
) -> DeviceDynamics:
    """Pick the dynamics class.

    An explicit override (a ``DeviceDynamics`` value) wins; ``"auto"`` or any
    unknown value falls through to auto-detection: a climate device that can
    cool or move air is a fast air system, anything else (heat-only TRV / switch
    / valve) keeps the slow hydronic tuning.
    """
    if override:
        try:
            return DeviceDynamics(override)
        except ValueError:
            pass  # "auto" / unknown -> auto-detect below
    if domain == "climate" and (can_cool or can_fan):
        return DeviceDynamics.FAST_AIR
    return DeviceDynamics.SLOW_HYDRONIC


def profile_for(
    *,
    domain: str,
    can_cool: bool,
    can_fan: bool,
    override: str | None = None,
) -> DynamicsProfile:
    return PROFILES[
        classify_dynamics(
            domain=domain, can_cool=can_cool, can_fan=can_fan, override=override
        )
    ]


def regulation_throttled(
    *, now_s: float, last_write_s: float | None, regulation_period_s: float
) -> bool:
    """True if a self-regulating setpoint nudge should be held back this tick.

    A self-regulating climate entity has its own thermostat, so Poise writes its
    target at most once per ``regulation_period_s`` (VTherm's "minimum regulation
    period", ADR-0052 §4) instead of nudging it every tick — otherwise per-tick
    comfort adjustments thrash the device (and its compressor). A dumb setpoint
    actuator (``regulation_period_s == 0``, e.g. a TRV that Poise's PI drives) is
    never throttled, and the first write (``last_write_s is None``) always
    passes. The coordinator additionally bypasses this for mode changes / window
    / override / frozen-sensor safety, so only routine comfort nudges throttle.
    """
    if regulation_period_s <= 0.0 or last_write_s is None:
        return False
    return (now_s - last_write_s) < regulation_period_s
