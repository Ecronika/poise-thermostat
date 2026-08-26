from __future__ import annotations

import pytest

from custom_components.poise.control.calibration import (
    calibration_accumulation_allowed,
    calibration_converged,
    calibration_diverged,
    calibration_write_due,
    local_calibration,
    setpoint_calibration,
    snap_offset,
)


def test_local_calibration_corrects_toward_external() -> None:
    # TRV reads 19, external truth 21 -> offset should push +2
    assert local_calibration(21.0, 19.0, 0.0) == pytest.approx(2.0)


def test_local_calibration_accumulates_and_clamps() -> None:
    assert local_calibration(30.0, 0.0, 4.0) == 5.0  # clamped to max


def test_setpoint_calibration_fakes_target() -> None:
    # want 21 with external 21, trv reads 19 -> calibrated setpoint 19
    assert setpoint_calibration(21.0, 21.0, 19.0) == pytest.approx(19.0)


def test_setpoint_calibration_clamps() -> None:
    assert setpoint_calibration(40.0, 0.0, 20.0) == 30.0  # clamped to max_sp


def test_snap_offset_raster_relative_to_min_tie_picks_smaller() -> None:
    # min=-4.3, step=0.2: candidates -0.1 / +0.1, equal distance, equal
    # magnitude -> rule 3: the smaller value
    assert snap_offset(0.0, step=0.2, min_value=-4.3, max_value=4.3) == pytest.approx(
        -0.1
    )


def test_snap_offset_half_step_rounds_away_from_zero() -> None:
    # candidates 0.0/0.5 resp. -0.5/0.0, equal distance -> larger magnitude
    assert snap_offset(0.25, step=0.5, min_value=-5.0, max_value=5.0) == 0.5
    assert snap_offset(-0.25, step=0.5, min_value=-5.0, max_value=5.0) == -0.5


def test_snap_offset_identity_on_exact_rung() -> None:
    assert snap_offset(0.5, step=0.5, min_value=-5.0, max_value=5.0) == 0.5


def test_snap_offset_degenerate_min_equals_max() -> None:
    assert snap_offset(3.0, step=0.5, min_value=2.0, max_value=2.0) == 2.0


def test_snap_offset_nearest_wins_when_not_tied() -> None:
    assert snap_offset(0.2, step=0.5, min_value=-5.0, max_value=5.0) == 0.0
    assert snap_offset(0.3, step=0.5, min_value=-5.0, max_value=5.0) == 0.5


def test_snap_offset_clamps_and_handles_float_artifacts() -> None:
    assert snap_offset(9.0, step=0.1, min_value=-5.0, max_value=5.0) == 5.0
    assert snap_offset(-9.0, step=0.1, min_value=-5.0, max_value=5.0) == -5.0
    assert snap_offset(
        0.30000000000000004, step=0.1, min_value=-5.0, max_value=5.0
    ) == pytest.approx(0.3)


def test_snap_offset_never_leaves_grid_at_offgrid_max() -> None:
    # max=4.25 is not on the grid min+n*0.2; the last valid grid value is 4.1
    assert snap_offset(9.0, step=0.2, min_value=-4.3, max_value=4.25) == pytest.approx(
        4.1
    )
    assert snap_offset(4.2, step=0.2, min_value=-4.3, max_value=4.25) == pytest.approx(
        4.1
    )


def test_write_due_deadband_and_interval() -> None:
    assert not calibration_write_due(
        new_offset=1.0, reported_offset=0.9, last_write_ts=None, now=1000.0
    )
    assert calibration_write_due(
        new_offset=1.0, reported_offset=0.6, last_write_ts=None, now=1000.0
    )
    assert not calibration_write_due(
        new_offset=3.0, reported_offset=0.0, last_write_ts=800.0, now=1000.0
    )
    assert calibration_write_due(
        new_offset=3.0, reported_offset=0.0, last_write_ts=600.0, now=1000.0
    )
    # deadband boundary is float-epsilon tolerant: 0.7-0.4 == 0.29999999999999993
    # (< 0.3 in raw float) must still count as "at the deadband" -> due
    assert calibration_write_due(
        new_offset=0.7, reported_offset=0.4, last_write_ts=None, now=1000.0
    )
    # interval boundary is inclusive: exactly min_interval_s elapsed -> due
    assert calibration_write_due(
        new_offset=3.0, reported_offset=0.0, last_write_ts=700.0, now=1000.0
    )


def test_accumulation_requires_convergence_and_fresh_report() -> None:
    # before the first write: always allowed
    assert calibration_accumulation_allowed(
        reported_offset=0.0,
        last_cal_value=None,
        step=0.5,
        actuator_updated_after_write=False,
    )
    # -1.5 dispatched, device still reports 0.0 -> not allowed (runaway guard)
    assert not calibration_accumulation_allowed(
        reported_offset=0.0,
        last_cal_value=-1.5,
        step=0.5,
        actuator_updated_after_write=True,
    )
    # device reports -1.5 but no fresh actuator report since the write -> not allowed
    assert not calibration_accumulation_allowed(
        reported_offset=-1.5,
        last_cal_value=-1.5,
        step=0.5,
        actuator_updated_after_write=False,
    )
    # both -> allowed (half-step tolerance)
    assert calibration_accumulation_allowed(
        reported_offset=-1.4,
        last_cal_value=-1.5,
        step=0.5,
        actuator_updated_after_write=True,
    )


def test_diverged_is_a_time_predicate_not_a_tick_counter() -> None:
    # tick interval irrelevant: diverged only from 3 * 300 s without convergence
    assert not calibration_diverged(converged=False, last_write_ts=0.0, now=899.0)
    assert calibration_diverged(converged=False, last_write_ts=0.0, now=900.0)
    assert not calibration_diverged(converged=True, last_write_ts=0.0, now=5000.0)
    assert not calibration_diverged(converged=False, last_write_ts=None, now=5000.0)


def test_converged_none_is_trivially_true_and_tolerance_is_half_step() -> None:
    # P1.4c: THE one convergence formula, shared by the evidence gate and the
    # divergence input. No command ever dispatched -> trivially converged.
    assert calibration_converged(reported_offset=0.0, last_cal_value=None, step=0.5)
    # Exactly half a step (plus the shared epsilon) still converges...
    assert calibration_converged(reported_offset=-1.25, last_cal_value=-1.5, step=0.5)
    # ...anything beyond does not.
    assert not calibration_converged(
        reported_offset=-1.0, last_cal_value=-1.5, step=0.5
    )
