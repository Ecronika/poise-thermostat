"""Golden-trace helpers for the Phase-0 behaviour freeze, Testebene A (pure).

Plan reference: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md,
"Phase 0 - Verhalten einfrieren", Testebene A ("Exakte Golden-Tests (pure)")
and the checklist item "Golden Traces sichern (ADR-0011) + Referenz-Traces
einchecken (tests/golden/); Normalisierungs-Helfer fuer Ebene B".

Three responsibilities:

1. A deterministic *reference scenario* driven through the production pure
   pipeline via :func:`tests.harness.replay.simulate` (which uses a
   ``ManualClock`` internally, so the run is fully deterministic). All
   scenario, plant, and controller parameters are pinned explicitly here so
   the golden fixture stays stable even if library defaults move.

2. Byte-stable serialisation of the resulting ``TracePoint`` sequence as
   JSON lines: fixed field order (``t``, ``air``, ``setpoint``), floats
   rounded to :data:`FLOAT_PRECISION` decimals (``round`` + ``json.dumps``
   float repr is deterministic and absorbs last-ulp libm differences),
   compact separators, one ``\\n``-terminated line per tick.

3. :func:`normalize_semantic` - the Ebene-B pre-work normaliser: strips
   time/runtime fields (``t``, ``mono_ts``, wall timestamps, ``tick_ms*``,
   ``tick_over_budget``; plan line "B. Semantischer Trace-Vergleich") so two
   traces can be compared on control semantics only.

This module is covered by ``mypy --strict`` (pyproject ``files`` includes
``tests/harness``).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from custom_components.poise.controller import BangBangController

from .plant import RCPlant
from .replay import Scenario, TracePoint, simulate

#: Decimal places kept in the serialised golden trace. Six decimals are far
#: below any control-relevant resolution but coarse enough to absorb
#: platform last-ulp differences in ``math.exp``.
FLOAT_PRECISION: Final[int] = 6

#: Field names that carry time / runtime metadata, not control semantics.
#: ``t`` is the harness TracePoint clock; the rest mirror the coordinator
#: trace fields named by the plan for Ebene-B normalisation.
_NON_SEMANTIC_FIELDS: Final[frozenset[str]] = frozenset(
    {"t", "ts", "mono", "mono_ts", "wall", "wall_ts", "tick_over_budget"}
)

#: Field-name prefixes treated as runtime metadata (``tick_ms``,
#: ``tick_ms_budget``, ...).
_NON_SEMANTIC_PREFIXES: Final[tuple[str, ...]] = ("tick_ms",)


def reference_scenario() -> Scenario:
    """The pinned Phase-0 reference scenario (10 h winter, warm start).

    ``start_air`` sits above ``target + hysteresis``, so the trace opens in
    the idle regime (setpoint parked at the frost floor while the room
    coasts down), transitions into the hold band, and then settles into the
    steady on/off limit cycle at the target. Both arbitration outcomes
    (frost-floor setpoint and target setpoint) appear in the golden trace.

    Note: a cold start can never reach the idle branch with the Phase-0
    replay device model (it heats only while ``setpoint > air``, so the room
    cannot overshoot ``target + hysteresis``); the warm start is what makes
    the idle regime observable.
    """
    return Scenario(
        t_out=3.0,
        target=21.0,
        frost_floor=7.0,
        device_max=30.0,
        start_air=22.5,
        dt=60.0,
        steps=600,
    )


def reference_plant() -> RCPlant:
    """The pinned reference plant (values frozen, independent of defaults)."""
    return RCPlant(
        alpha=0.15 / 3600.0,
        full_power_rise=20.0,
        valve_deadband=0.0,
        valve_curve=1.0,
    )


def reference_controller() -> BangBangController:
    """The pinned Phase-0 reference controller (hysteresis frozen)."""
    return BangBangController(hysteresis=0.3)


def run_reference_scenario() -> list[TracePoint]:
    """Run the reference scenario through the production pure pipeline."""
    return simulate(reference_controller(), reference_scenario(), reference_plant())


def trace_to_records(trace: Sequence[TracePoint]) -> list[dict[str, object]]:
    """Convert TracePoints to plain records with stable field order.

    Insertion order is the serialisation order: ``t``, ``air``, ``setpoint``.
    Floats are rounded to :data:`FLOAT_PRECISION` decimals for repr-stability.
    """
    return [
        {
            "t": round(point.t, FLOAT_PRECISION),
            "air": round(point.air, FLOAT_PRECISION),
            "setpoint": round(point.setpoint, FLOAT_PRECISION),
        }
        for point in trace
    ]


def record_to_line(record: Mapping[str, object]) -> str:
    """Serialise one record as a compact JSON line (insertion-ordered keys)."""
    return json.dumps(dict(record), separators=(",", ":"), sort_keys=False)


def serialize_records(records: Iterable[Mapping[str, object]]) -> str:
    """Serialise records as JSON lines; every line is ``\\n``-terminated."""
    return "".join(record_to_line(record) + "\n" for record in records)


def serialize_trace(trace: Sequence[TracePoint]) -> str:
    """Serialise a TracePoint sequence as the canonical golden JSONL text."""
    return serialize_records(trace_to_records(trace))


def parse_jsonl(text: str) -> list[dict[str, object]]:
    """Parse golden JSONL text back into records (blank lines skipped)."""
    records: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"golden line is not a JSON object: {line!r}")
        records.append({str(key): value for key, value in obj.items()})
    return records


def normalize_semantic(
    records: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Strip time/runtime fields, keeping only control semantics (Ebene B).

    Removes exact names in :data:`_NON_SEMANTIC_FIELDS` and any field whose
    name starts with a :data:`_NON_SEMANTIC_PREFIXES` prefix. Everything
    else (mode, target, setpoints, duty, safety decisions, ...) is kept
    verbatim so it can be compared exactly.
    """
    normalized: list[dict[str, object]] = []
    for record in records:
        normalized.append(
            {
                key: value
                for key, value in record.items()
                if key not in _NON_SEMANTIC_FIELDS
                and not key.startswith(_NON_SEMANTIC_PREFIXES)
            }
        )
    return normalized
