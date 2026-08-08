"""Phase-6b consistency gate: ZoneRuntime state relocation (proxies removed).

Step S1 of phase 6b (option A) moved the eleven long-lived domain-state
groups out of ``PoiseCoordinator.__init__`` into ``ZoneRuntime``
(``runtime/zone_runtime.py``).  During the migration every historically
pinned ``self._*`` name kept a transparent property proxy (getter+setter);
Step 2 S-C then DELETED those proxies once every call site read the group
directly.  This module locks the relocation and its completion (relocation
table <-> group fields <-> ``PERSISTED_FIELDS``):

* no migrated name survives as a coordinator ``@property``/setter — the
  proxies are gone, verified by AST over the coordinator SOURCE, so this
  stays pure (no Home Assistant import);
* ``PROXY_MAP`` stays the canonical relocation table and is a bijection onto
  the group fields MINUS ``POST_RELOCATION_FIELDS``: every relocated field is
  reached by exactly one entry, no entry targets a phantom field, and any
  field born after phase 6b must be declared as such instead of being given a
  fictional historical proxy name;
* every persisted field (``PERSISTED_FIELDS``) is therefore covered by the
  relocation table, which is what keeps the unchanged ``_save_payload``/
  codec encode path reading the runtime state;
* ``__init__`` no longer seeds any moved attribute directly — the ONE
  entry-dependent seed (``climate_mode``, AR-04) is injected into the
  ``ZoneRuntime`` construction instead of taking the dataclass default;
* ``ZoneRuntime`` owns the eleven group instances plus a replaceable
  clock reference (the ``coord.runtime.clock`` test-swap contract).
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Any

from custom_components.poise.clock import ManualClock
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
from custom_components.poise.runtime.zone_runtime import ZoneRuntime

COORDINATOR_SRC = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "poise"
    / "coordinator.py"
)

# ZoneRuntime group attribute -> state-group class (plan section 3).
GROUP_CLASSES: dict[str, type[Any]] = {
    "user": UserControlState,
    "external": ExternalOverrideRuntime,
    "actuator": ActuatorRuntime,
    "learning": LearningRuntime,
    "window": WindowRuntime,
    "presence": PresenceRuntime,
    "humidity": HumidityRuntime,
    "compressor": CompressorRuntime,
    "safety": SafetyRuntime,
    "diagnostics": DiagnosticsRuntime,
    "latches": PipelineLatches,
}

# coordinator proxy name -> (ZoneRuntime group attr, group field).  This is
# the canonical S1 relocation table (plan section 3 incl. the underscore-drop
# and the trm_tracker/regq/hdh names); the AST checks below hold the
# coordinator source to it, the bijection check holds it to the dataclasses.
PROXY_MAP: dict[str, tuple[str, str]] = {
    # UserControlState (store-owned user intention)
    "_enabled": ("user", "enabled"),
    "_preset": ("user", "preset"),
    "_climate_mode": ("user", "climate_mode"),
    "_window_bypass": ("user", "window_bypass"),
    "_override": ("user", "override"),
    "_mode_override": ("user", "mode_override"),
    "_override_set_wall": ("user", "override_set_wall"),
    "_override_requested": ("user", "override_requested"),
    "_override_expires_at": ("user", "override_expires_at"),
    "_override_expiry_is_switchpoint": ("user", "override_expiry_is_switchpoint"),
    "_override_reason": ("user", "override_reason"),
    "_boost_expires_at": ("user", "boost_expires_at"),
    "_boost_prev_preset": ("user", "boost_prev_preset"),
    "_override_stats": ("user", "override_stats"),
    "_last_adopt_log": ("user", "last_adopt_log"),
    # ExternalOverrideRuntime (echo/adoption baselines, finding 8)
    "_last_written_sp": ("external", "last_written_sp"),
    "_prev_device_sp": ("external", "prev_device_sp"),
    "_last_commanded_hvac": ("external", "last_commanded_hvac"),
    "_prev_device_mode": ("external", "prev_device_mode"),
    "_last_sp_write_ts": ("external", "last_sp_write_ts"),
    "_last_hvac_cmd_ts": ("external", "last_hvac_cmd_ts"),
    "_pre_write_sp": ("external", "pre_write_sp"),
    "_own_write_ctx_ids": ("external", "own_write_ctx_ids"),
    # ActuatorRuntime
    "_last_target": ("actuator", "last_target"),
    "_last_written_mode": ("actuator", "last_written_mode"),
    "_has_actuated": ("actuator", "has_actuated"),
    "_last_fed": ("actuator", "last_fed"),
    "_last_fed_ts": ("actuator", "last_fed_ts"),
    # LearningRuntime
    "_ekf": ("learning", "ekf"),
    "_trm_tracker": ("learning", "trm_tracker"),
    "_seasonless": ("learning", "seasonless"),
    "_prev_room": ("learning", "prev_room"),
    "_prev_room_mono": ("learning", "prev_room_mono"),
    "_heatup_acc": ("learning", "heatup_acc"),
    "_last_mono": ("learning", "last_mono"),
    "_last_u_h": ("learning", "last_u_h"),
    "_last_u_c": ("learning", "last_u_c"),
    "_last_q_solar": ("learning", "last_q_solar"),
    "_ref_offset": ("learning", "ref_offset"),
    "_ref_last_mono": ("learning", "ref_last_mono"),
    "_tau_settle": ("learning", "tau_settle"),
    "_tau_last_mono": ("learning", "tau_last_mono"),
    "_pi": ("learning", "pi"),
    # WindowRuntime
    "_window_auto": ("window", "window_auto"),
    "_was_cooling": ("window", "was_cooling"),
    "_wa_ref_room": ("window", "wa_ref_room"),
    "_wa_ref_mono": ("window", "wa_ref_mono"),
    "_wa_prev_mono": ("window", "wa_prev_mono"),
    "_wa_open_threshold": ("window", "wa_open_threshold"),
    "_last_window_open": ("window", "last_window_open"),
    "_window_open_since": ("window", "window_open_since"),
    # PresenceRuntime
    "_prev_home": ("presence", "prev_home"),
    "_last_presence_level": ("presence", "last_presence_level"),
    "_room_absent_since": ("presence", "room_absent_since"),
    # HumidityRuntime
    "_dry_active": ("humidity", "dry_active"),
    # CompressorRuntime
    "_multi_lifecycle": ("compressor", "multi_lifecycle"),
    "_dynamics": ("compressor", "dynamics"),
    # SafetyRuntime (moves into the runtime per option A)
    "_failure": ("safety", "failure"),
    "_prev_heating_failed": ("safety", "prev_heating_failed"),
    "_unavailable_since": ("safety", "unavailable_since"),
    # DiagnosticsRuntime
    "_outcome_stats": ("diagnostics", "outcome_stats"),
    "_regq": ("diagnostics", "regq"),
    "_ca_last_mono": ("diagnostics", "ca_last_mono"),
    "_outcome_session": ("diagnostics", "outcome_session"),
    "_hdh_last_mono": ("diagnostics", "hdh_last_mono"),
    "_hdh": ("diagnostics", "hdh"),
    "_hum_shadow_warned": ("diagnostics", "hum_shadow_warned"),
    # PipelineLatches
    "_was_preheating": ("latches", "was_preheating"),
    "_was_coasting": ("latches", "was_coasting"),
    "_cool_sp_eff_prev": ("latches", "cool_sp_eff_prev"),
}

# Group fields that were BORN in the runtime, after the phase-6b relocation —
# they never had a coordinator attribute, so they have no row above. Listing
# them here keeps the bijection honest instead of inventing a historical proxy
# name. Every entry needs a reason.
POST_RELOCATION_FIELDS: dict[tuple[str, str], str] = {
    # F-HUMSHADOW (phase 10) split the climate band into two boundaries, and
    # each boundary owns its own warn-once latch.
    ("diagnostics", "climate_shadow_warned"): "F-HUMSHADOW second warn-once latch",
    # ADR-0066 humidity axis (v0.180.0): ventilation-advice latch + surface-RH
    # EWMA — born on the group, persisted via the codec snapshot built directly
    # from zone_runtime (no coordinator proxy ever existed).
    ("humidity", "vent_active"): "ADR-0066 ventilation-advice hysteresis latch",
    ("humidity", "surface_rh_mean"): "ADR-0066 surface-RH EWMA (tau=48 h)",
    ("humidity", "vent_last_action"): "ADR-0066 B.5 emission edge (transient)",
    # ADR-0054 Nachtrag V1: forecast daily mean for the clo blend, latched
    # once per local day — transient, recomputed on the first tick of a run.
    ("diagnostics", "clo_forecast_key"): "ADR-0054 V1 clo forecast day latch key",
    ("diagnostics", "clo_forecast_day"): "ADR-0054 V1 clo forecast daily mean",
    # ADR-0060 §2: hysteresis anchor of the advisory season-mode hint —
    # transient (T_rm re-raises it after a restart when still beyond the
    # raise threshold).
    ("diagnostics", "season_hint_prev"): "ADR-0060 §2 season-hint hysteresis",
    # ADR-0067 §4: transient emission-slot memory of the conflict rule.
    ("diagnostics", "pending_suggestion_family"): "ADR-0067 §4 suggestion slot",
    # ADR-0067 F1: comfort-feedback statistic — born on the group, persisted
    # via the codec snapshot (no coordinator proxy ever existed).
    ("user", "feedback_stats"): "ADR-0067 F1 comfort-feedback statistic",
    # ADR-0060 L2: rejection of a suggestion suppresses exactly that pattern
    # key for 30 days — must survive a restart.
    ("user", "suggestion_rejected_key"): "ADR-0060 L2 rejected pattern key",
    ("user", "suggestion_rejected_at"): "ADR-0060 L2 rejection wall stamp",
    # ADR-0067 F2: own cool-down slot — a clo rejection must not overwrite a
    # remembered L2 rejection (two independent suggestion families).
    ("user", "clo_suggestion_rejected_key"): "ADR-0067 F2 rejected pattern key",
    ("user", "clo_suggestion_rejected_at"): "ADR-0067 F2 rejection wall stamp",
    # ADR-0060 §3 season gate: last tick the season-mode hint stood — floors
    # the L2 emission detection (mismatch-era events are mode signals, not
    # comfort evidence) and must survive mode switches and restarts.
    ("user", "season_hint_last_active_ts"): "ADR-0060 §3 season-gate floor stamp",
    # ADR-0055 N1: own elapsed anchor for the time-weighted PPD fold — PMV
    # validity and the CA fairness mask diverge, so the PPD clock is separate.
    ("diagnostics", "ppd_last_mono"): "ADR-0055 N1 PPD-fold elapsed anchor",
    # ADR-0069 U2: the persisted tier-2 activation lifecycle (latch, dwell,
    # baseline + signature) — documented boundary: lives under DiagnosticsRuntime
    # next to the quality metrics it consumes, never in PipelineLatches.
    ("diagnostics", "comfort_activation"): "ADR-0069 tier-2 activation state",
    # ADR-0068 U3: fan-stage echo baselines (B5-analog value baselines persist,
    # the ts stamp is transient and restore-staled like the mode channel's).
    ("external", "last_commanded_fan"): "ADR-0068 fan-command echo baseline",
    ("external", "prev_device_fan"): "ADR-0068 fan move-guard baseline",
    ("external", "last_fan_cmd_ts"): "ADR-0068 fan echo-window stamp (transient)",
    # ADR-0068 U6: the fan-first FSM state — transient control-flow memory
    # (restart -> idle is safe and documented); carried tick-to-tick.
    ("latches", "fan_first"): "ADR-0068 fan-first FSM state (transient)",
    ("diagnostics", "fan_first_reason"): "ADR-0068 fan-first reason (diagnosis)",
    # ADR-0069 U7/U8: tier-2 stepping anchor + next-tick solver inputs.
    ("diagnostics", "tier2_last_mono"): "ADR-0069 tier-2 step elapsed anchor",
    ("latches", "fan_ce_credit_k"): "ADR-0068 U7 next-tick fan-CE credit",
    ("latches", "pmv_offset_k"): "ADR-0069 U8 next-tick PMV band shift",
}


def _coordinator_class() -> ast.ClassDef:
    tree = ast.parse(COORDINATOR_SRC.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "PoiseCoordinator":
            return node
    raise AssertionError("PoiseCoordinator class not found")


def _attr_chain(node: ast.expr) -> tuple[str, ...]:
    """Flatten ``a.b.c`` into ``("a", "b", "c")``; empty when not a chain."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ()
    parts.append(node.id)
    return tuple(reversed(parts))


