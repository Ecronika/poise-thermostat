"""Phase-3 contract tests for the persistence codec (pure, py310).

Pins ``persistence/codec.py`` + ``persistence/migrations.py`` against the
frozen phase-0 behaviour of ``PoiseCoordinator._save_payload`` and the
restore path in ``async_bootstrap`` (docs/Konzepte/2026-07-18_Refactoring-
Plan_coordinator.md, phase 3 / findings 8+10):

* encode == today's payload: exact key set (31 keys, snapshot pinned), the
  per-key transforms and reference semantics (``override_stats``).
* the ``"ekf" in data`` restore gate: a dict store WITHOUT the key decodes
  NOTHING (marker ``legacy_bare_ekf``), even when user-intent keys are
  present (bound phase-0 finding 2).
* per-key coercions, the ``_hold_active`` gates and the stricter
  ``override_requested`` gate (setpoint hold only).
* ``override_policy``: stored, decoded for observability, marked
  config-owned — never restore-effective (F13).
* partial recovery: garbage EKF *values* self-recover without an error;
  a structurally throwing payload stops the sequential model parse at
  exactly the throwing key (prefix kept, tail undecoded, the original
  exception surfaced as ``model_error`` for the caller's broad boundary —
  behaviour-equivalent to the old monolithic restore, finding 10) and can
  never cost the user-intent sections.
* the v0 bare-EKF migration ("corrupt -> fresh" stays with the caller).
* consistency invariant: the encode key set covers the ``PERSISTED_FIELDS``
  constants of ``runtime/state.py`` (with the three documented storage-key
  renames) plus the ``override_policy`` special case.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from custom_components.poise.control.hdh_savings import HdhSavings
from custom_components.poise.control.outcome_scoring import OutcomeStats
from custom_components.poise.control.override import OverrideMode
from custom_components.poise.control.reference_offset import OffsetEstimate
from custom_components.poise.control.regulation_quality import RegulationQuality
from custom_components.poise.control.window_auto import WindowAutoState
from custom_components.poise.estimation.running_mean import RunningMeanTracker
from custom_components.poise.estimation.seasonless_rate import SeasonlessRate
from custom_components.poise.estimation.tau_settle import TauSettle
from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.multi import lifecycle as _lifecycle
from custom_components.poise.multi.lifecycle import DeviceLifecycle
from custom_components.poise.persistence import codec
from custom_components.poise.persistence.migrations import migrate_v0_bare_ekf
from custom_components.poise.runtime.state import (
    ActuatorRuntime,
    CompressorRuntime,
    DiagnosticsRuntime,
    ExternalOverrideRuntime,
    HumidityRuntime,
    LearningRuntime,
    PipelineLatches,
    PresenceRuntime,
    SafetyRuntime,
    UserControlState,
    WindowRuntime,
)

# Deterministic wall-clock anchor for the multi_lifecycle clamp (ADR-0046 §8);
# all lifecycle stamps below lie in its past, so nothing clamps or prunes.
NOW_WALL = 1_768_000_000.0

# The exact ``_save_payload`` key snapshot (coordinator.py, phase-2 baseline
# L1513-1567). A change here is a storage-schema decision, not a detail.
EXPECTED_PAYLOAD_KEYS = (
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

ALL_STATE_CLASSES: tuple[type[Any], ...] = (
    UserControlState,
    ExternalOverrideRuntime,
    ActuatorRuntime,
    LearningRuntime,
    WindowRuntime,
    PresenceRuntime,
    HumidityRuntime,
    CompressorRuntime,
    SafetyRuntime,
    DiagnosticsRuntime,
    PipelineLatches,
)

# The user-intent keys as a prior run would persist them (mirrors the
# integration seed in tests/integration/test_phase0_partial_recovery.py).
USER_KEYS: dict[str, Any] = {
    "enabled": False,
    "preset": "eco",
    "override": 21.5,
    "mode_override": "heat",
    "override_reason": "device_adopt_setpoint",
    "last_written_sp": 20.0,
    "prev_device_sp": 20.5,
    "last_commanded_hvac": "heat",
    "prev_device_mode": "heat",
}


def _ekf(n_updates: int = 0) -> ThermalEKF:
    ekf = ThermalEKF()
    ekf.n_updates = n_updates
    return ekf


def _rich_state() -> codec.PersistedZoneState:
    """A fully populated snapshot: every optional field non-default."""
    ekf = ThermalEKF()
    ekf.n_updates = 7
    ekf.n_idle = 2
    ekf.n_heating = 3
    return codec.PersistedZoneState(
        ekf=ekf,
        trm_tracker=RunningMeanTracker.from_dict(
            {
                "alpha": 0.8,
                "t_rm": 8.5,
                "day": "2026-07-18",
                "day_sum": 42.0,
                "day_count": 4,
                "recent_days": [8.0, 9.0],
            }
        ),
        seasonless=SeasonlessRate.from_dict(
            {"temp_sigma": 3.0, "half_life_days": 20.0, "obs": [[5.0, 0.4, 738000.0]]}
        ),
        window_auto=WindowAutoState.from_dict(
            {"ema_slope": -0.5, "n_points": 9, "open": True, "minutes_open": 12.5}
        ),
        multi_lifecycle=DeviceLifecycle(
            is_on=True,
            last_on_wall=NOW_WALL - 600.0,
            last_off_wall=NOW_WALL - 4000.0,
            last_mode="cool",
            mode_changed_wall=NOW_WALL - 600.0,
            starts_window=(NOW_WALL - 900.0, NOW_WALL - 600.0),
            expected_echo={"hvac_mode": "cool"},
        ),
        ref_offset=OffsetEstimate.from_dict(
            {"offset": 0.7, "deviation": 0.1, "minutes": 90.0}
        ),
        tau_settle=TauSettle.from_dict({"mean": 35.0, "var": 4.0, "minutes": 60.0}),
        outcome_stats=OutcomeStats.from_dict(
            {"ts_sum": 12.0, "ts_n": 3, "obs_sum": 6.0, "obs_n": 2, "last_score": 0.75}
        ),
        regq=RegulationQuality.from_dict(
            {
                "deviation_k": 0.3,
                "in_band": 0.9,
                "cycles_per_hour": 1.5,
                "minutes": 240.0,
                "last_mode": "heat",
            }
        ),
        hdh=HdhSavings.from_dict(
            {"saved_min": 120.0, "eligible_min": 480.0, "month": "2026-07"}
        ),
        dry_active=True,
        enabled=False,
        preset=OverrideMode.ECO,
        climate_mode="heat_only",
        window_bypass=True,
        has_actuated=True,
        override=21.5,
        mode_override="heat",
        override_set_wall=NOW_WALL - 1800.0,
        override_requested=22.0,
        override_policy="switchpoint",
        override_expires_at=NOW_WALL + 3600.0,
        override_expiry_is_switchpoint=True,
        boost_expires_at=NOW_WALL + 900.0,
        boost_prev_preset=OverrideMode.COMFORT,
        override_stats=[{"reason": "user_setpoint", "minutes": 45.0}],
        override_reason="device_adopt_setpoint",
        last_written_sp=20.0,
        prev_device_sp=20.5,
        last_commanded_hvac="heat",
        prev_device_mode="heat",
    )


def _v1(**extra: Any) -> dict[str, Any]:
    """A minimal valid v1 payload (the gate only requires the ``ekf`` key)."""
    return {"ekf": ThermalEKF().to_dict(), **extra}


# ---------------------------------------------------------------- encode ----


def test_encode_key_snapshot_exact() -> None:
    """The encode key set AND order are pinned to today's ``_save_payload``."""
    payload = codec.encode(_rich_state())
    assert list(payload) == list(EXPECTED_PAYLOAD_KEYS)
    assert list(codec.PAYLOAD_KEYS) == list(EXPECTED_PAYLOAD_KEYS)
    assert len(set(EXPECTED_PAYLOAD_KEYS)) == 31


