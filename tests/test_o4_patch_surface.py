"""Plan O.4 — proof that every migrated fault-injection patch still BITES.

Refactoring plan: ``docs/Konzepte/2026-08-16_Refactoring-Plan_tick-
orchestrator.md``, step "O.4 — Patch-Fläche aus dem Produktivcode entfernen".

O.4 moved nine fault-injection functions off the ``coordinator`` module's
namespace (where ``ha/tick_orchestrator.py`` used to resolve them through a
``_CoordinatorGlobals`` proxy) onto their OWNING module, called as
``owner_module.name(...)`` so the lookup happens at CALL time.  The rule is:

    **Patch where the name is looked up, not where it is defined.**

That migration has exactly one dangerous failure mode, and it is SILENT: if a
call site is written as ``from ..owner import name`` instead, the function
object is bound at IMPORT time, a patch on the owner module changes nothing,
and every fault-injection test keeps passing while injecting nothing.  A green
suite would then mean the opposite of what it looks like.

This file is the standing counter-proof.  For each of the nine names it
installs the real patch and observes a sentinel effect — a spy that can only
record a call if the production code resolved the name through the patched
module attribute.  ``test_from_import_binding_is_not_patchable_at_the_owner``
is the anti-vacuum control: ``shading_target_position`` is called in the SAME
expression as the (owner-resolved) ``predict_peak_operative`` but is a plain
from-import, so patching its owner must record NOTHING.  If the nine
assertions below ever went vacuous, that control would go green too.

``test_coordinator_module_no_longer_carries_the_patch_surface`` closes the
other half: the pre-O.4 targets are gone from ``coordinator``, so a leftover
``patch("custom_components.poise.coordinator.is_frozen")`` fails loudly with
AttributeError instead of quietly patching a name nobody reads.
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_HUMIDITY_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
)

# The nine migrated names -> the dotted path a test patches them at. The value
# is the OWNER module plus the REAL name there: two of them used to travel
# under an alias on the coordinator module (``psychro_dewpoint`` -> ``dewpoint``
# and ``comfort_decide`` -> ``decide``), and the alias is NOT a patch target.
_PATCH_TARGETS: dict[str, str] = {
    "is_frozen": "custom_components.poise.safety.sensor_watchdog.is_frozen",
    "ingest_temperature": "custom_components.poise.ingestion.ingest_temperature",
    "effective_window_open": (
        "custom_components.poise.control.window_auto.effective_window_open"
    ),
    "dewpoint": "custom_components.poise.estimation.psychrometrics.dewpoint",
    "decide": "custom_components.poise.comfort.dual_setpoint.decide",
    "resolve_write_target": (
        "custom_components.poise.control.tick_resolve.resolve_write_target"
    ),
    "humidity_decide": "custom_components.poise.comfort.humidity.humidity_decide",
    "predict_peak_operative": (
        "custom_components.poise.control.cover_shading.predict_peak_operative"
    ),
    "plan_preheat": "custom_components.poise.control.optimal_start.plan_preheat",
}

# What ``coordinator.py`` imported with a ``noqa: F401`` before O.4: the nine
# above plus the six that were only ever DOCUMENTED as patch surface. None of
# them may be reachable on the coordinator module any more.
_FORMER_COORDINATOR_NAMES: tuple[str, ...] = (
    "comfort_decide",
    "effective_window_open",
    "evaluate_thermal_shadow",
    "humidity_decide",
    "ingest_temperature",
    "is_frozen",
    "mode_adopt_reason",
    "plan_preheat",
    "predict_peak_operative",
    "psychro_dewpoint",
    "resolve_desired_mode",
    "resolve_write_target",
    "setpoint_adopt_reason",
    "shading_target_position",
    "_lifecycle",
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
    # A configured humidity sensor is what makes the dewpoint cap run at all
    # (``stage_safety_floors`` skips it when ``rh is None``), and the window
    # contact keeps the observe stage on its configured path.
    CONF_HUMIDITY_SENSOR: "sensor.room_rh",
    CONF_WINDOW_SENSOR: "binary_sensor.window",
}


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _resolve(target: str) -> Any:
    """The live object behind a dotted patch target, resolved the same way
    ``unittest.mock.patch`` resolves it. Used to build a WRAPPING spy, so the
    tick under test keeps running the real implementation.
    """
    module_path, _, attribute = target.rpartition(".")
    module = importlib.import_module(module_path)
    assert hasattr(module, attribute), (
        f"{target}: {module_path} has no attribute {attribute!r} - the patch "
        f"target is stale, which would make every test in this file vacuous."
    )
    return getattr(module, attribute)


def _healthy_states(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "18.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "cool", "dry", "fan_only", "off"],
            "temperature": 19.0,
            "current_temperature": 18.0,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set(
        "sensor.room_rh", "55", {"device_class": "humidity", "unit_of_measurement": "%"}
    )
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})


async def _setup(hass: HomeAssistant) -> Any:
    """One healthy zone whose tick reaches all nine call sites. Returns the
    coordinator; the service recorders are re-armed after setup so this file's
    ticks never reach the real climate handlers."""
    _healthy_states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data
    coord.runtime.clock = _FakeClock(1000.0)
    return coord


async def _tick(hass: HomeAssistant, coord: Any) -> None:
    coord.runtime.clock.t += 60.0
    await coord.async_refresh()
    await hass.async_block_till_done()


@pytest.mark.parametrize("name", sorted(_PATCH_TARGETS))
async def test_owner_module_patch_reaches_the_tick(
    hass: HomeAssistant, name: str
) -> None:
    """The O.4 obligation, one case per migrated name: a patch installed on the
    OWNING module is what the tick actually calls.

    The spy wraps the real function, so the tick behaves exactly as it would
    unpatched and the only observable is the recorded call — which can happen
    only if the orchestrator resolved the name through the patched module
    attribute at call time. A call site rewritten as ``from ..owner import
    name`` would bind at import time and leave this at zero.
    """
    target = _PATCH_TARGETS[name]
    coord = await _setup(hass)
    spy = MagicMock(wraps=_resolve(target))

    with patch(target, spy):
        await _tick(hass, coord)

    assert coord.last_update_success is True, (
        f"{target}: the reference tick failed, so a zero call count below "
        f"would be ambiguous. Fix the fixture, not the assertion."
    )
    assert spy.call_count >= 1, (
        f"{target} was patched but never called: the tick resolved the name "
        f"somewhere else. Plan O.4 requires the owner-module form "
        f"(``import owner`` + ``owner.{name}(...)``); a ``from owner import "
        f"{name}`` binds at IMPORT time and makes this patch a no-op while "
        f"every fault-injection test stays green."
    )


async def test_from_import_binding_is_not_patchable_at_the_owner(
    hass: HomeAssistant,
) -> None:
    """Anti-vacuum control for the nine cases above.

    ``evaluate_cover_shadow`` receives BOTH cover kernels in the same call:
    ``predict_peak_operative`` through its owner module (patchable, one of the
    nine) and ``shading_target_position`` as a plain from-import in
    ``ha/phase_shadow.py`` (never patched by any test since O.4). Patching
    the owner of the second one must therefore record NOTHING even though the
    segment demonstrably ran — which is exactly the silent failure mode the
    nine assertions above are there to detect. If this ever recorded a call,
    the two import styles would be indistinguishable and those assertions would
    prove nothing.
    """
    coord = await _setup(hass)
    reached = MagicMock(wraps=_resolve(_PATCH_TARGETS["predict_peak_operative"]))
    from_import_target = (
        "custom_components.poise.control.cover_shading.shading_target_position"
    )
    ignored = MagicMock(wraps=_resolve(from_import_target))

    with (
        patch(_PATCH_TARGETS["predict_peak_operative"], reached),
        patch(from_import_target, ignored),
    ):
        await _tick(hass, coord)

    assert coord.last_update_success is True
    assert reached.call_count >= 1, (
        "the cover shadow segment did not run this tick, so the control below "
        "would be vacuously green - re-seed the fixture."
    )
    assert ignored.call_count == 0, (
        "patching the owner of a FROM-IMPORTED name suddenly has an effect. "
        "Either phase_shadow switched shading_target_position to the "
        "owner-module form (then move it into _PATCH_TARGETS and give it a "
        "'the patch bites' case), or this control lost its meaning."
    )


def test_coordinator_module_no_longer_carries_the_patch_surface() -> None:
    """Plan O.4: the 15 ``noqa: F401`` re-exports are gone from
    ``coordinator``, so a pre-O.4 patch target fails LOUDLY.

    ``unittest.mock.patch`` raises ``AttributeError`` for a name the target
    module does not have, so any patch site missed by the migration turns into
    a red test rather than a green one that injects nothing.
    """
    coordinator = importlib.import_module("custom_components.poise.coordinator")
    leftovers = [n for n in _FORMER_COORDINATOR_NAMES if hasattr(coordinator, n)]
    assert not leftovers, (
        f"custom_components.poise.coordinator still exposes {leftovers} - O.4 "
        f"removed that re-export surface. A name back on this module is a "
        f"second, silent patch target."
    )


def test_every_patch_target_resolves_and_is_unique() -> None:
    """Guard on the table itself: nine distinct names, nine distinct targets,
    each one importable. A typo in a dotted path would otherwise turn a
    parametrised case into a collection error - or worse, a stale target could
    quietly duplicate another and hide a missing case.
    """
    assert len(_PATCH_TARGETS) == 9
    assert len(set(_PATCH_TARGETS.values())) == 9
    for name, target in _PATCH_TARGETS.items():
        assert target.rpartition(".")[2] == name
        _resolve(target)