def _properties(
    cls: ast.ClassDef,
) -> tuple[dict[str, ast.FunctionDef], dict[str, ast.FunctionDef]]:
    """(getters, setters) of every ``@property``/``@x.setter`` pair."""
    getters: dict[str, ast.FunctionDef] = {}
    setters: dict[str, ast.FunctionDef] = {}
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if isinstance(deco, ast.Name) and deco.id == "property":
                getters[node.name] = node
            elif (
                isinstance(deco, ast.Attribute)
                and deco.attr == "setter"
                and isinstance(deco.value, ast.Name)
                and deco.value.id == node.name
            ):
                setters[node.name] = node
    return getters, setters


def test_no_migrated_name_remains_a_coordinator_proxy() -> None:
    """S-C deleted the proxies: no migrated name may survive as a coordinator
    ``@property``/setter.

    Every relocated field now lives ONLY on its ``ZoneRuntime`` group,
    reached directly (``coord.runtime.<group>.<field>``); a lingering proxy
    would mean a call site still routes through the coordinator instead of
    the group.  ``PROXY_MAP`` remains the canonical relocation table — the
    bijection and persisted-field tests below still hold it to the group
    dataclasses.
    """
    getters, setters = _properties(_coordinator_class())
    for name in PROXY_MAP:
        assert name not in getters, f"{name} still exposes a @property getter proxy"
        assert name not in setters, f"{name} still exposes a setter proxy"


