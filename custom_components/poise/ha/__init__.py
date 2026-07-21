"""Home-Assistant adapter layer for the coordinator refactoring (plan phase 4+).

``input_reader`` is the single READING adapter: every ``hass.states.get``
(and the device-guard registry discovery) lives here. ``actuator_executor``
holds the WRITING call primitives and ``forecast_provider`` the forecast
fetch + TTL cache (both phase 5A; try boundaries/stamps stay in the
coordinator until 5B). ``presenter`` (phase 8, S3) flattens
``TickOutcome.data`` into ``coordinator.data`` — hass-free display glue with
a binding object-identity contract, see its module docstring. A later phase
adds ``health_reporter``.

These modules belong to the HA adapter layer and are therefore covered by
the HA-runtime integration gate (``coverage_glue.ini``), not the pure-core
gate.
See docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md.
"""
