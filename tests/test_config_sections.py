"""Tests for the pure flatten/nest helpers of the sectioned options flow."""

from __future__ import annotations

from custom_components.poise.config_sections import flatten_sections, nest_by_section

SECTIONS = {
    "comfort": ("comfort_base", "category"),
    "schedule": ("setback_delta", "optimal_start"),
    "advanced": ("cool_hard_cap_c", "operative_input"),
}


def test_flatten_spreads_sections_and_keeps_plain_keys() -> None:
    submitted = {
        "comfort": {"comfort_base": 22.0, "category": "II"},
        "schedule": {"setback_delta": 3.0, "optimal_start": True},
        "advanced": {"cool_hard_cap_c": 26.0, "operative_input": False},
    }
    flat = flatten_sections(submitted, SECTIONS.keys())
    assert flat == {
        "comfort_base": 22.0,
        "category": "II",
        "setback_delta": 3.0,
        "optimal_start": True,
        "cool_hard_cap_c": 26.0,
        "operative_input": False,
    }


def test_flatten_copies_unknown_top_level_keys() -> None:
    # a non-section top-level key (defensive) is copied verbatim, not dropped
    flat = flatten_sections({"comfort": {"category": "I"}, "stray": 5}, SECTIONS.keys())
    assert flat == {"category": "I", "stray": 5}


def test_nest_groups_present_fields_only() -> None:
    values = {"comfort_base": 21.0, "category": "III", "setback_delta": 2.0}
    nested = nest_by_section(values, SECTIONS)
    assert nested == {
        "comfort": {"comfort_base": 21.0, "category": "III"},
        "schedule": {"setback_delta": 2.0},
    }
    # a section with no present fields is omitted -> its fields show schema defaults
    assert "advanced" not in nested


def test_round_trip_flat_to_nested_to_flat() -> None:
    flat = {"comfort_base": 20.5, "category": "II", "optimal_start": False}
    nested = nest_by_section(flat, SECTIONS)
    assert flatten_sections(nested, SECTIONS.keys()) == flat
