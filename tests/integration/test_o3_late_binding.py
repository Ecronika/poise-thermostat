"""Plan O.3: prove that every late-binding port really binds LATE.

Plan reference: ``docs/Konzepte/2026-08-16_Refactoring-Plan_tick-orchestrator.md``,
sections 4.4 and O.3.

Six targets must resolve through the coordinator INSTANCE on every call,
because fault-injection tests replace them there long after the coordinator
(and with it the orchestrator and its port adapter) was constructed:

* five coordinator instance methods — ``_write_unavailable_safe_state``,
  ``_maybe_record_trace``, ``_forecast_outdoor``, ``commit_execution``,
  ``_maybe_save``;
* one method of a COLLABORATOR — ``HealthReporter.emit``, resolved through
  ``coordinator._health``.

Until O.3 the rule was carried by comment discipline alone: the adapter code
happened to write ``self._c.<name>(...)`` and a module docstring said it must
stay that way. A frozen dataclass of bound methods, or a plain
``self._emit = coordinator._health.emit`` in ``__init__``, would have kept
every existing test GREEN while silently making the patch points inert. Each
test below therefore installs a replacement AFTER setup and asserts a sentinel
effect that only the replacement can produce.

THE SIXTH IS NOT LIKE THE OTHER FIVE. ``emit`` belongs to the
``HealthReporter``, which declares ``__slots__`` — so it cannot be replaced on
the reporter instance at all. Its substitution form is "replace the reporter on
the coordinator", and ``test_health_emit_resolves_through_the_reporter``
asserts both halves: that the five-target form raises, and that the correct
form takes effect.

TWO CHAINS ARE SELF-REFERENTIAL. ``_write_unavailable_safe_state`` and
``_maybe_record_trace`` call back INTO the orchestrator, so the coordinator
method in the middle is the patch point and the chain must survive O.3 intact:

    TickOrchestrator._run_unavailable_tick
      -> SequencerPorts.write_unavailable_safe_state()
      -> PoiseCoordinator._write_unavailable_safe_state()   <- patch point
      -> TickOrchestrator._write_unavailable_safe_state()

    TickOrchestrator.finalize_tick
      -> SequencerPorts.record_trace(...)
      -> PoiseCoordinator._maybe_record_trace(...)          <- patch point
      -> TickOrchestrator._maybe_record_trace(...)

Both are driven through a REAL tick here, not through the port in isolation, so
the test also pins that the orchestrator still reaches the patch point at all.

Run (from the project root):
    python -m pytest tests/integration/test_o3_late_binding.py \\
        -q -o asyncio_mode=auto
"""

from __future__ import annotations