def test_encode_values_match_save_payload_transforms() -> None:
    """Per-key transforms are exactly today's: nested ``to_dict()`` for the
    models, ``.value`` for the enums, raw pass-through (by reference for
    ``override_stats``) for the scalars."""
    state = _rich_state()
    payload = codec.encode(state)
    assert payload["ekf"] == state.ekf.to_dict()
    assert payload["trm"] == state.trm_tracker.to_dict()
    assert payload["seasonless"] == state.seasonless.to_dict()
    assert payload["window_auto"] == state.window_auto.to_dict()
    assert payload["multi_lifecycle"] == _lifecycle.to_dict(state.multi_lifecycle)
    assert payload["outcome_stats"] == state.outcome_stats.to_dict()
    assert payload["regulation_quality"] == state.regq.to_dict()
    assert state.ref_offset is not None and state.tau_settle is not None
    assert payload["ref_offset"] == state.ref_offset.to_dict()
    assert payload["tau_settle"] == state.tau_settle.to_dict()
    assert payload["hdh_savings"] == state.hdh.to_dict()
    assert payload["dry_active"] is True
    assert payload["window_bypass"] is True
    assert payload["preset"] == "eco"  # OverrideMode -> .value
    assert payload["enabled"] is False
    assert payload["override"] == 21.5
    assert payload["mode_override"] == "heat"
    assert payload["override_set_wall"] == NOW_WALL - 1800.0
    assert payload["override_requested"] == 22.0
    assert payload["override_policy"] == "switchpoint"
    assert payload["override_expires_at"] == NOW_WALL + 3600.0
    assert payload["override_expiry_is_switchpoint"] is True
    assert payload["boost_expires_at"] == NOW_WALL + 900.0
    assert payload["boost_prev_preset"] == "comfort"  # enum-or-None
    assert payload["override_stats"] is state.override_stats  # by reference
    assert payload["override_reason"] == "device_adopt_setpoint"
    assert payload["last_written_sp"] == 20.0
    assert payload["prev_device_sp"] == 20.5
    assert payload["last_commanded_hvac"] == "heat"
    assert payload["prev_device_mode"] == "heat"
    assert payload["climate_mode"] == "heat_only"
    assert payload["has_actuated"] is True


