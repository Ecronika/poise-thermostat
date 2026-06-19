from __future__ import annotations

import pytest

from custom_components.poise.comfort.corridor import ComfortContext, build_corridor
from custom_components.poise.comfort.en16798 import Category


def test_target_equals_comfort_temp_without_mrt() -> None:
    # No MRT -> operative == air; target should equal the EN comfort temp.
    corridor = build_corridor(
        ComfortContext(t_rm=15.0, t_air=20.0, frost_floor=7.0, device_max=30.0)
    )
    assert corridor.target == pytest.approx(23.75, abs=0.01)


def test_band_bounds_present_with_causes() -> None:
    corridor = build_corridor(
        ComfortContext(t_rm=15.0, t_air=20.0, frost_floor=7.0, device_max=30.0)
    )
    lower_causes = {b.cause for b in corridor.lower}
    upper_causes = {b.cause for b in corridor.upper}
    assert "en16798" in lower_causes and "frost" in lower_causes
    assert "en16798" in upper_causes and "device_max" in upper_causes


def test_mold_floor_added_when_humidity_known() -> None:
    corridor = build_corridor(
        ComfortContext(
            t_rm=15.0,
            t_air=20.0,
            frost_floor=7.0,
            device_max=30.0,
            rh_percent=70.0,
            t_out=-5.0,
        )
    )
    assert any(b.cause == "mold" for b in corridor.lower)


def test_cold_walls_raise_the_air_target() -> None:
    warm_walls = build_corridor(ComfortContext(15.0, 20.0, 7.0, 30.0, t_mrt=21.0))
    cold_walls = build_corridor(ComfortContext(15.0, 20.0, 7.0, 30.0, t_mrt=17.0))
    assert cold_walls.target > warm_walls.target


def test_category_one_is_narrower_than_three() -> None:
    cat1 = build_corridor(ComfortContext(20.0, 22.0, 7.0, 30.0, category=Category.I))
    cat3 = build_corridor(ComfortContext(20.0, 22.0, 7.0, 30.0, category=Category.III))
    band1 = cat1.binding_upper().value - cat1.binding_lower().value
    band3 = cat3.binding_upper().value - cat3.binding_lower().value
    assert band3 > band1
