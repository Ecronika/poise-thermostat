from __future__ import annotations

import math
from dataclasses import replace

from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.trace.schema import (
    TRACE_VERSION,
    ModelSnapshot,
    TraceRecord,
    build_record,
)
from tests.harness.trace_replay import load_trace, replay_ekf


def _make_trace(n: int = 40) -> list[TraceRecord]:
    """A deterministic trace whose per-tick snapshot is exactly what a fresh EKF
    reaches when re-driven from the same records (the golden self-consistency).
    Rooms are pre-rounded to 4 dp so serialization round-trips the drive fields
    losslessly (only room varies; t_out/u_* are exact)."""
    a_true, b_true, t_out = 0.1, 3.0, 5.0
    dt_s = 60.0
    ex = math.exp(-a_true * (dt_s / 3600.0))
    air = 18.0
    rooms: list[float] = []
    u_hs: list[float] = []
    monos: list[float] = []
    mono = 0.0
    for _ in range(n):
        u = 1.0 if air < 21.0 else 0.0
        rooms.append(round(air, 4))
        u_hs.append(u)
        monos.append(mono)
        t_eq = t_out + b_true * u / a_true
        air = t_eq + (air - t_eq) * ex
        mono += dt_s

    ekf = ThermalEKF()
    ekf.x[0] = rooms[0]
    records: list[TraceRecord] = []
    prev: float | None = None
    for i in range(n):
        if prev is not None:
            ekf.predict((monos[i] - prev) / 3600.0, t_out=t_out, u_h=u_hs[i], u_c=0.0)
            ekf.update(rooms[i])
        prev = monos[i]
        records.append(
            TraceRecord(
                v=TRACE_VERSION,
                ts=float(i),
                mono=monos[i],
                room=rooms[i],
                t_out=t_out,
                u_h=u_hs[i],
                u_c=0.0,
                q_solar=0.0,
                q_occ=0.0,
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
            )
        )
    return records


def test_json_line_round_trip_is_lossless_for_round_values() -> None:
    r = TraceRecord(
        v=1, ts=1700000000.0, mono=120.0, room=20.5, t_out=5.0, u_h=1.0, u_c=0.0,
        q_solar=0.0, q_occ=0.0, alpha=0.15, beta_h=3.0, beta_c=4.0, beta_s=0.5,
        beta_o=0.25, t_std=0.5, n_idle=3, n_heating=2, n_cooling=0, identified=False,
        mode="heat", heat_sp=21.0, mode_nudge_blocked="min-off 240s",
    )
    assert TraceRecord.from_json_line(r.to_json_line()) == r


def test_none_fields_are_dropped_and_reads_are_forward_compatible() -> None:
    r = TraceRecord(
        v=1, ts=0.0, mono=0.0, room=20.0, t_out=5.0, u_h=0.0, u_c=0.0, q_solar=0.0,
        q_occ=0.0, alpha=0.15, beta_h=3.0, beta_c=4.0, beta_s=0.5, beta_o=0.3,
        t_std=1.0, n_idle=0, n_heating=0, n_cooling=0, identified=False,
    )
    line = r.to_json_line()
    assert "rh" not in line and "ca_deviation_k" not in line  # None dropped
    # an unknown future key must not break the reader
    assert TraceRecord.from_json_line(line.replace("{", '{"future_key":1,', 1)) == r


def test_build_record_maps_inputs_model_and_decision() -> None:
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    data = {
        "mode": "cool", "target_temperature": 24.0, "heat_sp": 21.0, "cool_sp": 24.0,
        "window_open": False, "mode_nudge_blocked": "",
        "preheating": False, "coasting": True, "ca_deviation_k": 0.3,
    }
    r = build_record(
        data, model, ts=1.0, mono=60.0, room=27.0, t_out=30.0, u_h=0.0, u_c=1.0,
        q_solar=0.4, rh=55.0,
    )
    assert r.v == TRACE_VERSION and r.room == 27.0 and r.u_c == 1.0
    assert r.alpha == 0.12 and r.identified is True and r.n_idle == 61
    assert r.mode == "cool" and r.target == 24.0 and r.cool_sp == 24.0
    assert r.coasting is True and r.ca_deviation_k == 0.3 and r.rh == 55.0


def test_replay_reproduces_recorded_model_and_is_deterministic() -> None:
    records = _make_trace()
    text = "\n".join(r.to_json_line() for r in records)
    loaded = load_trace(text)
    assert len(loaded) == len(records)

    model = replay_ekf(loaded)
    # golden: re-driving from the recorded (serialized) inputs reproduces the
    # model the recorder captured — proving the trace is replay-sufficient.
    assert abs(model.alpha - records[-1].alpha) < 1e-9
    assert abs(model.beta_h - records[-1].beta_h) < 1e-9
    # deterministic: same trace, same model, byte-for-byte.
    assert replay_ekf(loaded) == model


def test_missing_cooling_drive_would_break_replay_sufficiency() -> None:
    # guard the contract: if u_c were dropped from the record, a cooling trace
    # could not be reproduced. Here we prove u_c is actually consumed by replay.
    records = _make_trace()
    tampered = [replace(r, u_c=1.0) for r in records]
    assert replay_ekf(tampered).beta_c != replay_ekf(records).beta_c