def test_encode_optional_models_serialise_as_none() -> None:
    """``ref_offset``/``tau_settle`` (optional models) and
    ``boost_prev_preset`` (enum-or-None) encode as ``None`` when unset."""
    state = replace(
        _rich_state(), ref_offset=None, tau_settle=None, boost_prev_preset=None
    )
    payload = codec.encode(state)
    assert payload["ref_offset"] is None
    assert payload["tau_settle"] is None
    assert payload["boost_prev_preset"] is None


def test_encode_key_set_covers_persisted_fields_invariant() -> None:
    """Consistency invariant: encode keys == the union of the
    ``PERSISTED_FIELDS`` constants (3 documented storage-key renames) plus
    the config-owned ``override_policy`` — nothing more, nothing less."""
    union: set[str] = set()
    for cls in ALL_STATE_CLASSES:
        fields: frozenset[str] = cls.PERSISTED_FIELDS
        assert not (union & fields)  # no field is owned by two groups
        union |= fields
    mapped = {codec.STORAGE_KEY_RENAMES.get(f, f) for f in union}
    assert "override_policy" not in mapped  # no state-group home (config-owned)
    assert mapped | {"override_policy"} == set(codec.PAYLOAD_KEYS)
    # The three renames are real state fields on their owning groups.
    assert "trm_tracker" in LearningRuntime.PERSISTED_FIELDS
    assert {"regq", "hdh"} <= DiagnosticsRuntime.PERSISTED_FIELDS
    assert set(codec.STORAGE_KEY_RENAMES) == {"trm_tracker", "regq", "hdh"}


# ------------------------------------------------------------- roundtrip ----


