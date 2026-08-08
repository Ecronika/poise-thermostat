"""ADR-0069 control-readiness predicates, pure.

Diagnosis and live control have different requirements: a PMV computed on an
ASSUMED 50 % RH is a fine estimate to display, but never a basis for an
active setpoint shift; a presence lane that fail-safes missing signals to
"present" protects heating comfort, but must never enable an elevated fan
stage.  These predicates are the control-side gates — the diagnostic signals
(``pmv_valid``, ``occupied``) keep their meaning untouched.
"""

from __future__ import annotations

from .presence import any_present


def pmv_control_ready(*, rh: float | None, pmv_valid: bool) -> bool:
    """All REAL inputs for an active PMV-based setpoint shift are present.

    ``rh`` must be an actual sensor value — the climate shadow substitutes
    50 % when it is missing, and ``pmv_validity()`` only checks the met/clo
    domain, so ``pmv_valid`` alone can be True without any humidity sensor.
    The live ±1-K offset (ADR-0054 Stufe 2) hangs exclusively on this
    predicate; ``pmv_valid`` stays the diagnostic criterion.
    """
    return rh is not None and pmv_valid


def presence_control_ready(occupancy: tuple[bool | None, ...]) -> bool:
    """A REAL room-occupancy signal is configured and currently resolvable.

    Readiness is not occupancy: a resolvable "nobody in the room" is ready.
    Nothing configured, or every configured entity unresolved (dead tracker),
    is NOT ready — the thermal fail-safe "assume present" must never enable
    an elevated fan stage (ADR-0068 guard).
    """
    return any_present(occupancy) is not None


def room_present(occupancy: tuple[bool | None, ...]) -> bool:
    """Confirmed room occupancy from the room lane — never the fail-safe.

    Elevated fan stages require ``presence_control_ready AND room_present``
    (ADR-0069): only a confirmed present counts; ``None`` (unresolved) and
    the schedule-derived ``occupied`` diagnostic do not.
    """
    return any_present(occupancy) is True
