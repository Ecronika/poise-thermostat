"""Home-Assistant adapter layer around the hass-free runtime.

``input_reader`` is the single READING adapter: every ``hass.states.get``
(and the device-guard registry discovery) lives here. ``actuator_executor``
holds the WRITING call primitives and the ``run_*`` effect sequences (which
own the per-effect try boundaries and the boundary logging; the stamps stay
with the coordinator's ``commit_execution``). ``forecast_provider`` owns the
forecast fetch + TTL cache. ``presenter`` flattens ``TickOutcome.data`` into
``coordinator.data`` — hass-free display glue with a binding object-identity
contract, see its module docstring. ``tick_orchestrator`` owns the whole
per-tick program — the tick methods and the stage methods — so
``coordinator.py`` is left with the HA coupling alone; its docstring holds
the binding patch-surface and dispatch-through-the-coordinator rules.
``health_reporter`` owns the repair-issue surface — the transition-only
``issue()``, the ``emit()`` checkpoint the tick flow drives, the
heating-failure ``notify_failure()`` and the setup-time
``validate_configured_ext_temp()``. Since S.3 it borrows nothing from the
coordinator: it holds the ``IssueLedger`` (whose content ``async_bootstrap``
re-adopts IN PLACE, which is what made the old backreference necessary), the
entry identity, and it reports the ext-temp verdict instead of writing it.

These modules belong to the HA adapter layer and are therefore covered by
the HA-runtime integration gate (``coverage_glue.ini``), not the pure-core
gate.
"""
