from __future__ import annotations

import pytest

from custom_components.poise.control.calibration import (
    local_calibration,
    setpoint_calibration,
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