def test_clock_proxy_was_removed() -> None:
    """The ``_clock`` and ``_dirty`` proxies are gone too (S-C).

    These are the two removed proxies that are NOT in ``PROXY_MAP`` (neither is
    a relocated group field), so the loop above does not cover them; pin both
    directly here.  Readers reach the live clock via ``coord.runtime.clock``
    and the ``_ReaderClock`` forwarder; the ``_dirty`` flag (S2 K1) lives on
    ``ZoneRuntime.dirty``, reached via ``coord.runtime.dirty``.  Neither
    ``coord._clock`` nor ``coord._dirty`` is a property any more.
    """
    getters, setters = _properties(_coordinator_class())
    assert "_clock" not in getters
    assert "_clock" not in setters
    assert "_dirty" not in getters
    assert "_dirty" not in setters


def test_init_no_longer_seeds_moved_attributes() -> None:
    """``__init__`` must not assign any relocated ``self._*`` name directly.

    (The values come from the group dataclass defaults; the one entry-
    dependent seed rides the ``ZoneRuntime`` construction below.)  An
    assignment would still WORK (it routes through the setter) but would
    re-introduce a second seeding path that can drift from the dataclass
    defaults — exactly what S1 removed.
    """
    cls = _coordinator_class()
    init = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    moved = set(PROXY_MAP) | {"_clock"}
    offenders: list[str] = []
    for node in ast.walk(init):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            chain = _attr_chain(target)
            if len(chain) == 2 and chain[0] == "self" and chain[1] in moved:
                offenders.append(chain[1])
    assert offenders == [], f"__init__ still seeds moved attributes: {offenders}"


