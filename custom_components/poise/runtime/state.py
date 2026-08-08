"""Grouped mutable runtime state owned by ``ZoneRuntime``.

Groups the long-lived, mutable domain state into eleven typed dataclasses so
ownership is explicit: long-lived persisted state always lives here, never "in
the pipeline".  The classes are deliberately *mutable* — they model state that
is updated tick over tick — in contrast to the frozen per-tick contracts in
``tick_inputs``/``tick_result``.

Each class carries ``PERSISTED_FIELDS``: the exact subset of its field names
that the persistence codec serialises; everything not listed is transient and
must be rebuilt or re-latched after a restart.  Field names drop the leading
underscore of the coordinator attribute they replace (``_override`` ->
``override``); where the storage key differs from the field name the class
docstring maps it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final

from ..control.comfort_activation import ComfortActivation
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

# The own-write context ring is bounded so it can never grow without limit.
_OWN_WRITE_CTX_CAPACITY: Final = 16

# The adaptive open threshold starts at the *default* window-auto config value;
# the owner re-seeds it from the zone's tuned ``WindowAutoConfig`` when one is
# configured.
_DEFAULT_WA_OPEN_THRESHOLD: Final[float] = WindowAutoConfig().open_threshold


def _own_ctx_ring() -> deque[str]:
    """Fresh bounded ring of HA ``Context`` ids for own-write echo detection."""
    return deque(maxlen=_OWN_WRITE_CTX_CAPACITY)


@dataclass(slots=True)
class UserControlState:
    """Store-owned user intention: enable, preset, holds, Boost (ADR-0059).

    Persisted: every field except ``last_adopt_log`` (a pure log-debounce
    latch).  ``climate_mode`` lives here (not in ``ZoneTuning``) because it is
    store-owned, not config-owned.  ``override_policy`` is config-owned
    (``ZoneTuning``) and therefore *not* a field here even though the payload
    stores a copy of it.
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
            "feedback_stats",
            "suggestion_rejected_key",
            "suggestion_rejected_at",
            "clo_suggestion_rejected_key",
            "clo_suggestion_rejected_at",
            "season_hint_last_active_ts",
        }
    )

    enabled: bool = True
    preset: OverrideMode = OverrideMode.NONE
    climate_mode: str = "auto"
    window_bypass: bool = False  # ignore window reaction (ADR-0041 stage 2)
    override: float | None = None
    # A device-side hvac_mode the user set, adopted as a manual mode-hold
    # sharing the setpoint hold's lifecycle.
    mode_override: str | None = None
    override_set_wall: float | None = None
    override_requested: float | None = None  # pre-clamp user ask
    override_expires_at: float | None = None  # announced at set-time (ADR-0059)
    # ADR-0059 §1: was the announced expiry the switchpoint (not the timer
    # fallback / max_h cap)? -> expiry-reason accuracy.
    override_expiry_is_switchpoint: bool = False
    override_reason: str | None = None  # origin of the active hold
    boost_expires_at: float | None = None
    boost_prev_preset: OverrideMode | None = None  # pre-Boost preset, restored
    override_stats: list[dict[str, Any]] = field(default_factory=list)  # §5 stats
    # ADR-0067 F1: explicit comfort-feedback statistic (observe only, cap 50).
    feedback_stats: list[dict[str, Any]] = field(default_factory=list)
    # ADR-0060 L2: a rejected suggestion suppresses exactly that pattern key
    # for 30 days — wall-clock stamped, restart-proof.
    suggestion_rejected_key: str | None = None
    suggestion_rejected_at: float | None = None
    # ADR-0067 F2: own cool-down slot for the clo family — a clo rejection
    # must not overwrite a remembered L2 rejection.
    clo_suggestion_rejected_key: str | None = None
    clo_suggestion_rejected_at: float | None = None
    # ADR-0060 §3 season gate: wall-clock of the last tick the season-mode
    # hint stood.  Floors the L2 emission detection (mismatch-era overrides
    # are mode signals, not comfort evidence) — persisted, because a mode
    # switch or a restart clears the HINT without clearing the contamination.
    season_hint_last_active_ts: float | None = None
    last_adopt_log: str = ""  # transient: debounces the adoption-suppression log


