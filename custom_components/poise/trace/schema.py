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

TRACE_VERSION: int = 1


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
    frozen: bool = False
    mode_nudge_blocked: str = ""
    preheating: bool = False
    coasting: bool = False
    rh: float | None = None
    t_rm: float | None = None
    ca_deviation_k: float | None = None

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

    ca = data.get("ca_deviation_k")
    return TraceRecord(
        v=TRACE_VERSION,
        ts=ts,
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
        frozen=_b("frozen"),
        mode_nudge_blocked=str(data.get("mode_nudge_blocked", "")),
        preheating=_b("preheating"),
        coasting=_b("coasting"),
        rh=rh,
        t_rm=t_rm,
        ca_deviation_k=(float(ca) if ca is not None else None),
    )
