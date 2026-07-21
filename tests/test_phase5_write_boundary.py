"""Phase-5A write-boundary grep gate (refactoring plan, phase 5A).

Pins the module boundary this phase established: ``ha/actuator_executor.py``
holds the effect-call primitives (the single WRITING adapter of the tick) and
``ha/forecast_provider.py`` the one blocking READ (``weather.get_forecasts``,
``return_response`` — the DoD-documented exception). ``coordinator.py`` must
contain no direct service dispatch (``hass.services.async_call`` /
``….services.async_call(…`` through any alias) and no direct
``actuator_mod.write`` — every effect call goes through the executor
primitives; try boundaries, log texts and stamps stay in the coordinator
until 5B.

Pure source-text test: no Home Assistant import, runs in the py3.10 pure gate.

The tree-wide check carries an explicit, documented exception list — every
entry is either the writing adapter layer itself or a module deliberately OUT
of phase-5A scope. Shrinking this list is the job of later phases; growing it
would mean a new direct write slipped in and must fail here.
"""

from __future__ import annotations

from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "poise"

# The gate strings. ``.services.async_call(`` (leading dot) also catches a
# dispatch through an aliased hass reference (``self.hass.…`` / ``self._hass.…``);
# ``actuator_mod.write`` catches the coordinator's old module-alias dispatch.
WRITE_PATTERNS = (
    "hass.services.async_call",
    ".services.async_call(",
    "actuator_mod.write",
)

# file (posix path relative to custom_components/poise) -> why it may contain
# a gate string. Goal state: only the ha/ entries remain (later phases).
ALLOWED = {
    "ha/actuator_executor.py": (
        "the single writing HA adapter itself — every effect-call primitive "
        "(set_hvac_mode / write_setpoint via actuator_mod.write / "
        "select_option / set_number) lives here by design (plan phase 5A)"
    ),
    "ha/forecast_provider.py": (
        "weather.get_forecasts with return_response — the tick's one "
        "blocking=True call and a READ, not an effect write (DoD-documented "
        "exception, plan phase 5A / Befund 5)"
    ),
    "actuator.py": (
        "the ADR-0013 single-writer choke point the executor dispatches "
        "through (``actuator_mod.write`` translates one ActuatorCommand into "
        "exactly one service call) — the primitive's own body, not a bypass"
    ),
    "hub_coordinator.py": (
        "system-hub coordinator — explicitly NOT part of phase 5A (the plan "
        "refactors the ZONE coordinator; the hub keeps its boiler service "
        "calls until its own phase)"
    ),
    "__init__.py": (
        "entry setup/teardown lifecycle writes (boiler OFF, actuator park, "
        "TRV sensor-source restore — also delegated to from the "
        "coordinator's _validate_configured_ext_temp and config_flow) — "
        "deliberate one-shot writes with their own blocking semantics, "
        "outside the tick's write boundary"
    ),
}


def _hits(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [p for p in WRITE_PATTERNS if p in text]


def test_coordinator_has_no_direct_service_calls() -> None:
    """coordinator.py: zero direct dispatches — the exception list is EMPTY."""
    assert _hits(COMPONENT / "coordinator.py") == []


def test_executor_is_the_only_writing_module() -> None:
    """No module outside the exception list contains a gate string."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(COMPONENT.rglob("*.py")):
        rel = path.relative_to(COMPONENT).as_posix()
        if rel in ALLOWED:
            continue
        found = _hits(path)
        if found:
            offenders[rel] = found
    assert offenders == {}, (
        "direct HA service dispatches outside ha/actuator_executor.py — route "
        f"them through the executor primitives (plan phase 5A): {offenders}"
    )


def test_exception_list_is_not_stale() -> None:
    """Every allowed file still needs its exception (and still exists).

    The moment a later phase cleans one of these up, its entry must be
    deleted here so the gate tightens instead of silently rotting.
    """
    for rel, why in ALLOWED.items():
        path = COMPONENT / rel
        assert path.is_file(), f"exception entry for a missing file: {rel}"
        assert _hits(path), f"{rel} no longer needs its exception ({why})"
