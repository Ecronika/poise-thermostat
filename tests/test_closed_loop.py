"""End-to-end closed-loop validation of the predictive core (ADR-0011/0032).

These exercise the *production* EKF + MPC + optimal-start as a learn → identify →
predict → control loop against the known-truth RC plant, so the winter-only path
is validated now (charter "Harness vor Hardware").
"""

from __future__ import annotations

from custom_components.poise.contracts import Bound, ComfortCorridor
from custom_components.poise.control.mpc_controller import MpcController
from custom_components.poise.control.optimal_start import advise, heatup_minutes
from tests.harness.closed_loop import (
    ekf_to_state,
    run_identification,
    run_mpc_optimizer,
)
from tests.harness.plant import RCPlant

# Plant truth: tau = 1/0.15 ≈ 6.67 h, effective beta_h = 3.0.
_TAU_TRUTH = 1.0 / 0.15
_BETA_H_TRUTH = 3.0


def test_ekf_identifies_and_learns_the_plant() -> None:
    res = run_identification(RCPlant())
    ekf = res.ekf
    model = ekf.get_model()
    assert ekf.identified, "EKF never reached identified under clean excitation"
    assert res.identified_step is not None and res.identified_step < 600
    assert abs(ekf.tau_hours - _TAU_TRUTH) < 1.5  # learns the time constant
    assert abs(model.beta_h - _BETA_H_TRUTH) < 0.6  # learns heating responsivity
    assert ekf.temperature_std < 0.5


def test_mpc_converges_to_target_without_oscillation() -> None:
    plant = RCPlant()
    model = run_identification(plant).ekf.get_model()
    trace = run_mpc_optimizer(
        plant,
        model,
        t_out=8.0,
        target=21.0,
        lower=20.0,
        upper=24.0,
        steps=144,
        start_air=18.0,
    )
    last_third = [air for air, _ in trace[-48:]]
    mean = sum(last_third) / len(last_third)
    assert 20.5 <= mean <= 21.5  # settles at the target
    assert max(last_third) - min(last_third) < 0.5  # no sustained oscillation
    assert max(air for air, _ in trace) <= 24.5  # never overshoots the band


def test_mpc_drives_a_cold_room_up() -> None:
    plant = RCPlant()
    model = run_identification(plant).ekf.get_model()
    trace = run_mpc_optimizer(plant, model, t_out=8.0, start_air=18.0, steps=144)
    assert trace[-1][0] > 20.0  # warmed from 18 toward target


def test_optimal_start_lead_is_physically_sane() -> None:
    plant = RCPlant()
    model = run_identification(plant).ekf.get_model()
    lead = heatup_minutes(model, room=19.0, target=21.0, t_out=8.0)
    assert lead is not None and 20.0 < lead < 240.0  # minutes, plausible
    # deadline within the lead -> start now; far deadline -> wait
    assert advise(
        model, room=19.0, target=21.0, t_out=8.0, minutes_to_comfort=30.0
    ).start_now
    assert not advise(
        model, room=19.0, target=21.0, t_out=8.0, minutes_to_comfort=600.0
    ).start_now


def test_mpc_controller_gate_blends_with_identified_model() -> None:
    ekf = run_identification(RCPlant()).ekf
    corridor = ComfortCorridor(
        lower=(Bound(20.0, "en16798"),), upper=(Bound(24.0, "en16798"),), target=21.0
    )
    mc = MpcController()
    cold = mc.evaluate(ekf_to_state(ekf, 18.0, 8.0, 12.0), corridor, "trv")
    warm = mc.evaluate(ekf_to_state(ekf, 25.0, 8.0, 12.0), corridor, "trv")
    assert cold.power > 0.5 and cold.regime == "heat"  # heats a cold room
    assert warm.power == 0.0 and warm.regime == "idle"  # idles a warm room
    assert "w=1.00" in cold.reason  # identified -> MPC fully weighted (no cliff)


def test_optimal_stop_coast_matches_plant() -> None:
    from custom_components.poise.control.optimal_stop import coastdown_minutes

    plant = RCPlant()
    model = run_identification(plant).ekf.get_model()
    room0, target, t_out, dt = 22.0, 20.0, 5.0, 60.0
    lead = coastdown_minutes(model, room=room0, target=target, t_out=t_out)
    assert lead is not None and 0.0 < lead < 240.0
    air = room0
    for _ in range(int(round(lead * 60.0 / dt))):
        air = plant.step(air, 0.0, t_out, dt)  # heater off -> coast
    assert abs(air - target) < 0.3  # lands at the lower comfort edge on schedule


def test_tpi_valve_control_converges_without_oscillation() -> None:
    from custom_components.poise.control.tpi import seed_from_model
    from tests.harness.closed_loop import run_tpi_control

    plant = RCPlant()  # truth: alpha 0.15/h, full-power rise 20 -> beta_h 3.0
    coef_int, coef_ext = seed_from_model(alpha=0.15, beta_h=3.0)
    trace = run_tpi_control(
        plant,
        coef_int=coef_int,
        coef_ext=coef_ext,
        t_out=8.0,
        target=21.0,
        steps=144,
        start_air=18.0,
    )
    last = [air for air, _ in trace[-48:]]
    mean = sum(last) / len(last)
    assert 20.5 <= mean <= 21.5  # holds the target
    assert max(last) - min(last) < 0.5  # no sustained oscillation
    assert all(0.0 <= d <= 1.0 for _, d in trace)  # duty stays a valid fraction
    # physical steady-state duty for t_out=8, target=21 is ~0.65 (8 + 20*d = 21)
    assert 0.5 < trace[-1][1] < 0.8


def test_tpi_drives_a_cold_room_up() -> None:
    from custom_components.poise.control.tpi import seed_from_model
    from tests.harness.closed_loop import run_tpi_control

    plant = RCPlant()
    coef_int, coef_ext = seed_from_model(alpha=0.15, beta_h=3.0)
    trace = run_tpi_control(
        plant, coef_int=coef_int, coef_ext=coef_ext, start_air=18.0, steps=144
    )
    assert trace[0][1] == 1.0  # cold room -> full duty initially
    assert trace[-1][0] > 20.0  # warmed toward target


def test_pi_compensator_reduces_proportional_droop() -> None:
    from tests.harness.closed_loop import run_pi_setpoint

    raw = run_pi_setpoint(RCPlant(), compensate=False)
    comp = run_pi_setpoint(RCPlant(), compensate=True)
    raw_air, comp_air = raw[-1][0], comp[-1][0]
    assert raw_air < 20.0  # a bare proportional TRV droops well below target
    assert comp_air - raw_air > 1.0  # compensation significantly cuts the droop
    assert comp_air > 20.3  # and gets the room close to the 21 °C target
    assert comp[-1][1] > 21.0  # by pushing the written setpoint above target
