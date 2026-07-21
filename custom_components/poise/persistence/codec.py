"""Storage-format codec for one Poise zone.

Single owner of the persisted store FORMAT: :func:`encode` produces the v1
payload dict and :func:`decode` reproduces the restore-side parsing —
including its deliberate gates and non-restores — as independently robust
sections.  Pure: stdlib + poise pure modules only, no Home Assistant import.

Format versions (no explicit version field — deliberate, the gate is pinned
by ``test_store_without_ekf_key_is_legacy_branch``):

* **v1** — a dict WITH an ``"ekf"`` key.  The restore gate is exactly
  ``isinstance(data, dict) and "ekf" in data``: a dict store WITHOUT the
  ``ekf`` key does NOT restore the user-intent keys either, even if they are
  present — it is classified ``legacy_bare_ekf``.
* **v0** (``legacy_bare_ekf``) — any other non-``None`` payload, a bare
  ``ThermalEKF.to_dict()``.  Parsing lives in
  :func:`..persistence.migrations.migrate_v0_bare_ekf`; "corrupt -> fresh"
  stays with the caller (the coordinator's broad restore boundary).

Deliberate non-restores / never-in-schema:

* ``override_policy`` is stored but NEVER applied on restore (ADR-0007): a
  config-owned hot-apply option — restoring it would revert a user's options
  change on every restart.  :func:`decode` still surfaces the stored value,
  marked via :data:`CONFIG_OWNED_KEYS`.  Pinned by
  ``test_override_policy_option_change_survives_restart``.
* Monotonic timestamps are never in schema (B5, ADR-0059 §9 / ADR-0007): the
  restore side stamps echo windows stale — a coordinator DOMAIN hook, not
  codec.  Covers ``_last_sp_write_ts`` / ``_last_hvac_cmd_ts`` and
  ``_window_open_since``.
* ``_pi`` / ``_pi.acc`` has no schema key.
* All presence/safety/latch/anchor attributes: their runtime groups declare
  ``PERSISTED_FIELDS = frozenset()``.

Domain-restore hooks that deliberately do NOT live here (coordinator /
``ZoneRuntime.restore()``): echo-window stale stamping, the
``resolve_hold_expiry`` recompute, EKF cold-start seeding, configured
ext-temp vetting and issue re-adoption.  The wall-clock anchor the
``multi_lifecycle`` restore needs is injected explicitly as ``now_wall``.

Error semantics of :func:`decode`: the cheap sections (user state, override
lifecycle, adoption baselines) use per-key defensive coercions and can never
fail on JSON-typed input; the heavy model tail (learned models + diagnostic
accumulators) is ONE sequential prefix parse in a fixed restore order —
``ekf`` -> ``trm`` -> ``seasonless`` -> ``window_auto`` -> ``multi_lifecycle``
-> ``outcome_stats`` -> ``regulation_quality`` -> ``ref_offset`` ->
``tau_settle`` -> ``hdh_savings`` -> ``dry_active``.  The FIRST structural
throw stops the parse: every model parsed before the throwing key is kept,
every later field stays undecoded (``None``), and it can never cost the
user-intent sections.  The original exception is surfaced as
``DecodedPersistence.model_error`` so the caller can re-raise it into its
broad restore boundary — "corrupt -> fresh" AND the single recovery log
record stay with the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Literal

from ..control.hdh_savings import HdhSavings
from ..control.outcome_scoring import OutcomeStats
from ..control.override import OverrideMode
from ..control.reference_offset import OffsetEstimate
from ..control.regulation_quality import RegulationQuality
from ..control.window_auto import WindowAutoState
from ..estimation.running_mean import RunningMeanTracker
from ..estimation.seasonless_rate import SeasonlessRate
from ..estimation.tau_settle import TauSettle
from ..estimation.thermal_ekf import ThermalEKF
from ..multi import lifecycle as _lifecycle
from ..multi.lifecycle import DeviceLifecycle

# The v1 payload key set, in insertion order (the wire order of the dict).
# 31 keys = the 30-field union of the ``PERSISTED_FIELDS`` constants in
# ``runtime/state.py`` (three storage-key renames, see STORAGE_KEY_RENAMES)
# plus the config-owned ``override_policy`` special case.
PAYLOAD_KEYS: Final[tuple[str, ...]] = (
    "ekf",
    "trm",
    "seasonless",
    "window_auto",
    "multi_lifecycle",
    "outcome_stats",
    "regulation_quality",
    "ref_offset",
    "tau_settle",
    "hdh_savings",
    "dry_active",
    "window_bypass",
    "preset",
    "enabled",
    "override",
    "mode_override",
    "override_set_wall",
    "override_requested",
    "override_policy",
    "override_expires_at",
    "override_expiry_is_switchpoint",
    "boost_expires_at",
    "boost_prev_preset",
    "override_stats",
    "override_reason",
    "last_written_sp",
    "prev_device_sp",
    "last_commanded_hvac",
    "prev_device_mode",
    "climate_mode",
    "has_actuated",
)

# State-group field name -> storage key, where they differ (documented in the
# ``runtime/state.py`` docstrings; fixed here as the codec's contract).
STORAGE_KEY_RENAMES: Final[dict[str, str]] = {
    "trm_tracker": "trm",
    "regq": "regulation_quality",
    "hdh": "hdh_savings",
}

# Payload keys that are stored but must NEVER be applied on restore:
# ``override_policy`` is a config-entry option (``ZoneTuning``), already read
# by the config parser — applying the stored copy would revert an options
# change on every restart.  Pinned by
# ``test_override_policy_option_change_survives_restart``.
CONFIG_OWNED_KEYS: Final[frozenset[str]] = frozenset({"override_policy"})

PayloadKind = Literal["v1", "legacy_bare_ekf", "empty"]


@dataclass(frozen=True, slots=True)
class PersistedZoneState:
    """Typed snapshot of everything the v1 payload persists (encode input).

    Field names follow the ``runtime/state.py`` groups (leading underscore of
    the coordinator attribute dropped); the three storage-key renames are in
    :data:`STORAGE_KEY_RENAMES`.  ``override_policy`` is the CONFIG value
    (stored for diagnostics, never restored).
    """

    # learning (LearningRuntime + WindowRuntime + CompressorRuntime)
    ekf: ThermalEKF
    trm_tracker: RunningMeanTracker  # storage key "trm"
    seasonless: SeasonlessRate
    window_auto: WindowAutoState
    multi_lifecycle: DeviceLifecycle
    ref_offset: OffsetEstimate | None
    tau_settle: TauSettle | None
    # diagnostics (DiagnosticsRuntime + HumidityRuntime)
    outcome_stats: OutcomeStats
    regq: RegulationQuality  # storage key "regulation_quality"
    hdh: HdhSavings  # storage key "hdh_savings"
    dry_active: bool
    # user intent (UserControlState) + actuation latch (ActuatorRuntime)
    enabled: bool
    preset: OverrideMode
    climate_mode: str
    window_bypass: bool
    has_actuated: bool
    # override lifecycle (UserControlState, ADR-0059)
    override: float | None
    mode_override: str | None
    override_set_wall: float | None
    override_requested: float | None
    override_policy: str  # config-owned; stored, never restored
    override_expires_at: float | None
    override_expiry_is_switchpoint: bool
    boost_expires_at: float | None
    boost_prev_preset: OverrideMode | None
    override_stats: list[dict[str, Any]]
    override_reason: str | None
    # adoption baselines (ExternalOverrideRuntime, ADR-0059 §9)
    last_written_sp: float | None
    prev_device_sp: float | None
    last_commanded_hvac: str | None
    prev_device_mode: str | None

    def to_dict(self) -> dict[str, Any]:
        """The v1 store dict (key set, transforms, values).

        Timestamp keys are wall-clock only; the monotonic stamps
        (``_last_sp_write_ts``/``_last_hvac_cmd_ts``, ``_window_open_since``)
        are deliberately absent, as is any ``_pi`` state.
        ``override_stats`` is passed by reference.
        """
        return {
            "ekf": self.ekf.to_dict(),
            "trm": self.trm_tracker.to_dict(),
            "seasonless": self.seasonless.to_dict(),
            "window_auto": self.window_auto.to_dict(),
            "multi_lifecycle": _lifecycle.to_dict(self.multi_lifecycle),
            "outcome_stats": self.outcome_stats.to_dict(),
            "regulation_quality": self.regq.to_dict(),
            "ref_offset": (
                self.ref_offset.to_dict() if self.ref_offset is not None else None
            ),
            "tau_settle": (
                self.tau_settle.to_dict() if self.tau_settle is not None else None
            ),
            "hdh_savings": self.hdh.to_dict(),
            "dry_active": self.dry_active,
            "window_bypass": self.window_bypass,
            "preset": self.preset.value,
            "enabled": self.enabled,
            "override": self.override,
            "mode_override": self.mode_override,  # manual mode-hold
            "override_set_wall": self.override_set_wall,
            "override_requested": self.override_requested,
            "override_policy": self.override_policy,
            "override_expires_at": self.override_expires_at,
            "override_expiry_is_switchpoint": self.override_expiry_is_switchpoint,
            "boost_expires_at": self.boost_expires_at,
            "boost_prev_preset": (
                self.boost_prev_preset.value
                if self.boost_prev_preset is not None
                else None
            ),
            "override_stats": self.override_stats,
            "override_reason": self.override_reason,  # hold origin
            "last_written_sp": self.last_written_sp,
            "prev_device_sp": self.prev_device_sp,
            "last_commanded_hvac": self.last_commanded_hvac,
            "prev_device_mode": self.prev_device_mode,
            "climate_mode": self.climate_mode,
            "has_actuated": self.has_actuated,  # teardown-park gate
        }


def encode(state: PersistedZoneState) -> dict[str, Any]:
    """Encode the zone snapshot into the v1 store payload."""
    return state.to_dict()


@dataclass(frozen=True, slots=True)
class UserStateSection:
    """Cheap user-intent keys, restored FIRST and each defensively.

    ``has_actuated`` (ActuatorRuntime) is decoded here on the same robust
    pre-model path.  ``climate_mode`` is the one no-fallback key: a non-``str``
    payload value decodes to ``None`` = "leave the ``__init__``/config value
    in place" (never a reset).
    """

    enabled: bool = True
    preset: OverrideMode = OverrideMode.NONE
    window_bypass: bool = False
    climate_mode: str | None = None  # None: keep the __init__/config value
    has_actuated: bool = False


@dataclass(frozen=True, slots=True)
class OverrideLifecycleSection:
    """The shared setpoint/mode hold lifecycle (ADR-0059).

    ``hold_active`` is the derived gate ``override is not None or
    mode_override is not None``; ``override_reason`` / ``override_set_wall`` /
    ``override_expires_at`` only decode while it holds.
    ``override_requested`` is stricter: gated on ``override is not None``
    (setpoint hold ONLY — a pure mode-hold does not restore it).
    ``override_policy`` is decoded for observability but CONFIG-OWNED
    (:data:`CONFIG_OWNED_KEYS`): the caller must never apply it.
    """

    override: float | None = None
    mode_override: str | None = None
    hold_active: bool = False
    override_reason: str | None = None
    override_set_wall: float | None = None
    override_requested: float | None = None
    override_expires_at: float | None = None
    override_expiry_is_switchpoint: bool = False
    boost_expires_at: float | None = None
    boost_prev_preset: OverrideMode | None = None
    override_stats: list[dict[str, Any]] = field(default_factory=list)
    override_policy: str | None = None  # stored copy; NEVER apply (F13)


@dataclass(frozen=True, slots=True)
class AdoptionBaselinesSection:
    """Adoption baselines (ADR-0059 §9) — deliberately NOT hold-gated.

    The baseline describes the actuator, not the hold.  The monotonic echo
    stamps are not part of the schema; re-stamping the echo windows as
    expired (only where a baseline exists) is a domain-restore hook in the
    coordinator, not codec.
    """

    last_written_sp: float | None = None
    prev_device_sp: float | None = None
    last_commanded_hvac: str | None = None
    prev_device_mode: str | None = None


@dataclass(frozen=True, slots=True)
class LearningSection:
    """The learned models (heavy ``from_dict`` parsing, prefix-parsed).

    ``None`` means "not decoded" — either the key was absent/non-dict (keep
    the fresh default) or the sequential model parse stopped at an earlier key
    (see
    ``DecodedPersistence.model_error``).  ``ekf`` is special: on the v1 path
    the key is guaranteed by the gate and parsed WITHOUT an ``isinstance``
    guard — ``ThermalEKF.from_dict`` recovers garbage VALUES itself (fresh
    model, no error); only structurally throwing payloads (e.g. a list)
    stop the parse.
    """

    ekf: ThermalEKF | None = None
    trm_tracker: RunningMeanTracker | None = None
    seasonless: SeasonlessRate | None = None
    window_auto: WindowAutoState | None = None
    multi_lifecycle: DeviceLifecycle | None = None
    ref_offset: OffsetEstimate | None = None
    tau_settle: TauSettle | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticsSection:
    """Diagnostic accumulators + the dry-active latch (restore tail).

    ``dry_active`` sits here (not in the user section) because restore handles
    it as the LAST key, after the learned models — its strict
    ``isinstance(..., bool)`` check maps to ``None`` = "leave the ``__init__``
    value in place".  The fields are parsed INTERLEAVED with the learning
    section, at their restore positions (``outcome_stats``/
    ``regulation_quality`` between ``multi_lifecycle`` and ``ref_offset``;
    ``hdh_savings``/``dry_active`` at the very end), so a mid-tail throw
    retains the same prefix as a fully sequential parse.
    """

    outcome_stats: OutcomeStats | None = None
    regq: RegulationQuality | None = None
    hdh: HdhSavings | None = None
    dry_active: bool | None = None


@dataclass(frozen=True, slots=True)
class DecodedPersistence:
    """Sectionwise decode result; ``kind`` tells the caller what to apply.

    ``kind == "v1"``: apply the sections (user intent first).
    ``kind == "legacy_bare_ekf"``: the store predates the v1 format (any
    non-``None`` payload without an ``"ekf"`` key) — NO section is decoded,
    even if user-intent keys happen to be present;
    parse via ``migrations.migrate_v0_bare_ekf``.
    ``kind == "empty"``: no persisted state (``None`` store) — fresh defaults.
    """

    kind: PayloadKind
    user_state: UserStateSection = field(default_factory=UserStateSection)
    override_lifecycle: OverrideLifecycleSection = field(
        default_factory=OverrideLifecycleSection
    )
    adoption_baselines: AdoptionBaselinesSection = field(
        default_factory=AdoptionBaselinesSection
    )
    learning: LearningSection = field(default_factory=LearningSection)
    diagnostics: DiagnosticsSection = field(default_factory=DiagnosticsSection)
    # The ORIGINAL exception that stopped the sequential model parse (None =
    # clean parse).  The caller re-raises it into its broad restore boundary,
    # which owns the single ``_LOGGER.exception`` recovery record.
    model_error: Exception | None = None


def _decode_user_state(data: dict[Any, Any]) -> UserStateSection:
    try:
        preset = OverrideMode(data.get("preset", "none"))
    except ValueError:
        preset = OverrideMode.NONE
    cm = data.get("climate_mode")
    return UserStateSection(
        enabled=bool(data.get("enabled", True)),
        preset=preset,
        window_bypass=bool(data.get("window_bypass", False)),
        climate_mode=cm if isinstance(cm, str) else None,
        has_actuated=bool(data.get("has_actuated", False)),
    )


def _decode_override_lifecycle(data: dict[Any, Any]) -> OverrideLifecycleSection:
    ov = data.get("override")
    override = float(ov) if isinstance(ov, (int, float)) else None
    mov = data.get("mode_override")
    mode_override = mov if isinstance(mov, str) else None
    # The shared hold lifecycle is active if EITHER a setpoint or a mode
    # hold was persisted (an ``off`` hold carries no setpoint).
    hold_active = override is not None or mode_override is not None
    orr = data.get("override_reason")
    osw = data.get("override_set_wall")
    orq = data.get("override_requested")
    oea = data.get("override_expires_at")
    try:
        bpp = data.get("boost_prev_preset")
        boost_prev_preset = OverrideMode(bpp) if isinstance(bpp, str) else None
    except ValueError:
        boost_prev_preset = None
    bea = data.get("boost_expires_at")
    ostats = data.get("override_stats")
    opol = data.get("override_policy")
    return OverrideLifecycleSection(
        override=override,
        mode_override=mode_override,
        hold_active=hold_active,
        override_reason=(orr if hold_active and isinstance(orr, str) else None),
        override_set_wall=(
            float(osw) if hold_active and isinstance(osw, (int, float)) else None
        ),
        # NOT ``hold_active``: a pure mode-hold does not restore the pre-clamp
        # setpoint ask (the gate is ``override is not None``).
        override_requested=(
            float(orq)
            if override is not None and isinstance(orq, (int, float))
            else None
        ),
        override_expires_at=(
            float(oea) if hold_active and isinstance(oea, (int, float)) else None
        ),
        override_expiry_is_switchpoint=bool(
            data.get("override_expiry_is_switchpoint", False)
        ),
        boost_expires_at=(float(bea) if isinstance(bea, (int, float)) else None),
        boost_prev_preset=boost_prev_preset,
        override_stats=(
            [r for r in ostats if isinstance(r, dict)][-50:]
            if isinstance(ostats, list)
            else []
        ),
        override_policy=opol if isinstance(opol, str) else None,
    )


def _decode_adoption_baselines(data: dict[Any, Any]) -> AdoptionBaselinesSection:
    lws = data.get("last_written_sp")
    pds = data.get("prev_device_sp")
    lch = data.get("last_commanded_hvac")
    pdm = data.get("prev_device_mode")
    return AdoptionBaselinesSection(
        last_written_sp=(float(lws) if isinstance(lws, (int, float)) else None),
        prev_device_sp=(float(pds) if isinstance(pds, (int, float)) else None),
        last_commanded_hvac=lch if isinstance(lch, str) else None,
        prev_device_mode=pdm if isinstance(pdm, str) else None,
    )


def _decode_models(
    data: dict[Any, Any], *, now_wall: float
) -> tuple[LearningSection, DiagnosticsSection, Exception | None]:
    """Sequential prefix parse of the model tail, in a fixed order.

    Each model is committed as soon as it parses; the FIRST structural throw
    stops the parse — everything before the throwing key stays decoded,
    everything after it stays ``None`` — and the original exception is
    returned for the caller's broad boundary ("corrupt -> fresh" + the
    recovery log).
    """
    learn: dict[str, Any] = {}
    diag: dict[str, Any] = {}
    try:
        # Direct subscript, no isinstance guard — the key is guaranteed by the
        # v1 gate and ``from_dict`` self-recovers garbage values; a list-shaped
        # payload raises out of the parse.
        learn["ekf"] = ThermalEKF.from_dict(data["ekf"])
        trm = data.get("trm")
        if isinstance(trm, dict):
            learn["trm_tracker"] = RunningMeanTracker.from_dict(trm)
        sls = data.get("seasonless")
        if isinstance(sls, dict):
            learn["seasonless"] = SeasonlessRate.from_dict(sls)
        wa = data.get("window_auto")
        if isinstance(wa, dict):
            learn["window_auto"] = WindowAutoState.from_dict(wa)
        ml = data.get("multi_lifecycle")
        if isinstance(ml, dict):
            # ADR-0046: the wall-clock clamp anchor is injected explicitly
            # (the coordinator passes ``dt_util.utcnow().timestamp()``).
            learn["multi_lifecycle"] = _lifecycle.from_dict(ml, now=now_wall)
        ost = data.get("outcome_stats")
        if isinstance(ost, dict):
            diag["outcome_stats"] = OutcomeStats.from_dict(ost)
        rq = data.get("regulation_quality")
        if isinstance(rq, dict):
            diag["regq"] = RegulationQuality.from_dict(rq)
        ro = data.get("ref_offset")
        if isinstance(ro, dict):
            learn["ref_offset"] = OffsetEstimate.from_dict(ro)
        ts = data.get("tau_settle")
        if isinstance(ts, dict):
            learn["tau_settle"] = TauSettle.from_dict(ts)
        hdh = data.get("hdh_savings")
        if isinstance(hdh, dict):
            diag["hdh"] = HdhSavings.from_dict(hdh)
        da = data.get("dry_active")
        if isinstance(da, bool):
            # strict bool check — anything else leaves the latch alone.
            diag["dry_active"] = da
    except Exception as err:  # first structural throw stops the parse
        return LearningSection(**learn), DiagnosticsSection(**diag), err
    return LearningSection(**learn), DiagnosticsSection(**diag), None


def decode(raw: object, *, now_wall: float) -> DecodedPersistence:
    """Decode a raw store payload: robust cheap sections + prefix model tail.

    ``raw`` is whatever ``store.load()`` returned (JSON-typed values); store
    I/O errors are the caller's concern (``ConfigEntryNotReady`` — a transient
    load failure must never be mistaken for "no saved state").
    ``now_wall`` is the wall-clock anchor for the ``multi_lifecycle``
    future-timestamp clamp (ADR-0046 §8).  A structural throw in the model
    tail stops the sequential parse and is surfaced as ``model_error`` (see
    the module docstring) — it can never cost the cheap sections.
    """
    if raw is None:
        return DecodedPersistence(kind="empty")
    if not (isinstance(raw, dict) and "ekf" in raw):
        # The pinned legacy gate: also a *dict* without the ``ekf`` key — its
        # user-intent keys are deliberately NOT decoded.
        return DecodedPersistence(kind="legacy_bare_ekf")
    learning, diagnostics, model_error = _decode_models(raw, now_wall=now_wall)
    return DecodedPersistence(
        kind="v1",
        user_state=_decode_user_state(raw),
        override_lifecycle=_decode_override_lifecycle(raw),
        adoption_baselines=_decode_adoption_baselines(raw),
        learning=learning,
        diagnostics=diagnostics,
        model_error=model_error,
    )