def test_roundtrip_decode_encode_semantic_identity() -> None:
    """decode(encode(x)) restores every section semantically identical."""
    state = _rich_state()
    decoded = codec.decode(codec.encode(state), now_wall=NOW_WALL)
    assert decoded.kind == "v1"
    assert decoded.model_error is None

    user = decoded.user_state
    assert user.enabled is False
    assert user.preset is OverrideMode.ECO
    assert user.window_bypass is True
    assert user.climate_mode == "heat_only"
    assert user.has_actuated is True

    ovr = decoded.override_lifecycle
    assert ovr.override == 21.5
    assert ovr.mode_override == "heat"
    assert ovr.hold_active is True
    assert ovr.override_reason == "device_adopt_setpoint"
    assert ovr.override_set_wall == NOW_WALL - 1800.0
    assert ovr.override_requested == 22.0
    assert ovr.override_expires_at == NOW_WALL + 3600.0
    assert ovr.override_expiry_is_switchpoint is True
    assert ovr.boost_expires_at == NOW_WALL + 900.0
    assert ovr.boost_prev_preset is OverrideMode.COMFORT
    assert ovr.override_stats == [{"reason": "user_setpoint", "minutes": 45.0}]
    assert ovr.override_policy == "switchpoint"  # decoded, config-owned

    base = decoded.adoption_baselines
    assert base.last_written_sp == 20.0
    assert base.prev_device_sp == 20.5
    assert base.last_commanded_hvac == "heat"
    assert base.prev_device_mode == "heat"

    learn = decoded.learning
    assert learn.ekf is not None and learn.ekf.to_dict() == state.ekf.to_dict()
    assert learn.trm_tracker is not None
    assert learn.trm_tracker.to_dict() == state.trm_tracker.to_dict()
    assert learn.seasonless is not None
    assert learn.seasonless.to_dict() == state.seasonless.to_dict()
    assert learn.window_auto is not None
    assert learn.window_auto.to_dict() == state.window_auto.to_dict()
    # Frozen dataclass equality; no stamp lies in the future of NOW_WALL and
    # both starts are within the 1 h window, so nothing clamps or prunes.
    assert learn.multi_lifecycle == state.multi_lifecycle
    assert state.ref_offset is not None and state.tau_settle is not None
    assert learn.ref_offset is not None
    assert learn.ref_offset.to_dict() == state.ref_offset.to_dict()
    assert learn.tau_settle is not None
    assert learn.tau_settle.to_dict() == state.tau_settle.to_dict()

    diag = decoded.diagnostics
    assert diag.outcome_stats is not None
    assert diag.outcome_stats.to_dict() == state.outcome_stats.to_dict()
    assert diag.regq is not None and diag.regq.to_dict() == state.regq.to_dict()
    assert diag.hdh is not None and diag.hdh.to_dict() == state.hdh.to_dict()
    assert diag.dry_active is True


def test_minimal_v1_payload_decodes_to_defaults() -> None:
    """``{"ekf": ...}`` alone passes the gate; every other key falls back to
    its documented default (enabled=True, preset NONE, stats [], models
    untouched=None, sentinels None)."""
    decoded = codec.decode(_v1(), now_wall=NOW_WALL)
    assert decoded.kind == "v1"
    assert decoded.model_error is None
    assert decoded.user_state == codec.UserStateSection()
    assert decoded.user_state.climate_mode is None  # no None-reset, keep init
    ovr = decoded.override_lifecycle
    assert ovr == codec.OverrideLifecycleSection()
    assert ovr.hold_active is False and ovr.override_stats == []
    assert decoded.adoption_baselines == codec.AdoptionBaselinesSection()
    learn = decoded.learning
    assert isinstance(learn.ekf, ThermalEKF) and learn.ekf.n_updates == 0
    assert learn.trm_tracker is None
    assert learn.seasonless is None
    assert learn.window_auto is None
    assert learn.multi_lifecycle is None
    assert learn.ref_offset is None
    assert learn.tau_settle is None
    assert decoded.diagnostics == codec.DiagnosticsSection()


# ------------------------------------------------------------ hold gates ----


def test_inactive_hold_drops_lifecycle_keys() -> None:
    """No setpoint AND no mode hold -> reason/set_wall/requested/expires are
    all gated to None even when present in the payload."""
    decoded = codec.decode(
        _v1(
            override=None,
            mode_override=None,
            override_reason="stale",
            override_set_wall=NOW_WALL - 10.0,
            override_requested=21.0,
            override_expires_at=NOW_WALL + 10.0,
        ),
        now_wall=NOW_WALL,
    )
    ovr = decoded.override_lifecycle
    assert ovr.hold_active is False
    assert ovr.override_reason is None
    assert ovr.override_set_wall is None
    assert ovr.override_requested is None
    assert ovr.override_expires_at is None


def test_mode_only_hold_restores_lifecycle_but_not_requested() -> None:
    """A pure mode-hold (K2) activates the shared lifecycle, but
    ``override_requested`` stays None: its gate is ``override is not None``
    (setpoint hold ONLY), not ``hold_active``."""
    decoded = codec.decode(
        _v1(
            override=None,
            mode_override="off",
            override_reason="user_mode",
            override_set_wall=NOW_WALL - 100.0,
            override_requested=23.0,  # present, but must NOT decode
            override_expires_at=NOW_WALL + 100.0,
        ),
        now_wall=NOW_WALL,
    )
    ovr = decoded.override_lifecycle
    assert ovr.hold_active is True
    assert ovr.mode_override == "off"
    assert ovr.override_reason == "user_mode"
    assert ovr.override_set_wall == NOW_WALL - 100.0
    assert ovr.override_expires_at == NOW_WALL + 100.0
    assert ovr.override_requested is None  # the stricter setpoint-only gate