from typing import Any

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
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    UNAVAILABLE_SAFE_AFTER_S,
)
from custom_components.poise.runtime.tick_result import (
    CommitResult,
    ExecutionReport,
    HealthUpdate,
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
    CONF_OPTIMAL_START: False,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


class _FakeClock:
    """Deterministic monotonic clock (pattern: test_phase0_persistence_checkpoint)."""

    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _set_room(
    hass: HomeAssistant,
    *,
    trv_state: str = "heat",
    setpoint: float = 20.0,
    room: float | str = 20.0,
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        trv_state,
        {
            "hvac_modes": ["heat", "off"],
            "temperature": setpoint,
            "current_temperature": room if isinstance(room, float) else None,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant) -> Any:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


# ---------------------------------------------------------------------------
# The two self-referential chains, driven through a real tick
# ---------------------------------------------------------------------------


async def test_write_unavailable_safe_state_replacement_takes_effect(
    hass: HomeAssistant,
) -> None:
    """Chain 1: ``_run_unavailable_tick`` must still reach the coordinator
    method, and a replacement installed there must GOVERN the tick.

    Sentinel effect: the replacement records the call AND does not delegate, so
    the real body's climate dispatches must be absent. Had the adapter frozen
    the bound method in ``__init__``, the recorder would stay empty and the
    real safe-state write would have fired instead — both observable here.
    """
    _set_room(hass, trv_state="off", setpoint=5.0)
    coord: Any = await _setup(hass)

    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    hass.states.async_set("sensor.room_temp", "unavailable")

    # Tick A: the sensor loss starts the outage timer, nothing engages yet.
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.runtime.safety.unavailable_since == 1000.0

    seen: list[Any] = []

    async def _sentinel(bindings: Any) -> None:
        seen.append(bindings)  # deliberately NO delegation

    coord._write_unavailable_safe_state = _sentinel
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")

    # Tick B: the timeout has lapsed, so the safe-state node runs.
    clock.t = 1000.0 + UNAVAILABLE_SAFE_AFTER_S + 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert len(seen) == 1, (
        "the replacement on the coordinator instance was never reached — the "
        "port adapter must resolve _write_unavailable_safe_state on every call"
    )
    # the port forwards the tick's ZoneBindings unchanged
    assert seen[0].actuator == "climate.trv"
    assert seen[0].zone_name == "Test Room"
    # ...and it really SUPERSEDED the production body
    assert not set_mode, "the real safe-state body ran despite the replacement"
    assert not set_temp, "the real safe-state body ran despite the replacement"
    # the tick still completed and reported the unavailable-safe payload
    assert coord.data == {"available": False, "unavailable_safe": True}


async def test_maybe_record_trace_replacement_takes_effect(
    hass: HomeAssistant,
) -> None:
    """Chain 2: ``finalize_tick`` must still reach the coordinator method.

    Sentinel effect: the replacement records the payload and its keyword
    contract. A frozen bound method in the adapter would leave the recorder
    empty — the tick would still be green, which is exactly the silent failure
    this test exists for.
    """
    _set_room(hass)
    coord: Any = await _setup(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    seen: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def _sentinel(data: dict[str, Any], **kwargs: Any) -> None:
        seen.append((data, kwargs))

    coord._maybe_record_trace = _sentinel

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert len(seen) == 1, (
        "the replacement on the coordinator instance was never reached — the "
        "port adapter must resolve _maybe_record_trace on every call"
    )
    payload, kwargs = seen[0]
    assert payload["available"] is True
    # the keyword contract the orchestrator hands through the port
    assert set(kwargs) == {"room", "t_out", "rh", "t_rm", "now", "config"}
    # the real body never ran, so no recorder was ever built
    assert coord._tick._trace_recorder is None


# ---------------------------------------------------------------------------
# The three remaining coordinator instance methods, driven through the port
# ---------------------------------------------------------------------------


async def test_forecast_outdoor_replacement_takes_effect(
    hass: HomeAssistant,
) -> None:
    """``_forecast_outdoor`` stays a coordinator method (integration tests
    drive it directly); the port must return whatever the replacement returns,
    with the arguments passed through unchanged."""
    _set_room(hass)
    coord: Any = await _setup(hass)

    calls: list[tuple[float, float]] = []

    async def _sentinel(horizon_min: float, fallback: float) -> float:
        calls.append((horizon_min, fallback))
        return 42.5

    coord._forecast_outdoor = _sentinel

    got = await coord._tick._ports.forecast_outdoor(90.0, 3.0)

    assert got == 42.5
    assert calls == [(90.0, 3.0)]


async def test_commit_execution_replacement_takes_effect(
    hass: HomeAssistant,
) -> None:
    """``commit_execution`` is a coordinator method test_phase5b_sequences
    drives directly; the port must forward report/post_actions/now and hand
    back the ``CommitResult`` the replacement produced."""
    _set_room(hass)
    coord: Any = await _setup(hass)

    marker = CommitResult(events=())
    calls: list[tuple[Any, Any, Any]] = []

    def _sentinel(
        report: Any, post_actions: Any = (), *, now: float | None = None
    ) -> CommitResult:
        calls.append((report, post_actions, now))
        return marker

    coord.commit_execution = _sentinel

    report = ExecutionReport(executions=())
    got = coord._tick._ports.commit_execution(report, now=7.0)

    assert got is marker
    assert calls == [(report, (), 7.0)]


async def test_maybe_save_replacement_takes_effect(hass: HomeAssistant) -> None:
    """The F-SAVEPOINT persistence checkpoint. It was NEVER snapshotted as a
    bound method (the coordinator's own construction comment says so); this
    test makes that a machine-checked fact instead of a comment."""
    _set_room(hass)
    coord: Any = await _setup(hass)

    calls: list[str] = []

    async def _sentinel() -> None:
        calls.append("save")

    coord._maybe_save = _sentinel

    await coord._tick._ports.save_if_due()

    assert calls == ["save"]


# ---------------------------------------------------------------------------
# The sixth target — a collaborator's method, so a different substitution form
# ---------------------------------------------------------------------------


class _RecordingReporter:
    """Stand-in for ``HealthReporter`` that records and optionally delegates."""

    def __init__(self, inner: Any = None) -> None:
        self.inner = inner
        self.seen: list[tuple[HealthUpdate, ...]] = []

    def emit(self, updates: tuple[HealthUpdate, ...]) -> None:
        self.seen.append(updates)
        if self.inner is not None:
            self.inner.emit(updates)

    def __getattr__(self, name: str) -> Any:
        # Only for the delegating variant: the coordinator uses the reporter
        # for far more than ``emit`` during a live tick.
        if self.inner is None:
            raise AttributeError(name)
        return getattr(self.inner, name)


async def test_health_emit_resolves_through_the_reporter(
    hass: HomeAssistant,
) -> None:
    """The health checkpoint's substitution form differs from the other five.

    (a) The five-target form is not merely discouraged here, it is impossible:
        ``HealthReporter`` declares ``__slots__``, so ``emit`` cannot be
        replaced on the reporter instance.
    (b) The correct form — replace ``coordinator._health`` — must take effect
        through the port, which is only true if the adapter resolves BOTH
        ``_health`` and ``emit`` at call time.
    """
    _set_room(hass)
    coord: Any = await _setup(hass)

    # (a) why this target cannot use the other five's form
    assert "emit" not in vars(type(coord._health)).get("__slots__", ())
    with pytest.raises(AttributeError):
        coord._health.emit = lambda updates: None

    # (b) replacing the REPORTER is honoured on the next port call
    recorder = _RecordingReporter()
    coord._health = recorder
    update = HealthUpdate(issue_id="probe", active=True, translation_key="probe")
    coord._tick._ports.emit_health((update,))

    assert recorder.seen == [(update,)], (
        "the port adapter froze coordinator._health (or its emit) instead of "
        "resolving it on every call"
    )


async def test_health_emit_replacement_is_honoured_on_a_real_tick(
    hass: HomeAssistant,
) -> None:
    """The same substitution, driven through a whole tick: every health
    checkpoint of the prepare/finalize flow must land on the REPLACED reporter,
    not on the one that existed when the orchestrator was built."""
    _set_room(hass)
    coord: Any = await _setup(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    recorder = _RecordingReporter(inner=coord._health)
    coord._health = recorder

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert recorder.seen, "no health checkpoint reached the replaced reporter"
    # the availability gate's checkpoint is the first one of every tick
    assert recorder.seen[0][0].translation_key == "sensor_unavailable"
