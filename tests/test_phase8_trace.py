"""Phase 8 (S3) — pure tests for ``diagnostics/trace.py`` (plan §2, trace verdict).

``build_tick_record`` is the verbatim module relocation of the coordinator's
inline snapshot+build sequence inside ``_maybe_record_trace`` (6a-S1 binding
decision: the build stays fused with the append inside the swallow boundary —
only the INSTRUCTIONS moved). These tests pin the composition against the
underlying ``trace.schema`` kernels, so any drift between the relocated helper
and the historical inline sequence is caught pure, without HA.

The swallow-boundary and append-position semantics themselves are coordinator
behaviour and stay pinned by the integration suite (the trace capture path);
the object-identity chain of the traced dict is pinned by
``tests/integration/test_phase8_presenter.py``.
"""

from __future__ import annotations

from typing import Any

from custom_components.poise.diagnostics.trace import build_tick_record
from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.trace.schema import (
    TRACE_VERSION,
    ModelSnapshot,
    build_record,
)


def _driven_ekf() -> ThermalEKF:
    """A deterministic EKF with non-default state and non-zero regime counters,
    so a swapped field (e.g. beta_h vs beta_c) cannot cancel out in the tests."""
    ekf = ThermalEKF()
    ekf.x[0] = 18.0
    for i in range(6):
        ekf.predict(1.0 / 60.0, t_out=5.0, u_h=1.0 if i % 2 else 0.0, u_c=0.0)
        ekf.update(18.0 + 0.05 * i)
    return ekf


_DATA: dict[str, Any] = {
    "mode": "heat",
    "target_temperature": 21.5,
    "heat_sp": 21.0,
    "cool_sp": 26.0,
    "window_open": True,
    "frozen": False,
    "mode_nudge_blocked": "compressor_min_off",
    "preheating": True,
    "coasting": False,
    "ca_deviation_k": 0.4,
    "humidity_action": "dry",
    "dry_active": True,
    "device_hvac_mode": "dry",
    "hvac_action": "drying",
    "dewpoint": 12.3,
    "abs_humidity_gkg": 8.1,
    "rh_high_used": 60.0,
    "occupied": True,
}


def test_build_tick_record_equals_the_inline_snapshot_plus_build_record() -> None:
    """The relocated composition is the historical inline sequence: building the
    ``ModelSnapshot`` field-by-field from the SAME EKF and calling
    ``build_record`` with the SAME kwargs yields an equal record."""
    ekf = _driven_ekf()
    kwargs: dict[str, Any] = {
        "ts": 1700000123.5,
        "mono": 4321.0,
        "room": 19.25,
        "t_out": 3.5,
        "u_h": 0.75,
        "u_c": 0.0,
        "q_solar": 0.2,
        "rh": 55.0,
        "t_rm": 18.75,
    }
    inline = build_record(
        _DATA,
        ModelSnapshot(
            alpha=ekf.x[1],
            beta_h=ekf.x[2],
            beta_c=ekf.x[3],
            beta_s=ekf.x[4],
            beta_o=ekf.x[5],
            t_std=ekf.temperature_std,
            n_idle=ekf.n_idle,
            n_heating=ekf.n_heating,
            n_cooling=ekf.n_cooling,
            identified=ekf.identified,
        ),
        **kwargs,
    )
    assert build_tick_record(_DATA, ekf, **kwargs) == inline


def test_build_tick_record_maps_ekf_state_and_drive_inputs_verbatim() -> None:
    """Field-level pin: the EKF state vector, the covariance std, the regime
    counters and every explicit drive kwarg land on the record unchanged;
    ``q_occ`` keeps ``build_record``'s 0.0 default (the coordinator never
    passed it), and the decision context comes from the data dict."""
    ekf = _driven_ekf()
    r = build_tick_record(
        _DATA,
        ekf,
        ts=1.5,
        mono=2.5,
        room=3.5,
        t_out=4.5,
        u_h=0.25,
        u_c=0.5,
        q_solar=0.75,
        rh=None,
        t_rm=None,
    )
    assert r.v == TRACE_VERSION
    assert (r.ts, r.mono, r.room, r.t_out) == (1.5, 2.5, 3.5, 4.5)
    assert (r.u_h, r.u_c, r.q_solar, r.q_occ) == (0.25, 0.5, 0.75, 0.0)
    assert (r.rh, r.t_rm) == (None, None)
    assert (r.alpha, r.beta_h, r.beta_c, r.beta_s, r.beta_o) == (
        ekf.x[1],
        ekf.x[2],
        ekf.x[3],
        ekf.x[4],
        ekf.x[5],
    )
    assert r.t_std == ekf.temperature_std
    assert (r.n_idle, r.n_heating, r.n_cooling) == (
        ekf.n_idle,
        ekf.n_heating,
        ekf.n_cooling,
    )
    assert r.identified is ekf.identified
    assert r.n_heating > 0  # the fixture really drove the counters
    # decision context read from the data dict (defensive reads live in
    # build_record and are pinned by tests/test_trace.py)
    assert r.mode == "heat"
    assert r.target == 21.5
    assert r.mode_nudge_blocked == "compressor_min_off"
    assert r.device_hvac_mode == "dry"
    assert r.rh_ceiling == 60.0
