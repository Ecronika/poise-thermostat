"""Grouped mutable runtime state for the future ``ZoneRuntime`` (plan phase 1).

Today ``PoiseCoordinator.__init__`` (coordinator.py L299-587) holds 138 loose
``self._*`` attributes.  This module groups the long-lived, mutable domain
state into eleven typed dataclasses (refactoring plan, section 3) so ownership
becomes explicit: long-lived persisted state always lives here, never "in the
pipeline".  The classes are deliberately *mutable* — they model state that is
updated tick over tick — in contrast to the frozen per-tick contracts in
``tick_inputs``/``tick_result``.

Each class carries ``PERSISTED_FIELDS``: the exact subset of its field names
that the phase-3 persistence codec serialises.  The split mirrors today's
``_save_payload`` (coordinator.py L1665-1719) and the restore path
(L896-1063); everything not listed is transient and must be rebuilt or
re-latched after a restart.  Field names drop the leading underscore of the
coordinator attribute they replace (``_override`` -> ``override``); where the
storage key differs from the field name the class docstring maps it.

Phase-1 scope: type definitions only — no production code imports this module
yet, so introducing it cannot change behaviour.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final

from ..control.dynamics import DeviceDynamics
from ..control.hdh_savings import HdhSavings
from ..control.outcome_scoring import OutcomeSession, OutcomeStats
from ..control.override import OverrideMode
from ..control.pi import PiCompensator
from ..control.reference_offset import OffsetEstimate
from ..control.regulation_quality import RegulationQuality
from ..control.window_auto import WindowAutoConfig, WindowAutoState
from ..estimation.heatup_rate import HeatupAccumulator
from ..estimation.running_mean import RunningMeanTracker
from ..estimation.seasonless_rate import SeasonlessRate
from ..estimation.tau_settle import TauSettle
from ..estimation.thermal_ekf import ThermalEKF
from ..multi.lifecycle import DeviceLifecycle
from ..safety.heating_failure import HeatingFailureDetector

# V2: the own-write context ring is bounded so it can never grow without limit;
# 16 matches today's ``deque(maxlen=16)`` (coordinator.py L359).
_OWN_WRITE_CTX_CAPACITY: Final = 16

# The adaptive open threshold starts at the *default* window-auto config value
# (coordinator.py L326); the owner re-seeds it from the zone's tuned
# ``WindowAutoConfig`` when one is configured.
_DEFAULT_WA_OPEN_THRESHOLD: Final[float] = WindowAutoConfig().open_threshold


def _own_ctx_ring() -> deque[str]:
    """Fresh bounded ring of HA ``Context`` ids for own-write echo detection."""
    return deque(maxlen=_OWN_WRITE_CTX_CAPACITY)


@dataclass(slots=True)
class UserControlState:
    """Store-owned user intention: enable, preset, holds, Boost (ADR-0059).

    Persisted: every field except ``last_adopt_log`` (a pure log-debounce
    latch) — see ``_save_payload`` (coordinator.py L1665-1719, user-intent
    keys L1686-1705 and ``climate_mode`` L1717).  ``climate_mode`` lives here
    (not in ``ZoneTuning``) because it is store-owned, not config-owned.
    Note: ``override_policy`` is config-owned (``ZoneTuning``) and therefore
    *not* a field here even though today's payload stores a copy of it.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "enabled",
            "preset",
            "climate_mode",
            "window_bypass",
            "override",
            "mode_override",
            "override_set_wall",
            "override_requested",
            "override_expires_at",
            "override_expiry_is_switchpoint",
            "override_reason",
            "boost_expires_at",
            "boost_prev_preset",
            "override_stats",
        }
    )

    enabled: bool = True
    preset: OverrideMode = OverrideMode.NONE
    climate_mode: str = "auto"
    window_bypass: bool = False  # ignore window reaction (ADR-0041 stage 2)
    override: float | None = None
    # K2: a device-side hvac_mode the user set, adopted as a manual mode-hold
    # sharing the setpoint hold's lifecycle.
    mode_override: str | None = None
    override_set_wall: float | None = None
    override_requested: float | None = None  # pre-clamp user ask
    override_expires_at: float | None = None  # announced at set-time (ADR-0059)
    # ADR-0059 §1: was the announced expiry the switchpoint (not the timer
    # fallback / max_h cap)? -> expiry-reason accuracy.
    override_expiry_is_switchpoint: bool = False
    override_reason: str | None = None  # K3: origin of the active hold
    boost_expires_at: float | None = None
    boost_prev_preset: OverrideMode | None = None  # VT#1961 restore
    override_stats: list[dict[str, Any]] = field(default_factory=list)  # §5 L1
    last_adopt_log: str = ""  # transient: debounces the K3 suppression log


