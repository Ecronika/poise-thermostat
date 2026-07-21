"""Phase-6b S1 consistency gate: coordinator proxies <-> ZoneRuntime state.

Step S1 of phase 6b (option A) moved the eleven long-lived domain-state
groups out of ``PoiseCoordinator.__init__`` into ``ZoneRuntime``
(``runtime/zone_runtime.py``), keeping every historically pinned
``self._*`` name as a property proxy (getter+setter).  This module locks
the three-way consistency the plan demands (proxy names <-> group fields
<-> ``PERSISTED_FIELDS``):

* every moved coordinator attribute has EXACTLY the uniform proxy shape
  (one ``return self._zone_runtime.<group>.<field>`` getter, one
  mirroring setter) — verified by AST over the coordinator SOURCE, so
  this stays pure (no Home Assistant import);
* the mapping is a bijection: every field of every state group is
  reachable through exactly one proxy, and no proxy targets a phantom
  field;
* every persisted field (``PERSISTED_FIELDS``) is therefore covered by a
  proxy, which is what keeps the unchanged ``_save_payload``/codec
  encode path reading the runtime state;
* ``__init__`` no longer seeds any moved attribute directly — the ONE
  entry-dependent seed (``climate_mode``, AR-04) is injected into the
  ``ZoneRuntime`` construction instead of taking the dataclass default;
* ``ZoneRuntime`` owns the eleven group instances plus a replaceable
  clock reference (the ``coord._clock`` test-swap contract).
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


def test_every_moved_name_has_the_uniform_proxy_pair() -> None:
    """Each relocated attribute is a getter+setter onto its group field."""
    getters, setters = _properties(_coordinator_class())
    for name, (group, field) in PROXY_MAP.items():
        expected = ("self", "_zone_runtime", group, field)
        getter = getters.get(name)
        assert getter is not None, f"missing @property getter for {name}"
        assert len(getter.body) == 1 and isinstance(getter.body[0], ast.Return), (
            f"{name}: getter must be a single return"
        )
        ret = getter.body[0].value
        assert ret is not None and _attr_chain(ret) == expected, (
            f"{name}: getter must return self._zone_runtime.{group}.{field}"
        )
        setter = setters.get(name)
        assert setter is not None, f"missing setter for {name}"
        assert len(setter.body) == 1 and isinstance(setter.body[0], ast.Assign), (
            f"{name}: setter must be a single assignment"
        )
        assign = setter.body[0]
        assert len(assign.targets) == 1
        assert _attr_chain(assign.targets[0]) == expected, (
            f"{name}: setter must assign self._zone_runtime.{group}.{field}"
        )
        assert isinstance(assign.value, ast.Name) and assign.value.id == "value"


def test_clock_proxy_targets_the_runtime_clock() -> None:
    """``coord._clock`` reads/replaces ``zone_runtime.clock`` (test-swap pin)."""
    getters, setters = _properties(_coordinator_class())
    expected = ("self", "_zone_runtime", "clock")
    getter = getters["_clock"]
    assert isinstance(getter.body[0], ast.Return)
    ret = getter.body[0].value
    assert ret is not None and _attr_chain(ret) == expected
    setter = setters["_clock"]
    assert isinstance(setter.body[0], ast.Assign)
    assert _attr_chain(setter.body[0].targets[0]) == expected


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
    """Every group field has exactly one proxy; no proxy hits a phantom field."""
    per_group: dict[str, set[str]] = {group: set() for group in GROUP_CLASSES}
    for name, (group, field) in PROXY_MAP.items():
        assert group in GROUP_CLASSES, f"{name}: unknown group {group}"
        assert field not in per_group[group], f"{group}.{field} proxied twice"
        per_group[group].add(field)
    for group, cls in GROUP_CLASSES.items():
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert per_group[group] == field_names, (
            f"{cls.__name__}: proxies {sorted(per_group[group])} != "
            f"fields {sorted(field_names)}"
        )


def test_every_persisted_field_is_reachable_through_a_proxy() -> None:
    """PERSISTED_FIELDS chain: the unchanged encode path keeps full coverage."""
    reachable = {PROXY_MAP[name] for name in PROXY_MAP}
    for group, cls in GROUP_CLASSES.items():
        for field in cls.PERSISTED_FIELDS:
            assert (group, field) in reachable, (
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