@dataclass(slots=True)
class ExternalOverrideRuntime:
    """Echo/adoption baselines for external-change detection.

    All baselines live in ONE object.  The four value baselines persist (B5,
    ADR-0059 §9) so the first device-side intervention after a restart has
    something to compare against; the monotonic stamps and the attempt-state
    context ring stay transient — they are process-local, so the restore path
    stamps the echo windows stale instead of resurrecting them.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "last_written_sp",
            "prev_device_sp",
            "last_commanded_hvac",
            "prev_device_mode",
            "last_commanded_fan",
            "prev_device_fan",
        }
    )

    last_written_sp: float | None = None  # last commanded (snapped)
    # Device setpoint at the previous tick — a genuine user change *moves* it,
    # a device re-quantise of our own write does not.
    prev_device_sp: float | None = None
    last_commanded_hvac: str | None = None  # mode echo baseline
    prev_device_mode: str | None = None  # mode move-guard
    # ADR-0068 U3: fan-stage echo baselines (B5-analog value baselines).
    last_commanded_fan: str | None = None
    prev_device_fan: str | None = None
    last_sp_write_ts: float | None = None  # ADR-0052 §4 nudge throttle
    last_hvac_cmd_ts: float | None = None
    last_fan_cmd_ts: float | None = None  # ADR-0068 fan echo window (transient)
    # Attempt-state: device setpoint captured immediately before our last
    # write — updated even when the write call fails.
    pre_write_sp: float | None = None
    # Attempt-state: HA Context ids of our own actuator service calls.
    own_write_ctx_ids: deque[str] = field(default_factory=_own_ctx_ring)


@dataclass(slots=True)
class ActuatorRuntime:
    """Last actuator write results and the external-temperature feed anchor.

    Persisted: only ``has_actuated`` (the teardown-park gate); the write/feed
    anchors are transient success-state rebuilt by the next tick's commit.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"has_actuated"})

    last_target: float | None = None
    last_written_mode: str | None = None
    # True once any setpoint/mode write SUCCEEDED this run; gates the teardown
    # park so a zone that never actuated is not "parked".
    has_actuated: bool = False
    last_fed: float | None = None
    last_fed_ts: float = 0.0  # external-feed keep-alive (monotonic)


@dataclass(slots=True)
class LearningRuntime:
    """Thermal models and their observation anchors (EKF, ADR-0002/0024).

    Persisted: the models — ``ekf``, ``trm_tracker`` (storage key ``trm``),
    ``seasonless``, ``ref_offset``, ``tau_settle``.  The monotonic anchors are
    transient by construction, and ``pi`` is deliberately NOT persisted: its
    accumulator is cross-tick runtime state only.
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
    tau_settle: TauSettle | None = None  # settle-based tau-confidence
    tau_last_mono: float | None = None  # real dt for the tau settle EWMA
    pi: PiCompensator = field(default_factory=PiCompensator)


@dataclass(slots=True)
class WindowRuntime:
    """Window-open detection state: sensor latch + sensorless slope detector.

    Persisted: only the ``window_auto`` model (ADR-0041).  ``window_open_since``
    is a monotonic stamp and must NEVER be persisted — it resets on restart by
    design.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"window_auto"})

    window_auto: WindowAutoState = field(default_factory=WindowAutoState)
    was_cooling: bool = False  # last tick cooled -> gate the window slope
    wa_ref_room: float | None = None  # last distinct-move reference
    wa_ref_mono: float | None = None
    wa_prev_mono: float | None = None  # last tick, for the minutes_open dt
    wa_open_threshold: float = _DEFAULT_WA_OPEN_THRESHOLD
    last_window_open: bool = False  # cached for the stats snapshot
    # Monotonic stamp of the current open episode's rising edge; gates the
    # mould write-floor for its first WINDOW_MOULD_SUPPRESS_S.
    window_open_since: float | None = None


@dataclass(slots=True)
class PresenceRuntime:
    """Presence flip tracking and room-absence anchor (ADR-0058).

    Fully transient (no presence keys are persisted): a restart deliberately
    resumes as "present".
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    prev_home: bool | None = None  # house-gate flip tracking
    last_presence_level: str = "comfort"  # cached for the stats snapshot
    room_absent_since: float | None = None  # transient; restart -> present


@dataclass(slots=True)
class HumidityRuntime:
    """Long-lived humidity state; the dry decision itself runs live per tick.

    Persisted: ``dry_active`` — the hysteresis latch must survive a restart
    between the RH thresholds or the room drops out of dry mode until RH
    re-crosses the upper bound.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"dry_active", "vent_active", "surface_rh_mean"}
    )

    dry_active: bool = False  # ADR-0050/0051 dry-active hysteresis latch
    # ADR-0066 humidity axis (advice-only): the ventilation-advice hysteresis
    # latch and the ~48 h surface-RH EWMA (the mould CAUSE) — the mean must
    # survive a restart or every reboot forgets days of wall history.
    vent_active: bool = False
    surface_rh_mean: float | None = None
    # ADR-0066 B.5: previous advice-ACTION token for the emission edge.
    # Deliberately TRANSIENT (not persisted): "" after a restart makes the
    # edge re-announce a still-open episode (the notification survives the
    # reboot) and stay silent when settling into idle.
    vent_last_action: str = ""


