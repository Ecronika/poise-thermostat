"""ADR-0050 humidity management decision (pure)."""

from __future__ import annotations

from custom_components.poise.comfort.en16798 import Category
from custom_components.poise.comfort.humidity import (
    humidity_decide,
    rh_high_for_category,
)


def test_no_sensor_graceful() -> None:
    d = humidity_decide(rh=None, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "idle"
    assert d.dry_active is False


def test_dry_guard_blocks_below_rh_low() -> None:
    d = humidity_decide(rh=35.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "dry_guard"
    assert d.dry_active is False


def test_cool_first_when_too_warm() -> None:
    d = humidity_decide(rh=70.0, too_warm=True, in_deadband=False, can_dry=True)
    assert d.action == "cool"
    assert d.dry_active is False


def test_enter_dry_in_band_above_high() -> None:
    d = humidity_decide(rh=62.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "dry"
    assert d.dry_active is True


def test_no_entry_just_below_high() -> None:
    d = humidity_decide(rh=58.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "idle"
    assert d.dry_active is False


def test_hysteresis_holds_between_exit_and_entry() -> None:
    # already drying, RH 57 (>= 55 exit) -> stay dry
    d = humidity_decide(
        rh=57.0, too_warm=False, in_deadband=True, can_dry=True, prev_dry_active=True
    )
    assert d.action == "dry"
    assert d.dry_active is True


def test_hysteresis_exits_below_exit_threshold() -> None:
    d = humidity_decide(
        rh=54.0, too_warm=False, in_deadband=True, can_dry=True, prev_dry_active=True
    )
    assert d.action == "idle"
    assert d.dry_active is False


def test_fan_only_never_dehumidifies() -> None:
    d = humidity_decide(
        rh=65.0, too_warm=False, in_deadband=True, can_dry=False, can_fan_only=True
    )
    assert d.action == "idle"
    assert "fan_only" in d.reason


def test_capability_gap_no_dry() -> None:
    d = humidity_decide(rh=65.0, too_warm=False, in_deadband=True, can_dry=False)
    assert d.action == "idle"
    assert "cannot dry" in d.reason


def test_within_band_idle() -> None:
    d = humidity_decide(rh=50.0, too_warm=False, in_deadband=True, can_dry=True)
    assert d.action == "idle"
    assert d.dry_active is False


def test_category_one_lowers_ceiling_to_50() -> None:
    d = humidity_decide(
        rh=52.0, too_warm=False, in_deadband=True, can_dry=True, category=Category.I
    )
    assert d.action == "dry"
    assert d.dry_active is True


def test_category_two_keeps_60_default() -> None:
    d = humidity_decide(
        rh=52.0, too_warm=False, in_deadband=True, can_dry=True, category=Category.II
    )
    assert d.action == "idle"


def test_category_three_raises_ceiling_to_70() -> None:
    d = humidity_decide(
        rh=65.0, too_warm=False, in_deadband=True, can_dry=True, category=Category.III
    )
    assert d.action == "idle"


def test_rh_high_for_category_mapping() -> None:
    assert rh_high_for_category(Category.I) == 50.0
    assert rh_high_for_category(Category.II) == 60.0
    assert rh_high_for_category(Category.III) == 70.0
    assert rh_high_for_category(None) == 60.0  # Cat II fallback


def test_absolute_cap_triggers_when_rh_acceptable() -> None:
    # RH 55 < Cat II 60, but 12.5 g/kg exceeds the 12 g/kg absolute ceiling.
    d = humidity_decide(
        rh=55.0, too_warm=False, in_deadband=True, can_dry=True, abs_humidity_gkg=12.5
    )
    assert d.action == "dry"
    assert "g/kg" in d.reason


def test_absolute_cap_hysteresis_holds() -> None:
    # latched, RH below its exit (55) but w still >= abs exit (11) -> keep drying
    d = humidity_decide(
        rh=50.0,
        too_warm=False,
        in_deadband=True,
        can_dry=True,
        prev_dry_active=True,
        abs_humidity_gkg=11.5,
    )
    assert d.action == "dry"


def test_absolute_cap_hysteresis_exits() -> None:
    d = humidity_decide(
        rh=50.0,
        too_warm=False,
        in_deadband=True,
        can_dry=True,
        prev_dry_active=True,
        abs_humidity_gkg=10.5,
    )
    assert d.action == "idle"
    assert d.dry_active is False


def test_absolute_cap_never_overrides_dry_guard() -> None:
    # RH below the dry-guard floor wins even if absolute moisture is high.
    d = humidity_decide(
        rh=35.0, too_warm=False, in_deadband=True, can_dry=True, abs_humidity_gkg=13.0
    )
    assert d.action == "dry_guard"


def test_too_warm_precedes_absolute_cap() -> None:
    d = humidity_decide(
        rh=55.0, too_warm=True, in_deadband=False, can_dry=True, abs_humidity_gkg=13.0
    )
    assert d.action == "cool"


# --- Option 1: EN 16798-1 comfort-vs-health split (occupancy gate) ----------
# The category RH ceiling is a COMFORT criterion -> occupancy-gated. The
# absolute 12 g/kg cap is health/building protection -> never gated.


def test_unoccupied_defers_relative_ceiling() -> None:
    # RH over the Cat II ceiling but the room is empty: comfort criterion not
    # enforced, and no absolute load -> no dehumidification.
    d = humidity_decide(
        rh=62.0, too_warm=False, in_deadband=True, can_dry=True, occupied=False
    )
    assert d.action == "idle"
    assert d.dry_active is False
    assert "unoccupied" in d.reason


def test_unoccupied_cat_i_defers_the_observed_office_case() -> None:
    # The live office case: Cat I, RH just over 50, empty room -> no dehumidify.
    d = humidity_decide(
        rh=52.0,
        too_warm=False,
        in_deadband=True,
        can_dry=True,
        category=Category.I,
        occupied=False,
    )
    assert d.action == "idle"


def test_unoccupied_releases_a_relative_only_latch() -> None:
    # Was drying on the relative ceiling; the room empties -> the comfort latch
    # releases (no absolute load to hold it).
    d = humidity_decide(
        rh=57.0,
        too_warm=False,
        in_deadband=True,
        can_dry=True,
        prev_dry_active=True,
        occupied=False,
    )
    assert d.action == "idle"
    assert d.dry_active is False


def test_unoccupied_absolute_backstop_still_fires() -> None:
    # Health/building protection: 12.5 g/kg dehumidifies even in an empty room.
    d = humidity_decide(
        rh=55.0,
        too_warm=False,
        in_deadband=True,
        can_dry=True,
        abs_humidity_gkg=12.5,
        occupied=False,
    )
    assert d.action == "dry"
    assert d.dry_active is True
    assert "g/kg" in d.reason


def test_unoccupied_absolute_latch_still_holds() -> None:
    # A latched absolute-driven dry is not released by vacancy.
    d = humidity_decide(
        rh=50.0,
        too_warm=False,
        in_deadband=True,
        can_dry=True,
        prev_dry_active=True,
        abs_humidity_gkg=11.5,
        occupied=False,
    )
    assert d.action == "dry"


def test_occupied_still_enforces_relative_ceiling() -> None:
    # The default/occupied path is unchanged: relative ceiling enforced.
    d = humidity_decide(
        rh=62.0, too_warm=False, in_deadband=True, can_dry=True, occupied=True
    )
    assert d.action == "dry"
    assert d.dry_active is True
