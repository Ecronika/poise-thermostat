from __future__ import annotations

import json
import math
from dataclasses import replace

from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.trace.schema import (
    MIN_SUPPORTED_TRACE_VERSION,
    TRACE_TS_QUANTUM_S,
    TRACE_VERSION,
    ModelSnapshot,
    TraceRecord,
    build_record,
    is_supported_version,
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
        v=1,
        ts=1700000000.0,
        mono=120.0,
        room=20.5,
        t_out=5.0,
        u_h=1.0,
        u_c=0.0,
        q_solar=0.0,
        q_occ=0.0,
        alpha=0.15,
        beta_h=3.0,
        beta_c=4.0,
        beta_s=0.5,
        beta_o=0.25,
        t_std=0.5,
        n_idle=3,
        n_heating=2,
        n_cooling=0,
        identified=False,
        mode="heat",
        heat_sp=21.0,
        mode_nudge_blocked="min-off 240s",
    )
    assert TraceRecord.from_json_line(r.to_json_line()) == r


def test_none_fields_are_dropped_and_reads_are_forward_compatible() -> None:
    r = TraceRecord(
        v=1,
        ts=0.0,
        mono=0.0,
        room=20.0,
        t_out=5.0,
        u_h=0.0,
        u_c=0.0,
        q_solar=0.0,
        q_occ=0.0,
        alpha=0.15,
        beta_h=3.0,
        beta_c=4.0,
        beta_s=0.5,
        beta_o=0.3,
        t_std=1.0,
        n_idle=0,
        n_heating=0,
        n_cooling=0,
        identified=False,
    )
    line = r.to_json_line()
    assert "rh" not in line and "ca_deviation_k" not in line  # None dropped
    # an unknown future key must not break the reader
    assert TraceRecord.from_json_line(line.replace("{", '{"future_key":1,', 1)) == r


