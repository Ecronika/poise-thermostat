from __future__ import annotations

import dataclasses

import pytest

from custom_components.poise.contracts import Bound, ComfortCorridor, Reading, Source


def test_reading_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        Reading(20.0, "°C", Source.MEASURED, 1.5, 0.0)


def test_reading_is_frozen() -> None:
    reading = Reading(20.0, "°C", Source.MEASURED, 0.7, 0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        reading.value = 21.0  # type: ignore[misc]


def _corridor() -> ComfortCorridor:
    return ComfortCorridor(
        lower=(Bound(7.0, "frost"), Bound(19.0, "mold")),
        upper=(Bound(30.0, "device_max"), Bound(26.0, "cool")),
        target=21.0,
    )


def test_binding_bounds_are_max_lower_min_upper() -> None:
    corridor = _corridor()
    assert corridor.binding_lower().cause == "mold"
    assert corridor.binding_upper().cause == "cool"


@pytest.mark.parametrize(
    ("value", "expected", "cause"),
    [(18.0, 19.0, "mold"), (21.0, 21.0, None), (28.0, 26.0, "cool")],
)
def test_clamp_respects_binding_corridor(
    value: float, expected: float, cause: str | None
) -> None:
    got, got_cause = _corridor().clamp(value)
    assert got == expected
    assert got_cause == cause
