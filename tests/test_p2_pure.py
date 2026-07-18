"""Pure unit tests for the P2 audit bundle (R5, R7, R10).

Kept in one file so the P2 pure logic is verified in the sandbox without editing
existing test files (which the OneDrive mount tends to tail-truncate on edit).
The glue wiring (coordinator/climate) is exercised by the CI-only integration
suite; here we pin the pure helpers each finding rests on.
"""

from __future__ import annotations

from custom_components.poise.control.cooling import cooling_intent
from custom_components.poise.control.dynamics import PROFILES, DeviceDynamics
from custom_components.poise.control.optimal_start import heatup_minutes, plan_preheat
from custom_components.poise.control.tick_resolve import external_feed_due
from custom_components.poise.estimation.thermal_ekf import ThermalModel
from tests.harness.plant import RCPlant

# ---------------------------------------------------------------- R7 --

_MODEL = ThermalModel(alpha=0.15, beta_h=2.7, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def test_r7_max_lead_h_per_profile() -> None:
    # A heavy floor (user-flagged very_slow) begins heating hours earlier; the
    # radiator/AC classes keep today's 4 h so they never regress.
    assert PROFILES[DeviceDynamics.VERY_SLOW].max_lead_h == 12.0
    assert PROFILES[DeviceDynamics.SLOW_HYDRONIC].max_lead_h == 4.0
    assert PROFILES[DeviceDynamics.FAST_AIR].max_lead_h == 4.0


def test_r7_lead_reachable_only_within_a_longer_horizon() -> None:
    # This slow warm-up needs ~6 h of lead: outside the 4 h horizon, inside 12 h.
    lead4 = heatup_minutes(_MODEL, room=18.0, target=21.0, t_out=5.0, max_lead_h=4.0)
    assert lead4 is None
    lead12 = heatup_minutes(_MODEL, room=18.0, target=21.0, t_out=5.0, max_lead_h=12.0)
    assert lead12 is not None and 4 * 60 < lead12 < 12 * 60


def test_r7_plan_preheat_threads_max_lead_h() -> None:
    # ~5 h to the comfort deadline: within the 4 h horizon the room is unreachable
    # (best effort would begin only 4 h out, still in the future), while the 12 h
    # underfloor horizon finds a ~6 h lead and starts now. Proves plan_preheat
    # forwards max_lead_h into advise() -- the R7 wiring.
    kw = {
        "comfort_base": 21.0,
        "is_comfort": False,
        "setback_offset": -3.0,
        "minutes_to_comfort": 300.0,
        "optimal_start_enabled": True,
        "can_heat": True,
        "identified": True,
        "model": _MODEL,
        "room": 18.0,
        "t_out_lead": 5.0,
        "heat_lower": 20.0,
        "heat_upper": 24.0,
    }
    assert plan_preheat(**kw, max_lead_h=4.0).preheating is False
    assert plan_preheat(**kw, max_lead_h=12.0).preheating is True


# --------------------------------------------------------------- R10a --


def test_r10_cooling_intent_window_gate() -> None:
    # enabled + no window + mode cool -> cool; window / disabled / non-cool -> no.
    assert cooling_intent(enabled=True, window_open=False, mode="cool") is True
    assert cooling_intent(enabled=True, window_open=True, mode="cool") is False
    assert cooling_intent(enabled=False, window_open=False, mode="cool") is False
    assert cooling_intent(enabled=True, window_open=False, mode="heat") is False
    assert cooling_intent(enabled=True, window_open=False, mode="idle") is False


# --------------------------------------------------------------- R10e --


def test_r10_external_feed_due() -> None:
    # value move >= deadband -> due regardless of time
    moved = external_feed_due(20.0, 20.2, last_fed_ts=0.0, now=1.0, keepalive_s=600.0)
    assert moved
    # stable value, keepalive elapsed -> due
    stale = external_feed_due(20.0, 20.0, last_fed_ts=0.0, now=600.0, keepalive_s=600.0)
    assert stale
    # stable value, keepalive not elapsed -> not due
    fresh = external_feed_due(20.0, 20.0, last_fed_ts=0.0, now=59.0, keepalive_s=600.0)
    assert not fresh
    # keepalive disabled (<=0): only value moves fire
    off = external_feed_due(20.0, 20.0, last_fed_ts=0.0, now=1e9, keepalive_s=0.0)
    assert not off
    # first feed (last_fed None) always due
    first = external_feed_due(None, 20.0, last_fed_ts=0.0, now=0.0, keepalive_s=600.0)
    assert first


# ---------------------------------------------------------------- R5 --


def test_r5_plant_flow_is_linear_by_default() -> None:
    p = RCPlant()
    for d in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert p.flow(d) == d  # byte-for-byte identical to the old linear plant
    assert p.flow(-0.3) == 0.0  # clamps below 0
    assert p.flow(1.4) == 1.0  # clamps above 1


def test_r5_plant_flow_deadband_and_curve() -> None:
    p = RCPlant(valve_deadband=0.2, valve_curve=2.0)
    assert p.flow(0.2) == 0.0  # at/below deadband the seat is shut
    assert p.flow(0.1) == 0.0
    # above deadband: remaining travel remapped through the exponent, monotone
    assert 0.0 < p.flow(0.4) < p.flow(0.7) < p.flow(1.0)
    assert p.flow(1.0) == 1.0  # full travel still delivers full flow
