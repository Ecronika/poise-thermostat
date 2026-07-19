"""Home-Assistant adapter layer for the coordinator refactoring (plan phase 4+).

``input_reader`` is the single READING adapter: every ``hass.states.get``
(and the device-guard registry discovery) lives here. Later phases add the
writing adapter (``actuator_executor``), ``forecast_provider``,
``health_reporter`` and ``presenter``.

These modules import Home Assistant and are therefore covered by the
HA-runtime integration gate, not the pure-core gate.
See docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md.
"""
