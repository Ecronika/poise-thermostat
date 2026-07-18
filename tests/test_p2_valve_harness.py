"""R5: TPI direct-valve control stays stable against a non-ideal valve.

The harness plant grows an optional deadband + authority curve (R5); driving the
seeded, stateless TPI duty controller against that non-linear valve must still
settle without hunting -- the direct-valve path is validated against realistic
actuator physics before any live flip (ADR-0011/0036). Linear-plant convergence
is already covered by ``test_closed_loop.py``; this pins the non-linear case.
"""

from __future__ import annotations

from custom_components.poise.control.tpi import seed_from_model
from tests.harness.closed_loop import run_tpi_control
from tests.harness.plant import RCPlant


def test_tpi_converges_against_nonlinear_valve() -> None:
    # a valve with a 15 % dead zone and a >1 authority curve (equal-%-ish)
    plant = RCPlant(valve_deadband=0.15, valve_curve=1.6)
    coef_int, coef_ext = seed_from_model(alpha=0.15, beta_h=3.0)
    trace = run_tpi_control(
        plant, coef_int=coef_int, coef_ext=coef_ext, start_air=18.0, steps=200
    )
    airs = [a for a, _ in trace]
    assert airs[0] < airs[-1]  # the cold room warms through the non-linear valve
    tail = airs[-20:]
    assert max(tail) - min(tail) < 0.2  # settled: no hunting / limit cycle
    assert all(0.0 <= d <= 1.0 for _, d in trace)  # duty stays a valid fraction