def test_setpoint_hold_restores_requested_and_numeric_coercion() -> None:
    """A setpoint hold restores ``override_requested``; the numeric coercion
    is exactly today's ``isinstance(x, (int, float))`` -> ``float`` (which
    deliberately admits bools: ``True -> 1.0``)."""
    decoded = codec.decode(_v1(override=21, override_requested=22), now_wall=NOW_WALL)
    ovr = decoded.override_lifecycle
    assert ovr.override == 21.0 and isinstance(ovr.override, float)
    assert ovr.override_requested == 22.0
    # today's isinstance(int) quirk: a bool coerces instead of dropping
    quirk = codec.decode(_v1(override=True), now_wall=NOW_WALL)
    assert quirk.override_lifecycle.override == 1.0
    assert quirk.override_lifecycle.hold_active is True


def test_garbage_scalars_fall_back_per_key() -> None:
    """Each scalar key is defensive on its own: enum garbage -> default,
    non-numeric stamps -> None, non-str strings -> None."""
    decoded = codec.decode(
        _v1(
            preset="fancy",  # ValueError -> NONE
            boost_prev_preset="fancy",  # ValueError -> None
            boost_expires_at="soon",  # non-numeric -> None
            mode_override=7,  # non-str -> None
            override="21.5",  # str is NOT coerced (isinstance gate)
            override_policy=5,  # non-str -> None
            climate_mode=3,  # non-str -> sentinel None
            dry_active=1,  # R9 strict bool -> sentinel None
        ),
        now_wall=NOW_WALL,
    )
    assert decoded.user_state.preset is OverrideMode.NONE
    assert decoded.user_state.climate_mode is None
    ovr = decoded.override_lifecycle
    assert ovr.boost_prev_preset is None
    assert ovr.boost_expires_at is None
    assert ovr.mode_override is None
    assert ovr.override is None
    assert ovr.hold_active is False
    assert ovr.override_policy is None
    assert decoded.diagnostics.dry_active is None
    # An int preset raises ValueError inside OverrideMode(...) too.
    assert (
        codec.decode(_v1(preset=5), now_wall=NOW_WALL).user_state.preset
        is OverrideMode.NONE
    )
    # A non-str boost_prev_preset skips the enum call (no raise).
    assert (
        codec.decode(
            _v1(boost_prev_preset=7), now_wall=NOW_WALL
        ).override_lifecycle.boost_prev_preset
        is None
    )


def test_override_stats_element_filter_and_tail_cap() -> None:
    """``override_stats``: non-list -> [], list -> dict-elements only,
    capped to the LAST 50 (exactly today's expression)."""
    rows: list[Any] = [{"i": i} for i in range(60)]
    rows.insert(0, "not-a-dict")
    rows.insert(30, None)
    decoded = codec.decode(_v1(override_stats=rows), now_wall=NOW_WALL)
    stats = decoded.override_lifecycle.override_stats
    assert len(stats) == 50
    assert stats[0] == {"i": 10} and stats[-1] == {"i": 59}
    assert (
        codec.decode(
            _v1(override_stats="nope"), now_wall=NOW_WALL
        ).override_lifecycle.override_stats
        == []
    )


# ------------------------------------------------- gate / legacy / empty ----


def test_store_without_ekf_key_is_legacy_marker() -> None:
    """The pinned restore gate: a dict store WITHOUT an ``ekf`` key decodes
    NOTHING — not even present user-intent keys (phase-0 finding 2, mirrored
    by ``test_store_without_ekf_key_is_legacy_branch``)."""
    decoded = codec.decode(dict(USER_KEYS), now_wall=NOW_WALL)
    assert decoded == codec.DecodedPersistence(kind="legacy_bare_ekf")
    assert decoded.user_state.enabled is True  # default, NOT the seeded False
    assert decoded.override_lifecycle.override is None
    assert decoded.adoption_baselines.last_written_sp is None


def test_non_dict_store_is_legacy_marker() -> None:
    """Any non-``None`` non-dict store is the legacy branch (today's
    ``elif data is not None``)."""
    decoded = codec.decode(["bare", "ekf"], now_wall=NOW_WALL)
    assert decoded == codec.DecodedPersistence(kind="legacy_bare_ekf")


