"""Replay-sufficient field-trace record (ADR-0011 harness, ADR-0014 determinism).

One ``TraceRecord`` is a single coordinator tick captured so it can be **replayed
offline**: the EKF drive inputs + measurement (``room``, ``t_out``, ``u_h``,
``u_c``, ``q_solar``, ``q_occ`` and the monotonic clock for ``dt``) let a fresh
estimator be re-driven deterministically; the model snapshot and Poise's realized
decision let a replay be scored against reality. Recorded one JSON line per tick,
opt-in — pure observation in the spirit of ADR-0026, it never touches control.

Pure stdlib; the file writer lives in the glue ``recorder`` module.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

# v3: semantics fix — ``frozen`` is now actually populated (v2 always recorded
# False because ``build_record`` read the key ``frozen`` while the live feed
# publishes ``sensor_frozen``), and the heating-failure verdict gains its trace
# field. The bump marks TRUSTWORTHY ``frozen``/``heating_failure`` semantics:
# in a v<=2 record their False is meaningless, in a v3 record it is a verdict.
TRACE_VERSION: int = 3
# Oldest on-disk trace version the replay loader still accepts (deprecation
# window). Bump this — and retire the matching frozen golden — only when a
# schema change makes older records genuinely un-replayable. Today a v1 record
# replays fine (its missing v2/v3 fields simply default), so v1 stays supported
# and is pinned by a frozen legacy golden.
MIN_SUPPORTED_TRACE_VERSION: int = 1

# ADR-0022 decision 3 (privacy): the wall-clock anchor ``ts`` is quantised to
# this bucket before recording, so a shared trace file carries no fine-grained
# presence/usage pattern. 15 min is coarse enough to hide behaviour and fine
# enough to keep the human anchor useful; ``mono`` — the replay dt source —
# is deliberately NOT quantised (determinism, ADR-0014).
TRACE_TS_QUANTUM_S: float = 900.0


def is_supported_version(v: int) -> bool:
    """Whether a record's ``v`` is inside the replayable window (deprecation)."""
    return MIN_SUPPORTED_TRACE_VERSION <= v <= TRACE_VERSION


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    """The learned-model state at one tick (the EKF's public numbers)."""

    alpha: float
    beta_h: float
    beta_c: float
    beta_s: float
    beta_o: float
    t_std: float
    n_idle: int
    n_heating: int
    n_cooling: int
    identified: bool


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """One replayable tick. Drive/measurement fields (top) are required and are
    the replay contract; the decision/context fields (defaulted) are for scoring.
    """

    v: int
    ts: float  # wall-clock epoch seconds (human anchor; NOT used for dt)
    mono: float  # monotonic seconds — the dt source for a deterministic replay
    room: float  # measured air temperature (the EKF measurement z)
    t_out: float  # effective outdoor temperature driving the model
    u_h: float  # heating drive in [0, 1]
    u_c: float  # cooling drive in [0, 1]
    q_solar: float  # normalised solar gain
    q_occ: float  # normalised occupancy gain
    alpha: float
    beta_h: float
    beta_c: float
    beta_s: float
    beta_o: float
    t_std: float
    n_idle: int
    n_heating: int
    n_cooling: int
    identified: bool
    mode: str = ""
    target: float = 0.0
    heat_sp: float = 0.0
    cool_sp: float = 0.0
    window_open: bool = False
    # Fed from the live tick feed's ``sensor_frozen`` key since v3. In v<=2
    # records this is permanently False (the historical mapping bug read the
    # non-existent key ``frozen``) — a replay must not treat an old False as
    # "sensor was healthy".
    frozen: bool = False
    mode_nudge_blocked: str = ""
    preheating: bool = False
    coasting: bool = False
    rh: float | None = None
    t_rm: float | None = None
    ca_deviation_k: float | None = None
    # --- v2: humidity / real-device axis ------------------------------------
    # Added in TRACE_VERSION 2 so a replayed trace can explain a dehumidification
    # episode (v1 recorded only Poise's thermal ``mode`` and never the humidity
    # axis or the actuator's real mode). All defaulted, so a v1 record loads
    # unchanged — that is the whole backward-compatibility mechanism.
    humidity_action: str = ""  # Poise RH decision: idle|cool|dry|dry_guard
    dry_active: bool = False  # dehumidification latch state
    device_hvac_mode: str = ""  # the REAL actuator mode: cool|dry|fan_only|off|...
    hvac_action: str = ""  # Poise zone resolved action: cooling|drying|idle|...
    dewpoint: float | None = None
    abs_humidity_gkg: float | None = None
    rh_ceiling: float | None = None  # category RH ceiling in effect [%]
    occupied: bool = False  # occupancy used by the humidity comfort gate
    # --- ADR-0066 humidity axis (added within v2; all defaulted, so records
    # from either side of the change load unchanged — same compat mechanism
    # as the v1->v2 fields, no version bump needed) ------------------------
    abs_humidity_gm3: float | None = None  # indoor absolute humidity [g/m³]
    abs_humidity_out_gm3: float | None = None  # outdoor comparison value
    surface_rh_mean: float | None = None  # EWMA surface RH — rule-1 trigger
    vent_action: str = ""  # ventilation advice: idle|open|close|discourage
    vent_reason: str = ""  # stable reason token (mold_risk|moisture_out|...)
    # --- Winter-gate instrumentation (added within v2, all defaulted — same
    # compat mechanism as the ADR-0066 fields, no version bump needed): the
    # shadow OUTPUTS (ADR-0033 flip criterion (b), ADR-0036/0037/0056) ride
    # along so cold-season flip evidence replays without the recorder's
    # ~10-day attribute history. -------------------------------------------
    mpc_active: bool = False
    mpc_setpoint: float | None = None  # would-be MPC setpoint [°C]
    mpc_weight: float | None = None  # confidence blend weight 0..1
    mpc_power: float | None = None  # would-be heating power 0..1
    tpi_duty: float | None = None  # would-be valve duty 0..1
    pi_setpoint: float | None = None  # would-be compensated setpoint [°C]
    pi_offset: float | None = None  # PI offset share [K]
    ref_offset: float | None = None  # actuator<->room frame offset [K]
    # --- Review C.8 write-convergence telemetry (added within v2, defaulted
    # — same compat mechanism, no version bump): consecutive unconverged
    # re-asserts/re-nudges so non-convergence episodes replay from the trace,
    # plus the cooling-failure verdict.
    sp_diverged_writes: int = 0
    mode_diverged_nudges: int = 0
    cooling_failure: bool = False
    # v3: the heating-failure verdict, symmetric to ``cooling_failure`` (the
    # feed published ``heating_failure`` all along; only the trace field was
    # missing). Defaulted, so v1/v2 records load unchanged.
    heating_failure: bool = False

    def to_json_line(self) -> str:
        """One compact JSON line; floats rounded and ``None`` fields dropped."""
        out: dict[str, Any] = {}
        for k, val in asdict(self).items():
            if val is None:
                continue
            out[k] = round(val, 4) if isinstance(val, float) else val
        return json.dumps(out, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json_line(cls, line: str) -> TraceRecord:
        return cls.from_dict(json.loads(line))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TraceRecord:
        """Build from a dict, ignoring unknown keys (forward-compatible reads)."""
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


def build_record(
    data: Mapping[str, Any],
    model: ModelSnapshot,
    *,
    ts: float,
    mono: float,
    room: float,
    t_out: float,
    u_h: float,
    u_c: float,
    q_solar: float = 0.0,
    q_occ: float = 0.0,
    rh: float | None = None,
    t_rm: float | None = None,
) -> TraceRecord:
    """Assemble a ``TraceRecord`` from the tick's raw drive inputs (explicit, the
    reliable replay contract) plus the coordinator's data dict (decision context,
    read defensively so a missing key degrades to a default, never raises)."""

    def _f(key: str) -> float:
        try:
            return float(data.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _b(key: str) -> bool:
        return bool(data.get(key, False))

    def _i(key: str) -> int:
        try:
            return int(data.get(key, 0))
        except (TypeError, ValueError):
            return 0

    def _maybe_f(key: str) -> float | None:
        val = data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    ca = data.get("ca_deviation_k")
    return TraceRecord(
        v=TRACE_VERSION,
        # ADR-0022: privacy quantisation — see TRACE_TS_QUANTUM_S above.
        ts=ts - (ts % TRACE_TS_QUANTUM_S),
        mono=mono,
        room=room,
        t_out=t_out,
        u_h=u_h,
        u_c=u_c,
        q_solar=q_solar,
        q_occ=q_occ,
        alpha=model.alpha,
        beta_h=model.beta_h,
        beta_c=model.beta_c,
        beta_s=model.beta_s,
        beta_o=model.beta_o,
        t_std=model.t_std,
        n_idle=model.n_idle,
        n_heating=model.n_heating,
        n_cooling=model.n_cooling,
        identified=model.identified,
        mode=str(data.get("mode", "")),
        target=_f("target_temperature"),
        heat_sp=_f("heat_sp"),
        cool_sp=_f("cool_sp"),
        window_open=_b("window_open"),
        # v3 fix: the feed key is ``sensor_frozen`` (phase_report), not
        # ``frozen`` — reading the latter recorded a permanent False.
        frozen=_b("sensor_frozen"),
        mode_nudge_blocked=str(data.get("mode_nudge_blocked", "")),
        preheating=_b("preheating"),
        coasting=_b("coasting"),
        rh=rh,
        t_rm=t_rm,
        ca_deviation_k=(float(ca) if ca is not None else None),
        humidity_action=str(data.get("humidity_action", "")),
        dry_active=_b("dry_active"),
        device_hvac_mode=str(data.get("device_hvac_mode", "")),
        hvac_action=str(data.get("hvac_action", "")),
        dewpoint=_maybe_f("dewpoint"),
        abs_humidity_gkg=_maybe_f("abs_humidity_gkg"),
        rh_ceiling=_maybe_f("rh_high_used"),
        occupied=_b("occupied"),
        abs_humidity_gm3=_maybe_f("abs_humidity_gm3"),
        abs_humidity_out_gm3=_maybe_f("abs_humidity_out_gm3"),
        surface_rh_mean=_maybe_f("surface_rh_mean"),
        vent_action=str(data.get("vent_action", "")),
        vent_reason=str(data.get("vent_reason", "")),
        mpc_active=_b("mpc_active"),
        mpc_setpoint=_maybe_f("mpc_setpoint"),
        mpc_weight=_maybe_f("mpc_weight"),
        mpc_power=_maybe_f("mpc_power"),
        tpi_duty=_maybe_f("tpi_duty"),
        pi_setpoint=_maybe_f("pi_setpoint"),
        pi_offset=_maybe_f("pi_offset"),
        ref_offset=_maybe_f("ref_offset"),
        sp_diverged_writes=_i("sp_diverged_writes"),
        mode_diverged_nudges=_i("mode_diverged_nudges"),
        cooling_failure=_b("cooling_failure"),
        heating_failure=_b("heating_failure"),
    )