@dataclass(slots=True)
class ExternalOverrideRuntime:
    """Echo-/adoption baselines for external-change detection (finding 8).

    All baselines live in ONE object.  The four value baselines are persisted
    (``_save_payload`` L1713-1716, B5) so the first device-side intervention
    after a restart has something to compare against; the monotonic stamps and
    the attempt-state context ring are deliberately transient — they are
    process-local, so the restore path stamps the echo windows as expired
    (coordinator.py L955-959) instead of resurrecting them.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "last_written_sp",
            "prev_device_sp",
            "last_commanded_hvac",
            "prev_device_mode",
        }
    )

    last_written_sp: float | None = None  # P1-4a: last commanded (snapped)
    # P1-4a: device setpoint at the previous tick — a genuine user change
    # *moves* it, a device re-quantise of our own write does not.
    prev_device_sp: float | None = None
    last_commanded_hvac: str | None = None  # mode echo baseline
    prev_device_mode: str | None = None  # mode move-guard
    last_sp_write_ts: float | None = None  # ADR-0052 §4 nudge throttle
    last_hvac_cmd_ts: float | None = None
    # V1 attempt-state (finding 9): device setpoint captured immediately
    # before our last write — updated even when the write call fails.
    pre_write_sp: float | None = None
    # V2 attempt-state: HA Context ids of our own actuator service calls.
    own_write_ctx_ids: deque[str] = field(default_factory=_own_ctx_ring)


@dataclass(slots=True)
class ActuatorRuntime:
    """Last actuator write results and the external-temperature feed anchor.

    Persisted: only ``has_actuated`` (AR-11 teardown-park gate, payload
    L1718 of ``_save_payload`` coordinator.py L1665-1719); the write/feed
    anchors are transient success-state rebuilt by the next tick's commit.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"has_actuated"})

    last_target: float | None = None
    last_written_mode: str | None = None
    # AR-11: True once any setpoint/mode write SUCCEEDED this run; gates the
    # teardown park so a zone that never actuated is not "parked".
    has_actuated: bool = False
    last_fed: float | None = None
    last_fed_ts: float = 0.0  # P2-2 external-feed keep-alive (monotonic)


@dataclass(slots=True)
class LearningRuntime:
    """Thermal models and their observation anchors (EKF, ADR-0002/0024).

    Persisted: the models — ``ekf``, ``trm_tracker`` (storage key ``trm``),
    ``seasonless``, ``ref_offset``, ``tau_settle`` (``_save_payload``
    coordinator.py L1665-1719).  The monotonic anchors are transient by
    construction, and ``pi`` is deliberately NOT persisted (finding 3): its
    accumulator is cross-tick runtime state only (F-PIACC, phase 10).
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"ekf", "trm_tracker", "seasonless", "ref_offset", "tau_settle"}
    )

    ekf: ThermalEKF = field(default_factory=ThermalEKF)
    trm_tracker: RunningMeanTracker = field(default_factory=RunningMeanTracker)
    seasonless: SeasonlessRate = field(default_factory=SeasonlessRate)
    prev_room: float | None = None
    prev_room_mono: float | None = None
    # anti-quantization anchor for the seasonless heat-up rate (ADR-0004/0009)
    heatup_acc: HeatupAccumulator = field(default_factory=HeatupAccumulator)
    last_mono: float | None = None
    last_u_h: float = 0.0
    last_u_c: float = 0.0
    last_q_solar: float = 0.0
    ref_offset: OffsetEstimate | None = None  # ADR-0056 actuator<->room
    ref_last_mono: float | None = None  # real dt for the offset EWMA
    tau_settle: TauSettle | None = None  # settle-based tau-confidence (T343)
    tau_last_mono: float | None = None  # real dt for the tau settle EWMA
    pi: PiCompensator = field(default_factory=PiCompensator)


@dataclass(slots=True)
class WindowRuntime:
    """Window-open detection state: sensor latch + sensorless slope detector.

    Persisted: only the ``window_auto`` model (ADR-0041; ``_save_payload``
    coordinator.py L1665-1719).  ``window_open_since`` is a monotonic stamp
    and must NEVER be persisted (comment at payload L1683-1685) — it resets
    on restart by design.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"window_auto"})

    window_auto: WindowAutoState = field(default_factory=WindowAutoState)
    was_cooling: bool = False  # last tick cooled -> gate the window slope
    wa_ref_room: float | None = None  # last distinct-move reference (V6)
    wa_ref_mono: float | None = None
    wa_prev_mono: float | None = None  # last tick, for the minutes_open dt
    wa_open_threshold: float = _DEFAULT_WA_OPEN_THRESHOLD
    last_window_open: bool = False  # cached for the §5 stat
    # P2-1: monotonic stamp of the current open episode's rising edge; gates
    # the mould write-floor for its first WINDOW_MOULD_SUPPRESS_S.
    window_open_since: float | None = None


