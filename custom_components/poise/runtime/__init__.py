"""Typed contracts for the coordinator refactoring (plan phase 1).

This package introduces the data types the future ``ZoneRuntime`` will
exchange with the HA adapter layer: input snapshots (``tick_inputs``),
tick plans/outcomes and execution reports (``tick_result``), grouped
runtime state (``state``), parsed zone configuration (``config``) and
the listener reaction registry (``input_registry``).

Phase-1 scope: type definitions only — nothing in ``coordinator.py``
imports these modules yet, so introducing them cannot change behaviour.
See docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md.
"""
