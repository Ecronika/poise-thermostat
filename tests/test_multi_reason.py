from __future__ import annotations

from custom_components.poise.multi.reason import (
    BlockingCause,
    FallbackCause,
    ReasonCode,
    ResolveReason,
    Severity,
    severity_of,
)


def test_reason_codes_are_stable_strings() -> None:
    assert ReasonCode.THERMAL_HEAT_PRIORITY.value == "thermal_heat_priority"
    assert ReasonCode.FAILOVER_PRIMARY_UNHEALTHY.value == "failover_primary_unhealthy"
    assert ReasonCode.HUMIDITY_NOOP.value == "humidity_noop"


def test_resolve_reason_four_fields_default_empty() -> None:
    r = ResolveReason(ReasonCode.NO_DEMAND)
    assert r.selected_source is None
    assert r.blocked == ()
    assert r.fallback is None
    assert dict(r.details) == {}


def test_severity_is_derived_not_stored() -> None:
    assert severity_of(ReasonCode.THERMAL_HEAT_PRIORITY) is Severity.INFO
    assert severity_of(ReasonCode.FAILOVER_PRIMARY_UNHEALTHY) is Severity.WARN
    assert ResolveReason(ReasonCode.NO_CAPABLE_SOURCE).severity is Severity.WARN


def test_blocking_and_fallback_enums_present() -> None:
    assert BlockingCause.COMPRESSOR_MIN_OFF_ACTIVE.value == "compressor_min_off_active"
    assert FallbackCause.PRIMARY_UNHEALTHY.value == "primary_unhealthy"
