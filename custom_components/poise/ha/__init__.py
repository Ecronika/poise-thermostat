"""Home-Assistant adapter layer for the coordinator refactoring (plan phase 4+).

``input_reader`` is the single READING adapter: every ``hass.states.get``
(and the device-guard registry discovery) lives here. ``actuator_executor``
holds the WRITING call primitives and ``forecast_provider`` the forecast
fetch + TTL cache (both phase 5A; try boundaries/stamps stay in the
coordinator until 5B). ``presenter`` (phase 8, S3) flattens
``TickOutcome.data`` into ``coordinator.data`` — hass-free display glue with
a binding object-identity contract, see its module docstring.
``tick_orchestrator`` (step 3, S1) owns the whole per-tick program — the eight
tick methods and the 26 stages — so ``coordinator.py`` is left with the HA
coupling alone; its docstring holds the binding patch-surface and
dispatch-through-the-coordinator rules. ``health_reporter`` (step 3, S2) owns
the repair-issue surface — the transition-only ``issue()``, the ``emit()``
checkpoint the tick flow drives, the heating-failure ``notify_failure()`` and
the setup-time ``validate_configured_ext_temp()``; ``_active_issues`` stays a
coordinator attribute on purpose (``async_bootstrap`` rebinds it), see that
module's docstring.

These modules belong to the HA adapter layer and are therefore covered by
the HA-runtime integration gate (``coverage_glue.ini``), not the pure-core
gate.
See docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md.
"""