def test_build_record_maps_inputs_model_and_decision() -> None:
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    data = {
        "mode": "cool",
        "target_temperature": 24.0,
        "heat_sp": 21.0,
        "cool_sp": 24.0,
        "window_open": False,
        "mode_nudge_blocked": "",
        "preheating": False,
        "coasting": True,
        "ca_deviation_k": 0.3,
    }
    r = build_record(
        data,
        model,
        ts=1.0,
        mono=60.0,
        room=27.0,
        t_out=30.0,
        u_h=0.0,
        u_c=1.0,
        q_solar=0.4,
        rh=55.0,
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


# --- v2: humidity / real-device axis + deprecation window -------------------


def test_v2_record_round_trips_the_humidity_axis() -> None:
    r = TraceRecord(
        v=TRACE_VERSION,
        ts=1700000000.0,
        mono=120.0,
        room=24.1,
        t_out=17.0,
        u_h=0.0,
        u_c=0.0,
        q_solar=0.3,
        q_occ=0.0,
        alpha=0.1,
        beta_h=3.0,
        beta_c=4.0,
        beta_s=0.3,
        beta_o=0.3,
        t_std=0.5,
        n_idle=10,
        n_heating=0,
        n_cooling=0,
        identified=True,
        humidity_action="dry",
        dry_active=True,
        device_hvac_mode="dry",
        hvac_action="drying",
        dewpoint=12.4,
        abs_humidity_gkg=8.9,
        rh_ceiling=50.0,
        occupied=False,
    )
    back = TraceRecord.from_json_line(r.to_json_line())
    assert back == r
    assert back.humidity_action == "dry" and back.device_hvac_mode == "dry"
    assert back.dry_active is True and back.occupied is False
    assert back.dewpoint == 12.4 and back.rh_ceiling == 50.0


def test_v1_record_loads_into_v2_with_defaulted_humidity_fields() -> None:
    # A record written by the v1 recorder (no humidity axis) must still load:
    # the new fields default, which IS the backward-compatibility mechanism.
    v1_line = (
        '{"v":1,"ts":0.0,"mono":0.0,"room":20.0,"t_out":5.0,"u_h":0.0,"u_c":0.0,'
        '"q_solar":0.0,"q_occ":0.0,"alpha":0.15,"beta_h":3.0,"beta_c":4.0,'
        '"beta_s":0.5,"beta_o":0.3,"t_std":1.0,"n_idle":0,"n_heating":0,'
        '"n_cooling":0,"identified":false,"mode":"idle"}'
    )
    rec = TraceRecord.from_json_line(v1_line)
    assert rec.v == 1 and rec.mode == "idle"
    assert rec.humidity_action == "" and rec.dry_active is False
    assert rec.device_hvac_mode == "" and rec.occupied is False
    assert rec.dewpoint is None and rec.rh_ceiling is None
    # and the deprecation-aware loader keeps it (v1 is still supported)
    assert len(load_trace(v1_line)) == 1


def test_build_record_populates_the_v2_humidity_fields() -> None:
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    data = {
        "mode": "idle",
        "humidity_action": "dry",
        "dry_active": True,
        "device_hvac_mode": "dry",
        "hvac_action": "drying",
        "dewpoint": 12.4,
        "abs_humidity_gkg": 8.9,
        "rh_high_used": 50.0,
        "occupied": False,
    }
    r = build_record(
        data,
        model,
        ts=1.0,
        mono=60.0,
        room=24.1,
        t_out=17.0,
        u_h=0.0,
        u_c=0.0,
        rh=48.0,
    )
    assert r.v == TRACE_VERSION
    assert r.humidity_action == "dry" and r.dry_active is True
    assert r.device_hvac_mode == "dry" and r.hvac_action == "drying"
    assert r.dewpoint == 12.4 and r.abs_humidity_gkg == 8.9
    assert r.rh_ceiling == 50.0 and r.occupied is False


def test_adr0066_humidity_axis_fields_map_round_trip_and_default() -> None:
    """The ADR-0066 additions ride within v2: build_record maps them from the
    data dict, they survive the JSON round trip, and a pre-ADR-0066 v2 line
    (without the keys) loads with defaults — no version bump required."""
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    data = {
        "abs_humidity_gm3": 14.3,
        "abs_humidity_out_gm3": 13.5,
        "surface_rh_mean": 77.35,
        "vent_action": "open",
        "vent_reason": "mold_risk",
    }
    r = build_record(
        data, model, ts=1.0, mono=60.0, room=22.9, t_out=16.0, u_h=0.0, u_c=0.0
    )
    assert r.abs_humidity_gm3 == 14.3 and r.abs_humidity_out_gm3 == 13.5
    assert r.surface_rh_mean == 77.35
    assert r.vent_action == "open" and r.vent_reason == "mold_risk"
    back = TraceRecord.from_json_line(r.to_json_line())
    assert back == r
    # a v2 line recorded BEFORE ADR-0066 (keys genuinely absent) still loads,
    # every new field defaulted
    payload = json.loads(r.to_json_line())
    for key in (
        "abs_humidity_gm3",
        "abs_humidity_out_gm3",
        "surface_rh_mean",
        "vent_action",
        "vent_reason",
    ):
        payload.pop(key, None)
    rec = TraceRecord.from_dict(payload)
    assert rec.abs_humidity_gm3 is None and rec.abs_humidity_out_gm3 is None
    assert rec.surface_rh_mean is None
    assert rec.vent_action == "" and rec.vent_reason == ""


def test_load_trace_drops_unsupported_versions() -> None:
    assert is_supported_version(MIN_SUPPORTED_TRACE_VERSION) is True
    assert is_supported_version(TRACE_VERSION) is True
    assert is_supported_version(TRACE_VERSION + 1) is False
    assert is_supported_version(MIN_SUPPORTED_TRACE_VERSION - 1) is False
    good = TraceRecord(
        v=TRACE_VERSION,
        ts=0.0,
        mono=0.0,
        room=20.0,
        t_out=5.0,
        u_h=0.0,
        u_c=0.0,
        q_solar=0.0,
        q_occ=0.0,
        alpha=0.1,
        beta_h=3.0,
        beta_c=4.0,
        beta_s=0.5,
        beta_o=0.3,
        t_std=1.0,
        n_idle=0,
        n_heating=0,
        n_cooling=0,
        identified=False,
    ).to_json_line()
    future = good.replace(f'"v":{TRACE_VERSION}', '"v":99')
    loaded = load_trace(good + "\n" + future)
    assert len(loaded) == 1 and loaded[0].v == TRACE_VERSION
    # opt out of the drop to inspect everything (e.g. for diagnostics)
    assert len(load_trace(good + "\n" + future, drop_unsupported=False)) == 2


def test_shadow_outputs_round_trip_and_default() -> None:
    """September-Instrumentierung: die Shadow-Outputs reiten als defaultete
    In-Version-Felder im Trace mit (gleicher Kompat-Mechanismus wie die
    v2-Feuchteachse, kein Version-Bump), damit die Winter-Gate-Evidenz
    (ADR-0033b/0036/0037/0056) nicht an der ~10-Tage-Attribut-History haengt."""
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    data = {
        "mpc_active": True,
        "mpc_setpoint": 21.5,
        "mpc_weight": 0.85,
        "mpc_power": 0.4,
        "tpi_duty": 0.63,
        "pi_setpoint": 22.3,
        "pi_offset": 1.3,
        "ref_offset": -0.8,
    }
    rec = build_record(
        data, model, ts=1.0, mono=60.0, room=20.0, t_out=5.0, u_h=1.0, u_c=0.0
    )
    assert rec.mpc_active is True and rec.mpc_setpoint == 21.5
    assert rec.mpc_weight == 0.85 and rec.mpc_power == 0.4
    assert rec.tpi_duty == 0.63
    assert rec.pi_setpoint == 22.3 and rec.pi_offset == 1.3
    assert rec.ref_offset == -0.8

    back = TraceRecord.from_json_line(rec.to_json_line())
    assert back.mpc_setpoint == 21.5 and back.tpi_duty == 0.63
    assert back.ref_offset == -0.8 and back.mpc_active is True

    # absent (alter Writer / Shadow inaktiv) -> Defaults, kein Version-Bump
    rec2 = build_record(
        {}, model, ts=1.0, mono=60.0, room=20.0, t_out=5.0, u_h=1.0, u_c=0.0
    )
    assert rec2.v == TRACE_VERSION
    assert rec2.mpc_active is False and rec2.mpc_setpoint is None
    assert rec2.tpi_duty is None and rec2.pi_setpoint is None
    assert rec2.pi_offset is None and rec2.ref_offset is None


def test_convergence_telemetry_round_trip_and_default() -> None:
    """Review C.8: the write-convergence counters ride along as defaulted
    in-version trace fields (same compat mechanism, no version bump) so
    non-convergence episodes are visible in a replay."""
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    data = {"sp_diverged_writes": 3, "mode_diverged_nudges": 2}
    rec = build_record(
        data, model, ts=1.0, mono=60.0, room=20.0, t_out=5.0, u_h=1.0, u_c=0.0
    )
    assert rec.sp_diverged_writes == 3
    assert rec.mode_diverged_nudges == 2

    back = TraceRecord.from_json_line(rec.to_json_line())
    assert back.sp_diverged_writes == 3 and back.mode_diverged_nudges == 2

    # absent (old writer / converged) -> defaults, no version bump
    rec2 = build_record(
        {}, model, ts=1.0, mono=60.0, room=20.0, t_out=5.0, u_h=1.0, u_c=0.0
    )
    assert rec2.v == TRACE_VERSION
    assert rec2.sp_diverged_writes == 0 and rec2.mode_diverged_nudges == 0


def test_cooling_failure_round_trip_and_default() -> None:
    """Review C.8: the cooling-failure verdict rides in the trace (defaulted
    in-version, no bump)."""
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    rec = build_record(
        {"cooling_failure": True},
        model,
        ts=1.0,
        mono=60.0,
        room=27.0,
        t_out=30.0,
        u_h=0.0,
        u_c=1.0,
    )
    assert rec.cooling_failure is True
    back = TraceRecord.from_json_line(rec.to_json_line())
    assert back.cooling_failure is True

    rec2 = build_record(
        {}, model, ts=1.0, mono=60.0, room=20.0, t_out=5.0, u_h=1.0, u_c=0.0
    )
    assert rec2.v == TRACE_VERSION and rec2.cooling_failure is False


def test_frozen_reads_the_live_feed_key_and_heating_failure_rides_along() -> None:
    """The v3 fix: the live tick feed publishes ``sensor_frozen`` (see
    ``phase_report``), so ``build_record`` must read THAT key — v2 recorded a
    permanently-False ``frozen``. The heating-failure verdict (fed as
    ``heating_failure`` all along) gets its trace field, symmetric to
    ``cooling_failure``."""
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    rec = build_record(
        {"sensor_frozen": True, "heating_failure": True},
        model,
        ts=1.0,
        mono=60.0,
        room=20.0,
        t_out=5.0,
        u_h=1.0,
        u_c=0.0,
    )
    assert rec.frozen is True
    assert rec.heating_failure is True
    back = TraceRecord.from_json_line(rec.to_json_line())
    assert back.frozen is True and back.heating_failure is True

    # The semantics fix is version-marked: records claiming trustworthy
    # ``frozen`` carry v3; the replay window still accepts v1/v2.
    assert TRACE_VERSION == 3
    assert is_supported_version(2) is True

    # absent keys (old feed shape) -> defaults
    rec2 = build_record(
        {}, model, ts=1.0, mono=60.0, room=20.0, t_out=5.0, u_h=1.0, u_c=0.0
    )
    assert rec2.frozen is False and rec2.heating_failure is False


def test_ts_is_quantized_to_the_privacy_bucket() -> None:
    """ADR-0022 decision 3: the wall-clock anchor is quantised (15 min
    buckets) so a shared trace carries no fine-grained usage pattern. ``mono``
    — the actual dt source for replay — stays exact."""
    model = ModelSnapshot(0.12, 2.5, 4.0, 0.5, 0.3, 0.4, 61, 22, 0, True)
    rec = build_record(
        {}, model, ts=1700000123.5, mono=4321.25, room=20.0, t_out=5.0, u_h=1.0, u_c=0.0
    )
    assert rec.ts == 1700000100.0  # floor(ts / 900) * 900
    assert rec.ts % TRACE_TS_QUANTUM_S == 0.0
    assert rec.mono == 4321.25  # replay dt source is untouched