def test_init_constructs_zone_runtime_with_climate_mode_seed() -> None:
    """The ZoneRuntime construction injects the entry ``climate_mode`` seed.

    AR-04: the options/data value seeds only the very first start — the
    dataclass default "auto" must NOT silently take over.
    """
    cls = _coordinator_class()
    init = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    for node in ast.walk(init):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and _attr_chain(node.targets[0]) == ("self", "_zone_runtime")
        ):
            call = node.value
            assert isinstance(call, ast.Call)
            assert isinstance(call.func, ast.Name) and call.func.id == "ZoneRuntime"
            kwargs = {kw.arg for kw in call.keywords}
            assert "climate_mode" in kwargs, (
                "ZoneRuntime construction must inject the entry climate_mode seed"
            )
            return
    raise AssertionError("__init__ does not construct self._zone_runtime")


def test_proxy_map_is_a_bijection_onto_the_group_fields() -> None:
    """Every relocated group field has exactly one proxy row; no row hits a
    phantom field; every field without a row is declared post-relocation."""
    per_group: dict[str, set[str]] = {group: set() for group in GROUP_CLASSES}
    for name, (group, field) in PROXY_MAP.items():
        assert group in GROUP_CLASSES, f"{name}: unknown group {group}"
        assert field not in per_group[group], f"{group}.{field} proxied twice"
        per_group[group].add(field)
    for group, cls in GROUP_CLASSES.items():
        born_later = {f for (g, f) in POST_RELOCATION_FIELDS if g == group}
        field_names = {f.name for f in dataclasses.fields(cls)} - born_later
        assert per_group[group] == field_names, (
            f"{cls.__name__}: proxies {sorted(per_group[group])} != "
            f"fields {sorted(field_names)} (fields added after phase 6b belong "
            f"in POST_RELOCATION_FIELDS, not in PROXY_MAP)"
        )


