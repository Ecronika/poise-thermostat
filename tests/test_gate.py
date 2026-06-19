from __future__ import annotations

import pytest

from custom_components.poise.control.gate import blend, mpc_weight


def test_low_std_gives_full_mpc() -> None:
    assert mpc_weight(0.1) == 1.0


def test_high_std_gives_zero_mpc() -> None:
    assert mpc_weight(0.5) == 0.0
    assert mpc_weight(0.9) == 0.0


def test_midband_is_linear() -> None:
    assert mpc_weight(0.35) == pytest.approx(0.5, abs=0.01)


def test_blend_is_convex() -> None:
    assert blend(1.0, 0.0, 0.5) == 0.5
    assert blend(1.0, 0.0, 1.0) == 1.0
    assert blend(1.0, 0.0, 0.0) == 0.0