def test_none_store_is_empty() -> None:
    """``store.load() -> None`` skips both branches: fresh defaults, and
    NEVER a ``ConfigEntryNotReady`` concern (that is store I/O, AR-20)."""
    assert codec.decode(None, now_wall=NOW_WALL) == codec.DecodedPersistence(
        kind="empty"
    )


# ------------------------------------------------------- partial recovery ----


def test_garbage_ekf_values_self_recover_without_error() -> None:
    """Fall 1 (phase-0): garbage EKF *values* are recovered by
    ``ThermalEKF.from_dict`` itself — fresh model, NO parse stop."""
    decoded = codec.decode(
        {"ekf": {"x": "garbage"}, **USER_KEYS, "dry_active": True},
        now_wall=NOW_WALL,
    )
    assert decoded.kind == "v1"
    assert decoded.model_error is None
    assert isinstance(decoded.learning.ekf, ThermalEKF)
    assert decoded.learning.ekf.n_updates == 0  # fresh
    assert decoded.user_state.enabled is False
    assert decoded.override_lifecycle.override == 21.5
    assert decoded.adoption_baselines.prev_device_sp == 20.5
    assert decoded.diagnostics.dry_active is True


def test_throwing_ekf_structure_loses_whole_tail_keeps_user_sections() -> None:
    """Fall 2 (phase-0): ``ekf`` as a list throws structurally (no ``.get``)
    at the FIRST model key — the prefix parse stops immediately, so ALL
    models AND the diagnostics tail stay undecoded (exactly the old
    sequential restore, which never reached them); the user-intent, override
    and baseline sections are untouched, and ``model_error`` carries the
    original exception for the caller's broad boundary."""
    decoded = codec.decode(
        {
            "ekf": ["not", "a", "dict"],
            **USER_KEYS,
            "dry_active": True,
            "hdh_savings": {"saved_min": 5.0, "eligible_min": 10.0, "month": "2026-07"},
        },
        now_wall=NOW_WALL,
    )
    assert decoded.kind == "v1"
    assert isinstance(decoded.model_error, AttributeError)  # a list has no .get
    assert decoded.learning == codec.LearningSection()  # nothing parsed
    assert decoded.diagnostics == codec.DiagnosticsSection()  # tail lost too
    assert decoded.diagnostics.dry_active is None
    assert decoded.diagnostics.hdh is None
    assert decoded.user_state.enabled is False
    assert decoded.user_state.preset is OverrideMode.ECO
    ovr = decoded.override_lifecycle
    assert ovr.override == 21.5 and ovr.mode_override == "heat"
    assert ovr.override_reason == "device_adopt_setpoint"
    base = decoded.adoption_baselines
    assert base.last_written_sp == 20.0 and base.prev_device_mode == "heat"


def test_throwing_trm_keeps_parsed_ekf_prefix() -> None:
    """Finding-10 prefix semantics: a structurally corrupt SECOND model
    (``trm`` with a non-numeric value -> ``float`` ValueError) stops the
    parse AFTER ``ekf`` — the already-parsed EKF is KEPT (the old restore
    had assigned it before the throw), while everything after ``trm`` stays
    undecoded, including the diagnostics tail."""
    decoded = codec.decode(
        _v1(
            trm={"alpha": "not-a-number"},
            seasonless={"temp_sigma": 3.0, "half_life_days": 20.0, "obs": []},
            dry_active=True,
            outcome_stats={"ts_sum": 1.0, "ts_n": 1, "obs_sum": 1.0, "obs_n": 1},
        ),
        now_wall=NOW_WALL,
    )
    assert decoded.kind == "v1"
    assert isinstance(decoded.model_error, ValueError)
    assert isinstance(decoded.learning.ekf, ThermalEKF)  # prefix kept
    assert decoded.learning.trm_tracker is None  # the throwing key
    assert decoded.learning.seasonless is None  # after the throw: lost
    assert decoded.diagnostics == codec.DiagnosticsSection()  # tail lost


