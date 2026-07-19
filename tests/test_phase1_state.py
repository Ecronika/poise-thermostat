"""Phase-1 contract tests for the grouped runtime state (``runtime/state.py``).

Locks the field/persistence contract of the eleven mutable state groups from
refactoring-plan section 3 (docs/Konzepte/2026-07-18_Refactoring-Plan_
coordinator.md): default construction, ``PERSISTED_FIELDS`` consistency with
the actual dataclass fields, the ``ExternalOverrideRuntime`` split (finding 8)
and mutability.  Pure — no Home Assistant import.
"""

from __future__ import annotations

import dataclasses
from collections import deque
from typing import Any

import pytest

from custom_components.poise.control.dynamics import DeviceDynamics
from custom_components.poise.control.override import OverrideMode
from custom_components.poise.control.window_auto import WindowAutoConfig
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

# The exact persisted-field contract per state group (plan section 3, verified
# against ``_save_payload`` coordinator.py L1665-1719).  A change here is a
# storage-schema decision, not a refactoring detail.
EXPECTED_PERSISTED: dict[type[Any], frozenset[str]] = {
    UserControlState: frozenset(
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
    ),
    ExternalOverrideRuntime: frozenset(
        {
            "last_written_sp",
            "prev_device_sp",
            "last_commanded_hvac",
            "prev_device_mode",
        }
    ),
    ActuatorRuntime: frozenset({"has_actuated"}),
    LearningRuntime: frozenset(
        {"ekf", "trm_tracker", "seasonless", "ref_offset", "tau_settle"}
    ),
    WindowRuntime: frozenset({"window_auto"}),
    PresenceRuntime: frozenset(),
    HumidityRuntime: frozenset({"dry_active"}),
    CompressorRuntime: frozenset({"multi_lifecycle"}),
    SafetyRuntime: frozenset(),
    DiagnosticsRuntime: frozenset({"outcome_stats", "regq", "hdh"}),
    PipelineLatches: frozenset(),
}

ALL_STATE_CLASSES = list(EXPECTED_PERSISTED)

_ids = [cls.__name__ for cls in ALL_STATE_CLASSES]


@pytest.mark.parametrize("cls", ALL_STATE_CLASSES, ids=_ids)
def test_constructs_with_defaults(cls: type[Any]) -> None:
    """Every state group is a zero-arg constructible mutable dataclass."""
    instance = cls()
    assert dataclasses.is_dataclass(instance)
    # Mutable by design (long-lived runtime state), unlike the frozen
    # per-tick contracts.
    assert cls.__dataclass_params__.frozen is False


@pytest.mark.parametrize("cls", ALL_STATE_CLASSES, ids=_ids)
def test_persisted_fields_are_consistent(cls: type[Any]) -> None:
    """``PERSISTED_FIELDS`` is a frozenset and a subset of the real fields."""
    persisted = cls.PERSISTED_FIELDS
    assert isinstance(persisted, frozenset)
    field_names = {f.name for f in dataclasses.fields(cls)}
    assert persisted <= field_names
    # ``PERSISTED_FIELDS`` itself must be a ClassVar, never a field.
    assert "PERSISTED_FIELDS" not in field_names


@pytest.mark.parametrize("cls", ALL_STATE_CLASSES, ids=_ids)
def test_persisted_fields_exact_contract(cls: type[Any]) -> None:
    """The persisted subset matches the plan-section-3 storage contract."""
    assert EXPECTED_PERSISTED[cls] == cls.PERSISTED_FIELDS


def test_external_override_split_exact() -> None:
    """Finding 8: the four value baselines persist; stamps/context do not."""
    assert {
        "last_written_sp",
        "prev_device_sp",
        "last_commanded_hvac",
        "prev_device_mode",
    } == ExternalOverrideRuntime.PERSISTED_FIELDS
    field_names = {f.name for f in dataclasses.fields(ExternalOverrideRuntime)}
    transient = field_names - ExternalOverrideRuntime.PERSISTED_FIELDS
    assert transient == {
        "last_sp_write_ts",
        "last_hvac_cmd_ts",
        "pre_write_sp",
        "own_write_ctx_ids",
    }