@dataclass(slots=True)
class PresenceRuntime:
    """Presence flip tracking and room-absence anchor (ADR-0058).

    Fully transient (``_save_payload`` coordinator.py L1665-1719 has no
    presence keys): a restart deliberately resumes as "present".
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    prev_home: bool | None = None  # §1 house-gate flip tracking
    last_presence_level: str = "comfort"  # cached for the §5 stat
    room_absent_since: float | None = None  # transient; restart -> present


@dataclass(slots=True)
class HumidityRuntime:
    """Long-lived humidity state; the dry decision itself runs live per tick.

    Persisted: ``dry_active`` (R9, ``_save_payload`` coordinator.py L1686) —
    the hysteresis latch must survive a restart between the RH thresholds or
    the room drops out of dry mode until RH re-crosses the upper bound.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"dry_active"})

    dry_active: bool = False  # ADR-0050/0051 dry-active hysteresis latch


@dataclass(slots=True)
class CompressorRuntime:
    """Compressor lifecycle fold and the derived dynamics profile (ADR-0046).

    Persisted: ``multi_lifecycle`` (wall-clock run-state, ``_save_payload``
    coordinator.py L1671) so anti-short-cycle timers survive a restart;
    ``dynamics`` is derived from the actuator each tick (ADR-0052) and
    therefore transient.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"multi_lifecycle"})

    multi_lifecycle: DeviceLifecycle = field(default_factory=DeviceLifecycle)
    dynamics: DeviceDynamics = DeviceDynamics.SLOW_HYDRONIC


@dataclass(slots=True)
class SafetyRuntime:
    """Domain safety state that feeds regulation and learning gates.

    Fully transient (``_save_payload`` coordinator.py L1665-1719 has no
    safety keys): failure detection and unavailability re-arm from live
    observations after a restart.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    failure: HeatingFailureDetector = field(default_factory=HeatingFailureDetector)
    # R3: previous tick's failure verdict — latched so the learn gate can
    # pause EKF learning during a boiler-off/valve-open episode (VTherm #1428).
    prev_heating_failed: bool = False
    unavailable_since: float | None = None  # sustained sensor loss anchor


@dataclass(slots=True)
class DiagnosticsRuntime:
    """Long-lived diagnostic accumulators (ADR-0044/0045/0055).

    Persisted: the stats objects ``outcome_stats``, ``regq`` (storage key
    ``regulation_quality``) and ``hdh`` (storage key ``hdh_savings``) —
    ``_save_payload`` coordinator.py L1672-1680.  The dt anchors, the open
    scoring session and the warn-once latch are transient.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"outcome_stats", "regq", "hdh"}
    )

    outcome_stats: OutcomeStats = field(default_factory=OutcomeStats)
    regq: RegulationQuality = field(default_factory=RegulationQuality)
    ca_last_mono: float | None = None  # real dt for the CA metric
    outcome_session: OutcomeSession = field(default_factory=OutcomeSession)
    hdh_last_mono: float | None = None  # F9: real dt for HDH/outcome obs
    hdh: HdhSavings = field(default_factory=HdhSavings)
    hum_shadow_warned: bool = False  # AR-32: warn once per run, not per tick


@dataclass(slots=True)
class PipelineLatches:
    """Transient anti-chatter latches carried tick-to-tick by the pipeline.

    Never persisted (they re-latch within one tick; ``_save_payload``
    coordinator.py L1665-1719 has no such keys).  Deliberately WITHOUT the
    tick budget: ``_tick_budget`` is a coordinator/adapter metric (wall time
    incl. I/O), not domain state (plan rev. 5).
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    # ADR-0025/0034: prior tick's engage state so the planner holds
    # preheat/coast until the room crosses target instead of flapping.
    was_preheating: bool = False
    was_coasting: bool = False
    cool_sp_eff_prev: float | None = None  # ADR-0051 rate-limit anchor
