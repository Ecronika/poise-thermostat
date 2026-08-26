"""P2.2 carry-over glue test (plan §4 P2.2 step 8a, disposition Rev. 2.3 #5):
``PreparePhase._stage_schedule_presence`` on an ``always_setback`` schedule.

P2.1 made "this transition does not exist" an honest ``None`` instead of a
sentinel; the consumer guard at ``phase_prepare.py`` (``has_comfort_edge``/
``has_setback_edge``) is only provable end to end through the REAL phase
class -- the pure ``stage_schedule_gate`` tests in
``tests/test_phase6b_stages.py`` stop one stage short of ``plan_preheat``
itself. ``PreparePhase`` imports ``homeassistant.components.persistent_
notification``, so this is HA-glue and lives here rather than in the pure
suite.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, cast
from unittest.mock import patch

from custom_components.poise.comfort.schedule import ScheduleState
from custom_components.poise.control.optimal_start import PreheatPlan
from custom_components.poise.ha.phase_prepare import PreparePhase
from custom_components.poise.runtime.tick_inputs import PresenceSnapshot
from tests.test_o2_tick_snapshot import sample_tick_config
from tests.test_phase6b_stages import _inputs, _runtime, _stage_ingest, _stage_observe

_LOG = logging.getLogger("tests.p22_prepare_schedule_glue")


class _StubReader:
    """Only ``read_presence()`` is touched by ``_stage_schedule_presence``."""

    def read_presence(self) -> PresenceSnapshot:
        return PresenceSnapshot(home=(True,), occupancy=())


class _StubPorts:
    """Only ``expire_timed_states``/``end_hold`` are touched by this stage."""

    def expire_timed_states(self, home: bool | None) -> None:
        pass

    def end_hold(self, reason: str) -> None:
        pass


def _phase() -> tuple[PreparePhase, Any]:
    runtime = _runtime()
    phase = PreparePhase(
        runtime=runtime,
        reader=cast(Any, _StubReader()),
        forecast=cast(Any, None),  # untouched by this stage
        hass=cast(Any, None),  # untouched by this stage
        ports=cast(Any, _StubPorts()),
        logger=_LOG,
    )
    return phase, runtime


def test_always_setback_disables_optimal_start_and_stop_gates() -> None:
    # P2.1 guard 3 (F26 site #3): both edges are None (always-setback has no
    # next comfort start OR end) -> both predictive gates must be False, the
    # SAME no-request treatment as an unidentified model -- never a 7-day
    # sentinel horizon.
    phase, runtime = _phase()
    inputs = _inputs()
    ing = _stage_ingest(runtime, inputs)
    obs = _stage_observe(runtime, inputs, ing)
    config = dataclasses.replace(
        sample_tick_config(), optimal_start=True, optimal_stop=True
    )
    always_setback = ScheduleState(
        is_comfort=False,
        minutes_to_comfort=None,
        setback_offset=-3.0,
        minutes_to_setback=None,
    )
    captured: dict[str, Any] = {}

    def _spy_plan_preheat(**kwargs: Any) -> PreheatPlan:
        captured.update(kwargs)
        return PreheatPlan(base=18.0, preheating=False, preheat_outdoor=None)

    with patch(
        "custom_components.poise.control.optimal_start.plan_preheat",
        side_effect=_spy_plan_preheat,
    ):
        phase._stage_schedule_presence(
            ing, obs, always_setback, config, t_out_lead=4.0, model=None
        )

    assert captured["optimal_start_enabled"] is False
    assert captured["optimal_stop_enabled"] is False
    # The neutral 0.0 fallback the disabled plan receives (never None -- the
    # planner's own signature is float, the caller guarantees non-None).
    assert captured["minutes_to_comfort"] == 0.0
    assert captured["minutes_to_setback"] == 0.0