@dataclass(slots=True)
class CompressorRuntime:
    """Compressor lifecycle fold and the derived dynamics profile (ADR-0046).

    Persisted: ``multi_lifecycle`` (wall-clock run-state) so anti-short-cycle
    timers survive a restart; ``dynamics`` is derived from the actuator each
    tick (ADR-0052) and therefore transient.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"multi_lifecycle"})

    multi_lifecycle: DeviceLifecycle = field(default_factory=DeviceLifecycle)
    dynamics: DeviceDynamics = DeviceDynamics.SLOW_HYDRONIC


@dataclass(slots=True)
class SafetyRuntime:
    """Domain safety state that feeds regulation and learning gates.

    Fully transient (no safety keys are persisted): failure detection and
    unavailability re-arm from live observations after a restart.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    failure: HeatingFailureDetector = field(default_factory=HeatingFailureDetector)
    # Previous tick's failure verdict — latched so the learn gate can pause EKF
    # learning during a boiler-off/valve-open episode.
    prev_heating_failed: bool = False
    unavailable_since: float | None = None  # sustained sensor loss anchor


@dataclass(slots=True)
class DiagnosticsRuntime:
    """Long-lived diagnostic accumulators (ADR-0044/0045/0055).

    Persisted: the stats objects ``outcome_stats``, ``regq`` (storage key
    ``regulation_quality``) and ``hdh`` (storage key ``hdh_savings``).  The dt
    anchors, the open scoring session and the warn-once latch are transient.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"outcome_stats", "regq", "hdh", "comfort_activation"}
    )

    outcome_stats: OutcomeStats = field(default_factory=OutcomeStats)
    regq: RegulationQuality = field(default_factory=RegulationQuality)
    # ADR-0069 U2: persisted tier-2 activation lifecycle (latch, qualified
    # dwell, baseline + signature). Documented ownership boundary: it lives
    # HERE next to the quality metrics it consumes (regq) — long-lived
    # release state, neither a diagnostic accumulator nor an anti-chatter
    # latch; PipelineLatches is explicitly forbidden (ADR-0069 Rev. 4).
    comfort_activation: ComfortActivation = field(default_factory=ComfortActivation)
    ca_last_mono: float | None = None  # real dt for the CA metric
    # ADR-0055 N1: own elapsed anchor for the time-weighted PPD fold — PMV
    # validity and the CA fairness mask diverge, so the PPD clock is separate.
    ppd_last_mono: float | None = None
    outcome_session: OutcomeSession = field(default_factory=OutcomeSession)
    hdh_last_mono: float | None = None  # real dt for HDH/outcome obs
    hdh: HdhSavings = field(default_factory=HdhSavings)
    # Warn once per run, not per tick — one latch per climate-band boundary
    # since F-HUMSHADOW split the live humidity decision from the pure shadows.
    hum_shadow_warned: bool = False
    climate_shadow_warned: bool = False
    # ADR-0054 Nachtrag V1: today's forecast daily mean for the clo blend,
    # latched once per local day.  Deliberately TRANSIENT: the first tick
    # after a restart recomputes it from the forecast cache.
    clo_forecast_key: str | None = None
    clo_forecast_day: float | None = None
    # ADR-0060 §2: hysteresis anchor of the season-mode advisory — transient
    # (T_rm re-raises the hint after a restart when still clearly beyond the
    # threshold; inside the hysteresis band it simply clears).  The §3 season
    # GATE does NOT depend on this anchor: it floors on the persisted
    # ``UserControlState.season_hint_last_active_ts`` and survives restarts.
    season_hint_prev: str | None = None
    # ADR-0067 #4: which suggestion family currently holds the emission slot
    # ("override"/"clo") - transient; after a restart a fresh tie resolves to
    # the override family (documented edge).
    pending_suggestion_family: str | None = None


@dataclass(slots=True)
class PipelineLatches:
    """Transient anti-chatter latches carried tick-to-tick by the pipeline.

    Never persisted (they re-latch within one tick).  Deliberately WITHOUT the
    tick budget: ``_tick_budget`` is a coordinator/adapter metric (wall time
    incl. I/O), not domain state.
    """

    PERSISTED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    # ADR-0025/0034: prior tick's engage state so the planner holds
    # preheat/coast until the room crosses target instead of flapping.
    was_preheating: bool = False
    was_coasting: bool = False
    cool_sp_eff_prev: float | None = None  # ADR-0051 rate-limit anchor
