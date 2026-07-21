"""Pure trace-record composition.

The record BUILD stays fused with the append INSIDE
``_maybe_record_trace``'s ``_trace_enabled``-gated swallow boundary — a build
failure is swallowed (one DEBUG record, the tick lives).  Only the build
INSTRUCTIONS live in this pure module; the CALL SITE remains inside that
``try``, directly before the append, so both obligations hold structurally:

* swallow semantics — an exception raised anywhere in ``build_tick_record``
  propagates to the coordinator's ``except`` and is swallowed with the
  identical DEBUG log ("Poise trace capture failed", coordinator channel);
* append position — ``await self._trace_recorder.append(...)`` remains the
  LAST observable statement of the tick under the lock, its I/O duration counts
  into ``tick_ms`` (until F-TRACEIO).

The hass-bound pieces stay in the coordinator: the ``TraceRecorder`` lazy-init
(``hass.config.path``), the append await, and the swallowing ``except`` + DEBUG
log.  The queued ``TraceWriter`` with ``flush_on_unload()`` is the F-TRACEIO
decoupling — until then ``TickOutcome.trace_record`` stays ``None`` and the
record never leaves the swallow boundary.

``ModelSnapshot`` and ``build_record`` are already pure in ``trace/schema.py``,
so this module reduces to the one composition the coordinator performed inline:
EKF state vector → ``ModelSnapshot`` → ``build_record``.

Micro-reorder (unobservable): the coordinator now evaluates the
``ts=dt_util.utcnow().timestamp()`` ARGUMENT before this helper builds the
``ModelSnapshot``, whereas the inline code built the snapshot literal first and
read the clock inside the ``build_record(...)`` call.  A wall-clock read has no
side effects and no observer sits between the two positions — both orders
produce the identical record on the success path (one ``utcnow`` call either
way).

Hass-free, mypy --strict, py310-clean; measured by the PURE coverage gate
(``tests/test_phase8_trace.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..trace.schema import ModelSnapshot, TraceRecord, build_record

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..estimation.thermal_ekf import ThermalEKF


def build_tick_record(
    data: Mapping[str, Any],
    ekf: ThermalEKF,
    *,
    ts: float,
    mono: float,
    room: float,
    t_out: float,
    u_h: float,
    u_c: float,
    q_solar: float,
    rh: float | None,
    t_rm: float | None,
) -> TraceRecord:
    """Compose one replayable ``TraceRecord`` from the tick's drive inputs.

    The EKF's public state (``x[1..5]`` = alpha/beta_h/beta_c/beta_s/beta_o,
    the covariance-derived ``temperature_std``, the regime counters and the
    ``identified`` gate) becomes the ``ModelSnapshot``; ``build_record`` merges
    it with the coordinator's data dict (decision context, read defensively
    there — a missing key degrades, never raises).  ``q_occ`` keeps its
    ``build_record`` default of ``0.0`` (the coordinator never passes it).
    """
    snapshot = ModelSnapshot(
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
    return build_record(
        data,
        snapshot,
        ts=ts,
        mono=mono,
        room=room,
        t_out=t_out,
        u_h=u_h,
        u_c=u_c,
        q_solar=q_solar,
        rh=rh,
        t_rm=t_rm,
    )
