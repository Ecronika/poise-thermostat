"""F29: the boiler keepalive must not re-assert a merely-ASSUMED state.

Until the real boiler entity was readable once (reconciled), a fresh BoilerState
(``last_keepalive_mono=0.0``) run against the real monotonic clock would fire an
immediate keepalive-OFF — switching a physically running boiler off on a boot
tick where a Zigbee/network switch has not loaded yet. The keepalive is therefore
gated on the caller's reconciliation flag (``allow_keepalive``).
"""

from __future__ import annotations

from custom_components.poise.control.hub_aggregate import BoilerState, step_boiler

_COMMON: dict[str, float] = {
    "now_mono": 10_000.0,  # >> keepalive_s vs the fresh state's last_keepalive_mono=0.0
    "activation_delay_s": 30.0,
    "min_on_s": 300.0,
    "min_off_s": 300.0,
    "keepalive_s": 600.0,
}


def test_keepalive_suppressed_before_reconciliation() -> None:
    # F29: unreconciled -> the assumed-off state is NOT re-asserted (no OFF call)
    step = step_boiler(BoilerState(), demand=False, allow_keepalive=False, **_COMMON)
    assert step.call is None


def test_keepalive_fires_once_reconciled() -> None:
    # the exact behaviour F29 guards against unless reconciled: keepalive re-asserts
    step = step_boiler(BoilerState(), demand=False, allow_keepalive=True, **_COMMON)
    assert step.call == "off"


def test_keepalive_default_is_backward_compatible() -> None:
    # existing callers (default allow_keepalive=True) keep the old re-assert
    step = step_boiler(BoilerState(), demand=False, **_COMMON)
    assert step.call == "off"


def test_demand_switch_still_works_when_keepalive_gated() -> None:
    # gating the keepalive must NOT block a real demand-driven transition: with
    # sustained demand past the activation delay the boiler still turns ON
    state = BoilerState(demand_true_since=_COMMON["now_mono"] - 100.0)
    step = step_boiler(state, demand=True, allow_keepalive=False, **_COMMON)
    assert step.call == "on"
