"""Presenter — flattens ``TickOutcome.data`` into ``coordinator.data``.

The ``_tick_data`` ASSEMBLY remains a finalize stage in the coordinator
(``_stage_assemble_tick_data``) because the trace consumes the assembled dict
BEFORE the ``TickOutcome`` exists — moving the assembly behind ``present()``
would reorder it across the trace append.  This module therefore holds only
the two hass-free presentation primitives:

* ``present`` — flattens both outcome data forms into the ``coordinator.data``
  dict.
* ``iso_utc`` — the ISO-8601 display format (ADR-0059 §4) the assembly stage
  uses for ``override_expires_at``/``boost_expires_at``.

There is no presenter state, so these are module functions rather than a class.

OBJECT-IDENTITY CONTRACT (binding): for the available form ``present`` returns
``outcome.diagnostics`` — THE SAME dict object the assembly stage built, the
trace consumed and ``TickOutcome.diagnostics`` carries.  ``_async_update_data``
then attaches ``tick_ms``/``tick_ms_ewma``/``tick_ms_max``/``tick_over_budget``
onto that same object, which becomes ``coordinator.data``.  The presenter must
NEVER copy or rebuild the available payload; the full chain is
``_tick_data`` ≡ trace input ≡ ``TickOutcome.diagnostics`` ≡ ``present()``
return ≡ ``_run_once`` return ≡ ``coordinator.data``
(pinned by ``tests/integration/test_phase8_presenter.py``).

KEY SHRINK (pinned behaviour): the available key set is NOT schema-stable —
three degradations shrink it silently, all three served through this same
identity chain: (1) a shadow-domain failure falls back to the neutral
``shadow_objs`` WITHOUT the two ``compressor_gate_*`` keys (156 → 154,
``test_phase0_fault_shadow_domain``); (2) an outcome-collector failure leaves
the 7 default keys instead of the full collector set (``ca_*``/``ref_offset*``/
``tau_*``/``cool_sp_compensated`` vanish); (3) a climate-band failure yields
``climate_diag == {}`` (all climate-band keys vanish,
``test_phase0_fault_climate_domain``).

UNAVAILABLE MINIMAL FORMS: each a FRESH dict, exactly ``{"available": False}``
or ``{"available": False, "unavailable_safe": True}`` (``unavailable_safe`` is
unconditional once the safe state engaged — independent of plan resolution and
dispatch success).  No ``tick_ms*`` keys: the timing attach gates on
``available`` (pinned by ``test_phase0_data_contract``).

Hass-free but HA-layer owned (display formatting for the entity/hub surface);
measured by the GLUE coverage gate (``coverage_glue.ini`` includes
``*/ha/*.py``), mypy --strict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from ..runtime.tick_result import TickOutcome, UnavailableTickData


def iso_utc(ts: float | None) -> str | None:
    """UTC ISO-8601 string for a wall-clock epoch, or None (ADR-0059 §4 attrs)."""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts is not None else None


def present(outcome: TickOutcome) -> dict[str, Any]:
    """Flatten ``outcome.data`` into the ``coordinator.data`` dict.

    Unavailable stays the minimal contract — the ``unavailable_safe`` key
    exists only once the safe state engaged, and ``_async_update_data``
    attaches ``tick_ms*`` only to available payloads (it keys on
    ``available``).  For the available form the full payload travels as
    ``outcome.diagnostics`` (the exact dict the trace consumed); it is returned
    as the SAME object (see the module docstring's identity contract).
    """
    if isinstance(outcome.data, UnavailableTickData):
        if outcome.data.unavailable_safe:
            return {"available": False, "unavailable_safe": True}
        return {"available": False}
    return cast("dict[str, Any]", outcome.diagnostics)
