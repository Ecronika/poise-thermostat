from __future__ import annotations

import pytest

from custom_components.poise.comfort.virtual_mrt import virtual_mrt


def test_equal_outdoor_no_sun_equals_air() -> None:
    assert virtual_mrt(21.0, 21.0, 0.0) == pytest.approx(21.0)


def test_cold_walls_pull_mrt_below_air() -> None:
    mrt = virtual_mrt(21.0, -5.0, 0.0)
    assert mrt < 21.0
    assert mrt > -5.0  # only a fraction of the way to outdoor


def test_warm_outside_pulls_mrt_above_air() -> None:
    assert virtual_mrt(21.0, 30.0, 0.0) > 21.0


def test_solar_adds_radiant_bump() -> None:
    assert virtual_mrt(21.0, 21.0, 1.0) == pytest.approx(21.0 + 1.5)
    # partial sun -> partial bump
    assert virtual_mrt(21.0, 21.0, 0.5) == pytest.approx(21.0 + 0.75)


def test_zero_coupling_no_sun_is_identity() -> None:
    assert virtual_mrt(21.0, -10.0, 0.0, env_coupling=0.0) == pytest.approx(21.0)


def test_blueprint_example_winter_correction() -> None:
    # Smart Setpoint README: cold day should nudge MRT a couple K below air.
    mrt = virtual_mrt(22.0, -5.0, 0.0)
    assert 19.0 < mrt < 21.0  # ~19.8 with ENV_COUPLING 0.08


def test_negative_solar_is_ignored() -> None:
    assert virtual_mrt(21.0, 21.0, -1.0) == pytest.approx(21.0)


def test_q_solar_bump_is_capped() -> None:
    # Nit: an unbounded q_solar must not produce an unbounded radiant bump.
    huge = virtual_mrt(t_air=21.0, t_out=21.0, q_solar=1000.0, env_coupling=0.0)
    capped = virtual_mrt(t_air=21.0, t_out=21.0, q_solar=2.0, env_coupling=0.0)
    assert huge == capped  # clamped to _Q_SOLAR_MAX
