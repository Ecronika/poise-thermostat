from __future__ import annotations

from custom_components.poise.contracts import Source
from custom_components.poise.ingestion import RawSample, ingest_temperature


def test_measured_fuses_available_sensors() -> None:
    reading = ingest_temperature([RawSample(20.0, 0.0), RawSample(22.0, 0.0)], now=0.0)
    assert reading.source is Source.MEASURED
    assert reading.value == 21.0
    assert reading.sensor_ok


def test_implausible_samples_are_dropped() -> None:
    reading = ingest_temperature([RawSample(999.0, 0.0), RawSample(20.0, 0.0)], now=0.0)
    assert reading.source is Source.MEASURED
    assert reading.value == 20.0


def test_derived_falls_back_to_last_good() -> None:
    reading = ingest_temperature(
        [RawSample(None, 0.0, available=False)], now=5.0, last_good=19.5
    )
    assert reading.source is Source.DERIVED
    assert reading.value == 19.5
    assert not reading.sensor_ok


def test_default_when_no_history() -> None:
    reading = ingest_temperature([], now=0.0, default=18.0)
    assert reading.source is Source.DEFAULT
    assert reading.value == 18.0
    assert not reading.sensor_ok


def test_parse_finite_rejects_nan_inf_and_junk() -> None:
    from custom_components.poise.ingestion import parse_finite

    assert parse_finite("nan") is None  # C1: NaN must be rejected at the boundary
    assert parse_finite("inf") is None
    assert parse_finite("-inf") is None
    assert parse_finite(float("nan")) is None
    assert parse_finite(float("inf")) is None
    assert parse_finite(None) is None
    assert parse_finite("abc") is None
    assert parse_finite("21.5") == 21.5
    assert parse_finite(22) == 22.0
