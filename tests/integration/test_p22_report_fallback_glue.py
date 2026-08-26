"""P2.2 carry-over glue test (plan §4 P2.2 step 8b, disposition Rev. 2.4 #3):
``ReportPhase._fold_hdh_and_outcome``'s fixed ``model_expected_minutes``
fallback when the schedule has no upcoming comfort start.

P2.1 made ``ScheduleState.minutes_to_comfort`` honestly ``None`` for
always-comfort/always-setback (plan §0.6 p.3); ``model_expected_minutes``
still requires a ``float``, so ``phase_report.py`` fixes the fallback at
``float(sched.minutes_to_comfort or 0.0)`` -- the same value ``always_comfort``
produced before the change (regression-free). This is provable only through
the REAL fold method (the pure ``stage_schedule_gate`` tests stop before this
seam), reusing ``test_o6_outcome_folds``'s realistic ``FinalizeContext``/
``ReportPhase`` harness. ``ha/phase_report.py`` imports
``homeassistant.util.dt``, so this is HA-glue and lives here.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from custom_components.poise.comfort.schedule import ScheduleState
from custom_components.poise.control.scoring_expectation import (
    model_expected_minutes as _real_model_expected_minutes,
)
from custom_components.poise.ha import phase_report
from tests.integration.test_o6_outcome_folds import NOW, _ctx, _phase


def test_hdh_fold_fallback_is_zero_when_no_comfort_start_exists(
    monkeypatch: Any,
) -> None:
    ctx = dataclasses.replace(
        _ctx(),
        sched=ScheduleState(
            is_comfort=True,
            minutes_to_comfort=None,  # P2.1: no upcoming comfort start exists
            setback_offset=0.0,
            minutes_to_setback=None,
        ),
    )
    captured: dict[str, Any] = {}

    def _spy(*args: Any, **kwargs: Any) -> float:
        captured.update(kwargs)
        return _real_model_expected_minutes(*args, **kwargs)

    monkeypatch.setattr(phase_report, "model_expected_minutes", _spy)
    phase, _runtime = _phase()
    phase._fold_hdh_and_outcome(ctx, tick_min=1.0)

    assert captured["fallback"] == 0.0  # float(None or 0.0), never None itself
    assert isinstance(captured["fallback"], float)


def test_hdh_fold_fallback_carries_the_real_minutes_when_present(
    monkeypatch: Any,
) -> None:
    # Contrast case: a real upcoming comfort start feeds its own minutes,
    # unaffected by the None-guard (pins the guard is `or 0.0`, not a blanket
    # override).
    ctx = dataclasses.replace(
        _ctx(),
        sched=ScheduleState(
            is_comfort=False, minutes_to_comfort=45.0, setback_offset=-3.0
        ),
    )
    captured: dict[str, Any] = {}

    def _spy(*args: Any, **kwargs: Any) -> float:
        captured.update(kwargs)
        return _real_model_expected_minutes(*args, **kwargs)

    monkeypatch.setattr(phase_report, "model_expected_minutes", _spy)
    phase, runtime = _phase()
    phase._fold_hdh_and_outcome(ctx, tick_min=1.0)

    assert captured["fallback"] == 45.0
    # No identified model in this fresh runtime -> model_expected_minutes
    # returns the fallback verbatim, which the session then books.
    assert runtime.diagnostics.hdh_last_mono == NOW