def test_post_relocation_fields_actually_exist() -> None:
    """The escape hatch may not rot: every declared field must still be a real
    field of its group, and must NOT also carry a proxy row."""
    for (group, field), reason in POST_RELOCATION_FIELDS.items():
        assert group in GROUP_CLASSES, f"unknown group {group}"
        names = {f.name for f in dataclasses.fields(GROUP_CLASSES[group])}
        assert field in names, f"{group}.{field} no longer exists ({reason})"
        assert (group, field) not in set(PROXY_MAP.values()), (
            f"{group}.{field} is both relocated and declared post-relocation"
        )
        assert reason, f"{group}.{field} needs a reason"


def test_every_persisted_field_is_reachable_through_a_proxy() -> None:
    """PERSISTED_FIELDS chain: the unchanged encode path keeps full coverage.

    Post-relocation fields are exempt: they are encoded straight off the
    group (codec snapshot reads ``zone_runtime.<group>.<field>``), so no
    historical coordinator proxy exists or is needed.
    """
    reachable = {PROXY_MAP[name] for name in PROXY_MAP}
    for group, cls in GROUP_CLASSES.items():
        for field in cls.PERSISTED_FIELDS:
            key = (group, field)
            assert key in reachable or key in POST_RELOCATION_FIELDS, (
                f"persisted {cls.__name__}.{field} has no coordinator proxy"
            )


def test_zone_runtime_owns_the_eleven_groups_and_the_clock() -> None:
    clock = ManualClock(123.0)
    runtime = ZoneRuntime(clock, climate_mode="heat")
    assert runtime.clock is clock
    for group, cls in GROUP_CLASSES.items():
        assert isinstance(getattr(runtime, group), cls)
    # AR-04 seed injection: the entry value, never the dataclass default.
    assert runtime.user.climate_mode == "heat"
    assert ZoneRuntime(clock).user.climate_mode == "auto"
    # Slots: the runtime cannot grow stray state outside the groups.
    assert not hasattr(runtime, "__dict__")


def test_zone_runtime_clock_is_replaceable() -> None:
    """The ``coord._clock = FakeClock(...)`` swap must land here (S1 wiring)."""
    runtime = ZoneRuntime(ManualClock(0.0))
    replacement = ManualClock(999.0)
    runtime.clock = replacement
    assert runtime.clock is replacement
    assert runtime.clock.monotonic() == 999.0


def test_group_defaults_match_the_removed_init_seeds() -> None:
    """Spot-pin the two non-obvious default equivalences S1 relies on."""
    # ``_wa_open_threshold`` was seeded from the DEFAULT WindowAutoConfig
    # (``self._window_auto_cfg = WindowAutoConfig()``) — the dataclass
    # default must stay value-identical.
    assert WindowRuntime().wa_open_threshold == WindowAutoConfig().open_threshold
    # The V2 own-write context ring stays bounded at today's deque(maxlen=16).
    assert ExternalOverrideRuntime().own_write_ctx_ids.maxlen == 16
