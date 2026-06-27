"""Stable Reason / Diagnostics contract for multi-actuator arbitration (ADR-0046 §11).

The *codes* here are the API contract — tests, diagnostics and support depend on
them; they are English/technical and must stay stable. Human-readable text lives
in ``strings.json`` (localisable, not contract); Card chips are UI hints only.
``ResolveReason`` carries the four orthogonal fields the design fixes from P0:
selected source, reason, blocking causes, and fallback cause.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReasonCode(Enum):
    """Why a source/action was chosen. Stable string values = the contract."""

    NO_DEMAND = "no_demand"
    NO_CAPABLE_SOURCE = "no_capable_source"
    THERMAL_HEAT_PRIORITY = "thermal_heat_priority"
    THERMAL_COOL_PRIORITY = "thermal_cool_priority"
    THERMAL_HEAT_COST_PREFERRED = "thermal_heat_cost_preferred"
    THERMAL_COOL_COST_PREFERRED = "thermal_cool_cost_preferred"
    BOOST_SECONDARY_ADDED = "boost_secondary_added"
    FAILOVER_PRIMARY_UNHEALTHY = "failover_primary_unhealthy"
    COMPRESSOR_MIN_OFF_ACTIVE = "compressor_min_off_active"
    DEVICE_EXTERNAL_OVERRIDE = "device_external_override"
    SHARED_RESOURCE_BUSY = "shared_resource_busy"
    STANDBY = "standby"
    # Humidity / air-movement codes are contract-stable from P0 even though the
    # resolvers are no-ops until P4-P7 (ADR-0046 §4).
    HUMIDITY_NOOP = "humidity_noop"
    AIR_MOVEMENT_NOOP = "air_movement_noop"
    AIR_MOVEMENT_CREDIT_APPLIED = "air_movement_credit_applied"
    FREE_COOLING_BLOCKED_OUTDOOR_MORE_HUMID = "free_cooling_blocked_outdoor_more_humid"
    AC_DRY_BLOCKED_WOULD_OVERCOOL = "ac_dry_blocked_would_overcool"
    HUMIDIFY_CAPPED_CONDENSATION_RISK = "humidify_capped_condensation_risk"


class BlockingCause(Enum):
    """What prevented an otherwise-eligible candidate from being chosen."""

    DEVICE_UNHEALTHY = "device_unhealthy"
    DEVICE_UNAVAILABLE = "device_unavailable"
    COMPRESSOR_MIN_OFF_ACTIVE = "compressor_min_off_active"
    MODE_HOLD_ACTIVE = "mode_hold_active"
    EXTERNAL_OVERRIDE = "external_override"
    SHARED_RESOURCE_BUSY = "shared_resource_busy"
    WRONG_DIRECTION = "wrong_direction"


class FallbackCause(Enum):
    """Why the preferred source was not the one selected."""

    PRIMARY_UNHEALTHY = "primary_unhealthy"
    PRIMARY_UNAVAILABLE = "primary_unavailable"
    PRIMARY_LOCKED = "primary_locked"
    NO_PREFERRED_SOURCE = "no_preferred_source"


class Severity(Enum):
    INFO = "info"
    WARN = "warn"


_WARN_CODES = frozenset(
    {
        ReasonCode.FAILOVER_PRIMARY_UNHEALTHY,
        ReasonCode.DEVICE_EXTERNAL_OVERRIDE,
        ReasonCode.HUMIDIFY_CAPPED_CONDENSATION_RISK,
        ReasonCode.NO_CAPABLE_SOURCE,
    }
)


def severity_of(reason: ReasonCode) -> Severity:
    """Severity is derived from the code, never stored as part of the contract."""
    return Severity.WARN if reason in _WARN_CODES else Severity.INFO


@dataclass(frozen=True, slots=True)
class ResolveReason:
    """The four orthogonal diagnostics fields fixed from P0 (ADR-0046 §11)."""

    reason: ReasonCode
    selected_source: str | None = None
    blocked: tuple[BlockingCause, ...] = ()
    fallback: FallbackCause | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def severity(self) -> Severity:
        return severity_of(self.reason)
