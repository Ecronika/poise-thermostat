"""Tests for the precedence-explicit constraint solver (ADR-0035)."""

from __future__ import annotations

from custom_components.poise.constraints import (
    Constraint,
    ConstraintKind,
    resolve_constraints,
)
from custom_components.poise.contracts import Precedence

FLOOR = ConstraintKind.FLOOR
CAP = ConstraintKind.CAP


def _floor(v, cause="floor", p=Precedence.HEALTH):
    return Constraint(v, cause, FLOOR, p)


def _cap(v, cause="cap", p=Precedence.COMFORT):
    return Constraint(v, cause, CAP, p)


def test_within_bounds_is_free() -> None:
    res = resolve_constraints(21.0, [_floor(7.0), _cap(26.0)])
    assert res.value == 21.0 and res.binding is None


def test_floors_compose_to_maximum() -> None:
    res = resolve_constraints(18.0, [_floor(7.0, "frost"), _floor(19.0, "mould")])
    assert res.value == 19.0 and res.binding is not None
    assert res.binding.cause == "mould"


def test_caps_compose_to_minimum() -> None:
    res = resolve_constraints(
        30.0, [_cap(26.0, "norm_cap"), _cap(25.0, "device_max", Precedence.SAFETY)]
    )
    assert res.value == 25.0 and res.binding.cause == "device_max"


def test_inversion_resolved_by_precedence_health_over_comfort() -> None:
    # mould floor (HEALTH) above ASR cap (COMFORT) -> floor wins
    res = resolve_constraints(
        24.0, [_floor(27.0, "norm_floor", Precedence.HEALTH), _cap(26.0, "norm_cap")]
    )
    assert res.value == 27.0 and res.binding.cause == "norm_floor"


def test_inversion_device_max_safety_beats_health_floor() -> None:
    # physical device max (SAFETY) below a mould floor (HEALTH) -> device wins
    res = resolve_constraints(
        24.0,
        [
            _floor(22.0, "mould", Precedence.HEALTH),
            _cap(21.0, "device_max", Precedence.SAFETY),
        ],
    )
    assert res.value == 21.0 and res.binding.cause == "device_max"


def test_reports_binding_floor_and_cap() -> None:
    res = resolve_constraints(30.0, [_floor(7.0), _cap(26.0, "norm_cap")])
    assert res.cap is not None and res.cap.cause == "norm_cap"
    assert res.floor is not None and res.floor.value == 7.0


def test_no_constraints_returns_desired() -> None:
    res = resolve_constraints(21.0, [])
    assert res.value == 21.0 and res.binding is None