def test_user_control_persists_climate_mode_but_not_adopt_log() -> None:
    """``climate_mode`` is store-owned; ``last_adopt_log`` is a log debounce."""
    assert "climate_mode" in UserControlState.PERSISTED_FIELDS
    assert "last_adopt_log" not in UserControlState.PERSISTED_FIELDS
    # Both are real fields — the exclusion is a persistence decision only.
    field_names = {f.name for f in dataclasses.fields(UserControlState)}
    assert {"climate_mode", "last_adopt_log"} <= field_names


def test_pipeline_latches_have_no_tick_budget() -> None:
    """Plan rev. 5: the tick budget is a coordinator metric, not a latch."""
    field_names = {f.name for f in dataclasses.fields(PipelineLatches)}
    assert field_names == {"was_preheating", "was_coasting", "cool_sp_eff_prev"}


def test_default_values_match_coordinator_init() -> None:
    """Defaults mirror today's ``__init__`` (coordinator.py L299-587)."""
    user = UserControlState()
    assert user.enabled is True
    assert user.preset is OverrideMode.NONE
    assert user.climate_mode == "auto"
    assert user.override is None
    assert user.override_expiry_is_switchpoint is False
    assert user.override_stats == []
    assert user.last_adopt_log == ""

    ext = ExternalOverrideRuntime()
    assert ext.last_written_sp is None
    assert isinstance(ext.own_write_ctx_ids, deque)
    assert ext.own_write_ctx_ids.maxlen == 16  # V2 bounded ring

    act = ActuatorRuntime()
    assert act.has_actuated is False
    assert act.last_fed_ts == 0.0

    learn = LearningRuntime()
    assert learn.ref_offset is None
    assert learn.tau_settle is None
    assert learn.last_u_h == 0.0

    window = WindowRuntime()
    assert window.wa_open_threshold == WindowAutoConfig().open_threshold
    assert window.window_open_since is None

    assert PresenceRuntime().last_presence_level == "comfort"
    assert HumidityRuntime().dry_active is False
    assert CompressorRuntime().dynamics is DeviceDynamics.SLOW_HYDRONIC
    assert SafetyRuntime().prev_heating_failed is False
    assert DiagnosticsRuntime().hum_shadow_warned is False
    assert PipelineLatches().cool_sp_eff_prev is None


def test_mutable_defaults_are_not_shared() -> None:
    """default_factory isolation: instances never share mutable containers."""
    a, b = UserControlState(), UserControlState()
    a.override_stats.append({"reason": "test"})
    assert b.override_stats == []

    ea, eb = ExternalOverrideRuntime(), ExternalOverrideRuntime()
    ea.own_write_ctx_ids.append("ctx-1")
    assert len(eb.own_write_ctx_ids) == 0

    la, lb = LearningRuntime(), LearningRuntime()
    assert la.ekf is not lb.ekf
    assert la.pi is not lb.pi


def test_state_groups_are_mutable() -> None:
    """The groups are long-lived mutable state: field assignment must work."""
    user = UserControlState()
    user.override = 21.5
    user.mode_override = "off"
    assert user.override == 21.5

    ext = ExternalOverrideRuntime()
    ext.last_written_sp = 20.0
    ext.pre_write_sp = 19.5
    assert ext.last_written_sp == 20.0

    latches = PipelineLatches()
    latches.was_preheating = True
    assert latches.was_preheating is True

    safety = SafetyRuntime()
    safety.unavailable_since = 1234.5
    assert safety.unavailable_since == 1234.5


def test_slots_reject_unknown_attributes() -> None:
    """slots=True: state cannot grow ad-hoc attributes (unlike today's
    coordinator with its 138 loose ``self._*`` names)."""
    user = UserControlState()
    with pytest.raises(AttributeError):
        user.nonexistent = 1  # type: ignore[attr-defined]
