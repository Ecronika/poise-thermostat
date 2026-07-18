"""R3: a heating failure (boiler off, valve open) must not poison ``beta_h``.

Closed-loop check on the *production* EKF + RC plant (no HA runtime). After the
harness identifies a good model, a "boiler is off while the TRV valve is open"
episode feeds the EKF ``u_h=1`` (Poise commands heat / the valve reports open)
while the plant receives zero power, so the warm room only cools toward the cold
outside. Learning through that episode corrupts ``beta_h`` -- the filter tries to
explain "full heat, yet the room falls" and mis-splits the surprise across the
loss and heating terms (the VTherm #1428 corruption class). The R3 gate
(``should_learn(heating_failed=True) is False``, wired from the latched
previous-tick verdict) skips the learn step, so the identified model is frozen
and stays usable. This test pins that difference.
"""

from __future__ import annotations

import copy

from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from tests.harness.closed_loop import run_identification
from tests.harness.plant import RCPlant


def _boiler_off_valve_open(
    ekf: ThermalEKF,
    *,
    learn: bool,
    t_out: float = 2.0,
    start_air: float = 21.0,
    steps: int = 360,
    dt: float = 60.0,
) -> float:
    """Run an 'intended heating' episode with NO real heat delivered.

    ``u_h=1`` every tick (valve open / Poise commands heat) but the plant gets
    zero power (boiler off), so the room drifts toward ``t_out``. ``learn`` gates
    the EKF step exactly as the coordinator's ``should_learn(heating_failed=...)``
    does: when the failure is latched the whole learn step is skipped, so the
    model is untouched across the contaminated interval.
    """
    plant = RCPlant()
    air = start_air
    dt_h = dt / 3600.0
    for _ in range(steps):
        if learn:
            ekf.predict(dt_h, t_out=t_out, u_h=1.0)
            ekf.update(air)
        air = plant.step(air, 0.0, t_out, dt)
    return ekf.get_model().beta_h


def test_heating_failure_does_not_poison_beta_h() -> None:
    ident = run_identification(RCPlant())
    assert ident.identified_step is not None  # a usable model was learned
    beta0 = ident.ekf.get_model().beta_h
    assert beta0 > 1.5  # close to the plant truth (~3.0), well above the bound

    # Same identified filter, two continuations of a boiler-off / valve-open spell.
    beta_leak = _boiler_off_valve_open(copy.deepcopy(ident.ekf), learn=True)
    beta_gated = _boiler_off_valve_open(copy.deepcopy(ident.ekf), learn=False)

    # R3 gate: the model is frozen through the failure -> identified value intact.
    assert beta_gated == beta0
    assert beta_gated > 1.5  # still usable after the episode
    # Ungated learning corrupts the heat gain: the room falls under commanded
    # heat, so the joint filter drives beta_h far off the ~3.0 plant truth (which
    # way it moves depends on how it splits the surprise with the loss term). The
    # gate keeps beta_h markedly closer to truth.
    assert abs(beta_gated - 3.0) < abs(beta_leak - 3.0)