def test_throwing_outcome_stats_loses_everything_after_it() -> None:
    """Cross-order pin (old restore order, forward direction):
    ``outcome_stats`` sits BETWEEN ``multi_lifecycle`` and ``ref_offset``.
    A throw there keeps ekf/trm (parsed before) and loses
    regulation_quality, ref_offset, tau_settle, hdh_savings and dry_active
    (all after) — retention follows the ORDER, not a learning/diagnostics
    grouping."""
    decoded = codec.decode(
        _v1(
            trm=RunningMeanTracker().to_dict(),
            outcome_stats={"ts_sum": "not-a-number"},
            ref_offset={"offset": 0.7, "deviation": 0.1, "minutes": 90.0},
            tau_settle={"mean": 35.0, "var": 4.0, "minutes": 60.0},
            dry_active=True,
        ),
        now_wall=NOW_WALL,
    )
    assert decoded.kind == "v1"
    assert isinstance(decoded.model_error, ValueError)
    assert isinstance(decoded.learning.ekf, ThermalEKF)  # before: kept
    assert decoded.learning.trm_tracker is not None  # before: kept
    assert decoded.diagnostics.outcome_stats is None  # the throwing key
    assert decoded.diagnostics.regq is None  # after: lost
    assert decoded.learning.ref_offset is None  # after: lost
    assert decoded.learning.tau_settle is None
    assert decoded.diagnostics.hdh is None
    assert decoded.diagnostics.dry_active is None


def test_throwing_ref_offset_keeps_outcome_stats_before_it() -> None:
    """Cross-order pin (reverse direction): a throw at ``ref_offset`` keeps
    ekf and outcome_stats (both parsed BEFORE it in the old order) and loses
    only tau_settle, hdh_savings and dry_active."""
    decoded = codec.decode(
        _v1(
            outcome_stats={"ts_sum": 1.0, "ts_n": 1, "obs_sum": 1.0, "obs_n": 1},
            ref_offset={"offset": "not-a-number"},
            tau_settle={"mean": 35.0, "var": 4.0, "minutes": 60.0},
            hdh_savings={"saved_min": 5.0, "eligible_min": 10.0, "month": "2026-07"},
            dry_active=True,
        ),
        now_wall=NOW_WALL,
    )
    assert decoded.kind == "v1"
    assert isinstance(decoded.model_error, ValueError)
    assert isinstance(decoded.learning.ekf, ThermalEKF)  # before: kept
    assert decoded.diagnostics.outcome_stats is not None  # before: kept
    assert decoded.learning.ref_offset is None  # the throwing key
    assert decoded.learning.tau_settle is None  # after: lost
    assert decoded.diagnostics.hdh is None
    assert decoded.diagnostics.dry_active is None


# ----------------------------------------------- override_policy (F13) ------


def test_override_policy_is_config_owned() -> None:
    """``override_policy`` is stored (payload key) and decoded for
    observability, but marked config-owned: it has no ``PERSISTED_FIELDS``
    home and must never be applied on restore (F13, pinned in integration by
    ``test_override_policy_option_change_survives_restart``)."""
    assert frozenset({"override_policy"}) == codec.CONFIG_OWNED_KEYS
    assert "override_policy" in codec.PAYLOAD_KEYS
    for cls in ALL_STATE_CLASSES:
        assert "override_policy" not in cls.PERSISTED_FIELDS
    decoded = codec.decode(_v1(override_policy="timer"), now_wall=NOW_WALL)
    assert decoded.override_lifecycle.override_policy == "timer"


# ------------------------------------------------------------- migrations ---


def test_migrate_v0_bare_ekf_roundtrip() -> None:
    """A genuine v0 store (bare ``ThermalEKF.to_dict()``) migrates losslessly."""
    ekf = _ekf(n_updates=4)
    migrated = migrate_v0_bare_ekf(ekf.to_dict())
    assert migrated.to_dict() == ekf.to_dict()


def test_migrate_v0_bare_ekf_recovers_garbage_values() -> None:
    """Dict-shaped garbage recovers to a fresh model WITHOUT raising —
    ``from_dict``'s own recovery (also covers a dict without EKF fields,
    i.e. today's fate of a user-keys-only store on the legacy branch)."""
    assert migrate_v0_bare_ekf({}).n_updates == 0
    assert migrate_v0_bare_ekf({"x": "garbage"}).n_updates == 0
    assert migrate_v0_bare_ekf(dict(USER_KEYS)).n_updates == 0


def test_migrate_v0_bare_ekf_structural_corruption_raises() -> None:
    """A structurally throwing payload propagates: "corrupt -> fresh" is the
    CALLER's decision (today: the coordinator's broad restore boundary)."""
    with pytest.raises(AttributeError):
        migrate_v0_bare_ekf(["not", "a", "dict"])
