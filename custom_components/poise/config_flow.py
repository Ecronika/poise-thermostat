"""Config flow for Poise — guided per-room onboarding + reconfigure (ADR-0008).

One entry per room. Pick the room sensor and the thermostat/TRV to control;
optional inputs improve accuracy. The reconfigure step lets the saved settings
be edited in place without removing the entry (so learning is preserved).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .adaptive_cool import adaptive_cool_mode
from .config_reconcile import reconcile_reconfigure
from .config_schema import (
    _RECONFIGURE_SECTIONS,
    _extra_window_ns,
    _options_schema,
    _options_sections,
    _reconfigure_schema,
    _setup_schema,
    _system_schema,
    _system_suggested,
)
from .config_sections import flatten_sections, nest_by_section
from .const import (
    CONF_ACTUATOR,
    CONF_ADAPTIVE_COOL,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_DAYS,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DEFAULT_COMFORT_BASE,
    DEFAULT_SETBACK_DELTA,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from .control.hub_aggregate import parse_service_action
from .migration import SETUP_TUNING_KEYS

_LOGGER = logging.getLogger(__name__)

# Sentinel for "no comfort_days_N key was submitted on this form" — distinct
# from the runtime parser's OWN ``_MISSING`` (runtime/config.py), which marks
# "the merged config mapping has no such key at all" for the fail-closed mask
# parse. Both are private, module-local stand-ins for the same "absent, not
# merely None/empty/falsy" idea, kept as two definitions on purpose: this
# module is HA-coupled (imports homeassistant.config_entries) and must not
# become an import dependency of the pure runtime/config.py, or vice versa.
_MISSING = object()


def _renumber_windows(flat: dict[str, Any]) -> str | None:
    """Validate + compact the numbered window TRIPLES in a submitted flat form.

    Per pair both bounds or neither (one alone is ambiguous — same rule as the
    base pair); valid extra windows are renumbered gaplessly from 2 so deleting
    a middle window never strands later ones. Returns an error key or None; the
    submitted options replace every form-owned key wholesale (window fields are
    always form-owned), so dropped keys vanish without explicit deletion —
    only non-form keys are carried over by the submit (review A.3).

    P2.3 / review Rev. 2.3 point 4: ``comfort_days_N`` rides along with its
    window as a TRIPLE, not just the start/end pair. ``_extra_window_ns``
    matches ONLY start/end keys (F30, deliberately unchanged) — a day-only
    key must never conjure a UI window on its own — so an orphaned
    ``comfort_days_N`` (its start/end pair already gone) would never be
    reached by the pairs loop below and would keep drifting under a stale
    index forever. The separate ``day_ns`` regex scan pops EVERY
    ``comfort_days_*`` key up front (orphans included) and only real windows
    get one rewritten back, at the new index. A missing ``days_N`` for a
    window stays missing after renumbering — legacy ALL_DAYS is never
    materialized onto a window that never had a mask.
    """
    window_ns = _extra_window_ns(flat)
    day_ns = {
        int(m.group(1))
        for key in list(flat)
        if (m := re.fullmatch(rf"{CONF_COMFORT_DAYS}_(\d+)", str(key)))
    }
    days_by_n = {n: flat.pop(f"{CONF_COMFORT_DAYS}_{n}") for n in day_ns}
    triples: list[tuple[Any, Any, Any]] = []
    for n in window_ns:
        s_val = flat.pop(f"{CONF_COMFORT_START}_{n}", None)
        e_val = flat.pop(f"{CONF_COMFORT_END}_{n}", None)
        if bool(s_val) != bool(e_val):
            return "comfort_window_pair"
        if s_val and e_val:
            triples.append((s_val, e_val, days_by_n.get(n, _MISSING)))
    for i, (s_val, e_val, d_val) in enumerate(triples, start=2):
        flat[f"{CONF_COMFORT_START}_{i}"] = s_val
        flat[f"{CONF_COMFORT_END}_{i}"] = e_val
        if d_val is not _MISSING:
            flat[f"{CONF_COMFORT_DAYS}_{i}"] = d_val
    return None


def _empty_days_error(flat: Mapping[str, Any]) -> str | None:
    """UI-only guard (review Rev. 2.2/2.3): reject an explicit EMPTY weekday
    selection on a window that has real times.

    The runtime parser stays defensive regardless (an empty/invalid
    ``comfort_days`` fail-closes to mask 0 -> that window degrades to
    always-setback, never silently to all-week comfort) — this is purely a
    save-time nudge, because an empty multi-select on an otherwise-filled
    window is almost certainly a UI mis-click, not intent. Checked BEFORE
    ``_renumber_windows`` pops the keys it inspects, so it sees the form
    exactly as submitted (base pair plus every still-numbered window,
    including ones about to be renumbered or dropped)."""
    for n in (None, *_extra_window_ns(flat)):
        suffix = "" if n is None else f"_{n}"
        has_times = bool(flat.get(f"{CONF_COMFORT_START}{suffix}")) and bool(
            flat.get(f"{CONF_COMFORT_END}{suffix}")
        )
        days_key = f"{CONF_COMFORT_DAYS}{suffix}"
        if has_times and days_key in flat and not flat[days_key]:
            return "schedule_days_empty"
    return None


def _heat_cool_only(hass: HomeAssistant, actuator: str) -> bool:
    """P2-4: True when the actuator can only condition via ``heat_cool`` (dual
    target_temp_high/low) and offers no single-target ``heat`` or ``cool`` mode.

    Poise writes one ``temperature`` per actuator, so such a device rejects the
    call and can't be driven. If ``hvac_modes`` is missing (the actuator is
    unavailable at validation time) return False so the flow isn't blocked.
    """
    state = hass.states.get(actuator)
    modes = state.attributes.get("hvac_modes") if state is not None else None
    if not modes:
        return False
    mode_set = set(modes)
    return HVACMode.HEAT_COOL in mode_set and not (
        {HVACMode.HEAT, HVACMode.COOL} & mode_set
    )


def _validate_room_entities(
    hass: HomeAssistant, temp_sensor: str, actuator: str
) -> dict[str, str]:
    """The entity checks room CREATE and room RECONFIGURE share (review
    2026-08-19 P2b): a heat_cool-only actuator is rejected (P2-4 — Poise
    writes a single ``temperature`` and can't drive a dual-setpoint-only
    device), and the room sensor must be free-standing — not the actuator's
    own built-in probe (same device), or the model learns the wrong room.
    Unique-id and abort semantics deliberately stay at the callers: create
    and reconfigure abort differently, and forcing them through one helper
    would be a false abstraction.
    """
    errors: dict[str, str] = {}
    if _heat_cool_only(hass, actuator):
        errors[CONF_ACTUATOR] = "heat_cool_only"
    reg = er.async_get(hass)
    te = reg.async_get(temp_sensor)
    ae = reg.async_get(actuator)
    if te and ae and te.device_id and te.device_id == ae.device_id:
        errors[CONF_TEMP_SENSOR] = "sensor_on_actuator"
    return errors


def _validate_boiler_actions(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Reject a boiler on/off action that doesn't parse (F11).

    An unusable action would silently leave the hub shadow-only, so a non-empty
    action that ``parse_service_action`` can't parse fails the form. An empty
    action stays allowed (diagnostic-only hub).

    Both stored forms are accepted: the structured mapping the field editor
    writes and the legacy free-text spec (which the form itself can still submit
    on the supported minimum, where ``ObjectSelector`` validates nothing — see
    ``_boiler_action``). They get different messages because the advice differs:
    a structured value has named fields, so "use the slash format" would be
    wrong guidance.
    """
    for key in (CONF_BOILER_ON_ACTION, CONF_BOILER_OFF_ACTION):
        spec = user_input.get(key)
        if spec and parse_service_action(spec) is None:
            if isinstance(spec, Mapping):
                return {"base": "invalid_boiler_action_fields"}
            return {"base": "invalid_boiler_action"}
    return {}


class PoiseConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[misc, call-arg]
    """Guided per-room config flow with reconfigure support."""

    # V2 (ADR-0007): async_migrate_entry splits data->options and normalizes the
    # window/presence/occupancy pickers (now multiple=True) to lists.
    # MINOR_VERSION 2 (ADR-0059 §7): migration pins pre-0.162 zones to the "timer"
    # override policy so their fixed-2 h manual hold is preserved verbatim.
    # MINOR_VERSION 3: the onboarding step no longer writes its two tuning fields
    # (SETUP_TUNING_KEYS) into ``data`` — the migration pulls them out of ``data``
    # on entries created before that, so ``entry.data`` means "structure" again.
    VERSION = 2
    MINOR_VERSION = 3
    # F5: hub-existence captured when the reconfigure form was RENDERED, reused on
    # submit so the anlagen section shown and the reconcile's structural flag can
    # never disagree. The class-level default also gives mypy the type at the
    # submit read site (it is otherwise only assigned in the render branch).
    _reconf_structural_rendered: bool = False

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        # F9: the system hub has no hot-tunable room options — its options flow
        # aborts immediately (the hub is edited via Reconfigure). Rooms get the
        # real tuning flow.
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM:
            return PoiseHubOptionsFlow()
        return PoiseOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # P1-2: Poise's control path is Celsius-only — reject imperial/°F Home
        # Assistant installs up front rather than silently mis-controlling.
        if self.hass.config.units is US_CUSTOMARY_SYSTEM:
            return self.async_abort(reason="imperial_not_supported")
        # AR-30: offer the singleton system hub only once at least one room entry
        # exists — a hub with no zones to aggregate has nothing to do, so a fresh
        # install starts with just "room" (system appears on a later add).
        has_room = any(
            e.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_SYSTEM
            for e in self._async_current_entries()
        )
        menu = ["room", "system"] if has_room else ["room"]
        return self.async_show_menu(step_id="user", menu_options=menu)

    async def async_step_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # The flattened sections land in entry.data — except the two tuning
            # fields the accuracy section collects (SETUP_TUNING_KEYS), which go
            # straight into entry.options below. ``entry.data`` therefore means
            # "structural wiring" on a fresh entry too, not "whatever the first
            # form happened to show" (MINOR_VERSION 3 does the same for entries
            # created before this).
            data = flatten_sections(user_input, ("accuracy",))
            act = data[CONF_ACTUATOR]
            # (a)+(b): the shared entity checks (heat_cool-only actuator,
            # sensor on the actuator's own device) — see _validate_room_entities.
            errors.update(
                _validate_room_entities(self.hass, data[CONF_TEMP_SENSOR], act)
            )
            # (c) one entry per actuator; name the zone that already owns it.
            for other in self._async_current_entries():
                if other.unique_id == act:
                    return self.async_abort(
                        reason="actuator_in_use",
                        description_placeholders={"zone": other.title},
                    )
            if not errors:
                if not data.get(CONF_NAME):
                    state = self.hass.states.get(act)
                    data[CONF_NAME] = (state.name if state else None) or act
                await self.async_set_unique_id(act)
                # Bare duplicate-abort: with no ``updates`` this call can
                # neither update nor reload an entry, so the 2026.12
                # listener-vs-reload rule does not apply here (its real scope
                # is pinned by test_ha_deprecations).
                self._abort_if_unique_id_configured()
                # Structure -> data, the two tuning values -> options. Reads are
                # merged either way ({**data, **options}); what changes is the
                # MEANING of entry.data, which the reload-vs-hot-apply predicate
                # (PoiseCoordinator.structural_unchanged) keys on.
                options = {k: data.pop(k) for k in SETUP_TUNING_KEYS if k in data}
                return self.async_create_entry(
                    title=data[CONF_NAME], data=data, options=options
                )
        return self.async_show_form(
            step_id="room", data_schema=_setup_schema(self.hass), errors=errors
        )

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # singleton hub entry (ADR-0038)
        await self.async_set_unique_id("poise_system")
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_boiler_actions(user_input)  # F11
            if not errors:
                return self.async_create_entry(
                    title="Poise System",
                    data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, **user_input},
                )
        schema = _system_schema()
        if user_input is not None:
            # A rejected submit keeps what was entered. This matters more now
            # that a boiler action is filled in field by field: re-rendering an
            # empty form would throw the whole dialog away over one typo. The
            # raw submit is used as-is (NOT via _system_suggested, which drops
            # an unparseable value — here that value is exactly what has to come
            # back for the user to fix).
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="system", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # P1-2: same Celsius-only gate on reconfigure — an entry can't be
        # reconfigured into an imperial/°F system either.
        if self.hass.config.units is US_CUSTOMARY_SYSTEM:
            return self.async_abort(reason="imperial_not_supported")
        entry = self._get_reconfigure_entry()
        is_system = entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM
        errors: dict[str, str] = {}
        if is_system:
            if user_input is not None:
                errors = _validate_boiler_actions(user_input)  # F11
                if not errors:
                    # V7: full replace (not merge); keep the ENTRY_TYPE tag.
                    # E.13d: store only — see the room branch below.
                    self.hass.config_entries.async_update_entry(
                        entry, data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, **user_input}
                    )
                    self._schedule_reload_if_unloaded(entry)
                    return self.async_abort(reason="reconfigure_successful")
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(
                    _system_schema(), _system_suggested(entry.data)
                ),
                errors=errors,
            )
        # Room reconfigure owns only structural + sensor + installation fields; tuning
        # stays in the options flow. reconcile_reconfigure carries any tuning still in
        # data over to options so shrinking the form never drops a setting. Built from
        # the dynamic section map so numbered comfort windows count as tuning too.
        tuning = {
            f
            for fields in _options_sections({**entry.data, **entry.options}).values()
            for f in fields
        }
        if user_input is not None:
            flat = flatten_sections(user_input, _RECONFIGURE_SECTIONS)
            # 1.1/1.2: the actuator is a zone's unique_id — re-validate so a changed
            # actuator can't silently collide with another zone's entry.
            await self.async_set_unique_id(flat[CONF_ACTUATOR])
            for other in self._async_current_entries():
                if (
                    other.entry_id != entry.entry_id
                    and other.unique_id == self.unique_id
                ):
                    return self.async_abort(reason="already_configured")
            # F3/P2-4: the shared entity checks, mirroring async_step_room —
            # see _validate_room_entities.
            errors.update(
                _validate_room_entities(
                    self.hass, flat[CONF_TEMP_SENSOR], flat[CONF_ACTUATOR]
                )
            )
            if not errors:
                # F5: reuse the hub-existence captured when the form was RENDERED so
                # a hub added/removed between render and submit can't flip which
                # fields the reconcile treats as rendered.
                hub_exists = self._reconf_structural_rendered
                # AR-09: signal that the anlagen section was rendered (a hub is
                # present) so a structural field the user CLEARED there is dropped,
                # not reanimated from old_data.
                new_data, new_options = reconcile_reconfigure(
                    flat,
                    entry.data,
                    entry.options,
                    tuning,
                    structural_section_rendered=hub_exists,
                )
                # AR-12: a reconfigure onto a DIFFERENT actuator must release the OLD
                # one — park it and hand its TRV sensor source back to internal, or
                # the old device stays frozen against Poise's external feed on reload.
                old_actuator = entry.data.get(CONF_ACTUATOR)
                if (
                    isinstance(old_actuator, str)
                    and old_actuator
                    and old_actuator != new_data.get(CONF_ACTUATOR)
                ):
                    # P1.5/D3: a live calibration offset is handed back BEFORE
                    # the park — the old device must report its original
                    # offset again before it leaves Poise's ownership. FAILED
                    # is a form error, nothing is written: the old config
                    # stays intact and the submit can simply be retried
                    # (already_at_target then confirms a slow device).
                    if not await self._handoff_calibration_before_swap(entry):
                        errors["base"] = "calibration_restore_failed"
                    else:
                        await self._park_replaced_actuator(entry, old_actuator)
                if not errors:
                    # Store only — the update listener is the single reload
                    # authority (see ``_async_options_updated``). Written out
                    # instead of ``async_update_and_abort`` on purpose: that
                    # helper only reaches ConfigFlow in HA 2025.12, and these
                    # two calls are exactly what it does, on every version we
                    # support.
                    self.hass.config_entries.async_update_entry(
                        entry,
                        unique_id=self.unique_id,
                        data=new_data,
                        options=new_options,
                    )
                    self._schedule_reload_if_unloaded(entry)
                    return self.async_abort(reason="reconfigure_successful")
        current = {**entry.data, **entry.options}
        suggested = nest_by_section(current, _RECONFIGURE_SECTIONS)
        # the structural fields live at the top level (not in a section), so carry
        # them into the suggested values or they'd show empty on reconfigure.
        for key in (CONF_NAME, CONF_TEMP_SENSOR, CONF_ACTUATOR):
            if key in current:
                suggested[key] = current[key]
        # F5: capture hub-existence at RENDER and reuse it on submit, so the anlagen
        # section shown and the reconcile's structural flag can never disagree.
        hub_exists = any(
            e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM
            for e in self.hass.config_entries.async_entries(DOMAIN)
        )
        self._reconf_structural_rendered = hub_exists
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _reconfigure_schema(self.hass, hub_exists), suggested
            ),
            errors=errors,
        )

    def _schedule_reload_if_unloaded(self, entry: ConfigEntry) -> None:
        """Reload a reconfigured entry that has no update listener (E.13d).

        A LOADED entry carries the update listener from ``async_setup_entry``,
        and that listener is the single reload authority — the flow must not
        reload as well (HA turns listener + reloading flow method into an
        error in 2026.12). An entry that is NOT loaded has no listener, so the
        flow schedules the reload itself — with no listener present this is
        not the deprecated combination. For a zone stuck in SETUP_ERROR (e.g.
        the corrupt-entry guard) nothing else would ever apply the corrected
        wiring or run a pending schema migration; for SETUP_RETRY the schedule
        merely applies it now instead of waiting out HA's retry backoff.
        """
        from homeassistant.config_entries import ConfigEntryState

        # ``recoverable`` keeps this to the states a reload can actually fix
        # (NOT_LOADED / SETUP_RETRY / SETUP_ERROR). Scheduling one for e.g.
        # MIGRATION_ERROR or SETUP_IN_PROGRESS would only raise inside a
        # detached task.
        if entry.state is not ConfigEntryState.LOADED and entry.state.recoverable:
            self.hass.config_entries.async_schedule_reload(entry.entry_id)

    async def _park_replaced_actuator(self, entry: ConfigEntry, actuator: str) -> None:
        """AR-12: release a room's PREVIOUS actuator when a reconfigure repoints the
        zone to a different one — park it in a capability-appropriate end state and
        flip a TRV sensor source back to internal, so the old device does not keep
        regulating against Poise's now-frozen external feed after the reload.

        Mirrors the delete-time park (``_remove_room_entry``). The live, Store-owned
        climate_mode wins over the (now option-free) config copy.
        """
        from .ha.actuator_lifecycle import park_actuator

        cfg = {**entry.data, **entry.options}
        coordinator = getattr(entry, "runtime_data", None)
        mode = getattr(coordinator, "climate_mode", None) or str(
            cfg.get(CONF_CLIMATE_MODE, "auto")
        )
        setback = float(cfg.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)) - float(
            cfg.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA)
        )
        # State read, device_min clamp, plan and execution live in the shared
        # lifecycle module (review 2026-08-19 P1) — only the policy stays here.
        await park_actuator(
            self.hass, actuator, climate_mode=mode, setback_setpoint=setback
        )

    async def _handoff_calibration_before_swap(self, entry: ConfigEntry) -> bool:
        """P1.5/D3: restore a live calibration offset before the actuator swap.

        Loaded entry: the runtime is the truth — the coordinator lifecycle
        port runs under the tick lock, clears the runtime ownership and
        disarms the old instance's calibration path before releasing the lock
        (F27 + §0.6/§0.6a re-acquisition race); a bare store write would be
        overwritten by that coordinator's final save. Unloaded entry: the
        store IS the truth (§0.5 point 1) — restore, then clear the two
        ownership keys on success.

        ``cal_entity``/``cal_baseline`` are SNAPSHOTTED FIRST: a successful
        port clears them before returning, and the WARN policy stays with the
        flow (§0.6a point 2) — ``GONE`` (entity structurally removed: whoever
        swaps the actuator because the old device is gone must not be
        blocked) logs the snapshot and continues. Returns False exactly on
        ``FAILED``; the caller then shows the form error and writes nothing.
        """
        from .ha import actuator_lifecycle
        from .ha.actuator_lifecycle import CalibrationRestoreResult
        from .storage import PoiseStore

        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            runtime_act = coordinator.runtime.actuator
            snap_entity = runtime_act.cal_entity
            snap_baseline = runtime_act.cal_baseline
            result = await coordinator.async_prepare_actuator_handoff()
        else:
            store = PoiseStore(self.hass, entry.entry_id)
            stored = await store.load() or {}
            snap_baseline = stored.get("cal_baseline")
            snap_entity = stored.get("cal_entity")
            if snap_baseline is None:
                return True  # no ownership — nothing to hand back
            # resolve_restore owns the corrupt-shape rule (missing entity or
            # non-numeric baseline -> structurally GONE).
            result = await actuator_lifecycle.resolve_restore(
                self.hass, entity_id=snap_entity, baseline=snap_baseline
            )
            if result is not CalibrationRestoreResult.FAILED:
                stored["cal_baseline"] = None
                stored["cal_entity"] = None
                await store.save(stored)
        if result is CalibrationRestoreResult.GONE:
            _LOGGER.warning(
                "Poise: calibration entity %s is structurally gone; the "
                "written offset (baseline %s) cannot be restored on the "
                "actuator swap — ownership released, reconfigure continues",
                snap_entity,
                snap_baseline,
            )
        return result is not CalibrationRestoreResult.FAILED


class PoiseOptionsFlow(OptionsFlow):  # type: ignore[misc]
    """Edit volatile tuning in place — no reload, so learning is preserved."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        # Effective current config drives the dynamic schedule section (ADR-0070):
        # the rendered form shows every configured window plus one empty pair.
        current = {**self.config_entry.data, **self.config_entry.options}
        # legacy bool -> canonical mode so the tri-state dropdown pre-fills
        if CONF_ADAPTIVE_COOL in current:
            current[CONF_ADAPTIVE_COOL] = adaptive_cool_mode(
                current[CONF_ADAPTIVE_COOL]
            )
        sections = _options_sections(current)
        if user_input is not None:
            # Sections nest the submit one level; store it flat (config_sections)
            # so the coordinator/merge/reconfigure paths stay unchanged.
            flat = flatten_sections(user_input, sections)
            # (a) comfort windows: per pair both bounds or neither (one alone is
            # ambiguous). Extra pairs are compacted gaplessly; the submit
            # replaces every FORM-OWNED key wholesale, so cleared windows simply
            # drop out (non-form keys are carried over below, review A.3).
            if bool(flat.get(CONF_COMFORT_START)) != bool(flat.get(CONF_COMFORT_END)):
                errors["base"] = "comfort_window_pair"
            elif (days_error := _empty_days_error(flat)) is not None:
                errors["base"] = days_error
            elif (pair_error := _renumber_windows(flat)) is not None:
                errors["base"] = pair_error
            else:
                # Keys the rendered form does not own (e.g. the ADR-0067
                # ``clo_offset`` the suggestion fix flow writes) must survive
                # the wholesale replace; form-owned keys keep replace
                # semantics, so cleared windows still drop out (review A.3).
                form_keys = {f for fields in sections.values() for f in fields}
                carried = {
                    k: v
                    for k, v in self.config_entry.options.items()
                    if k not in form_keys
                }
                return self.async_create_entry(title="", data={**carried, **flat})
            suggested = user_input
        else:
            # Pre-fill each section from the effective current config (data+options).
            suggested = nest_by_section(current, sections)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(self.hass, current), suggested
            ),
            errors=errors,
        )


class PoiseHubOptionsFlow(OptionsFlow):  # type: ignore[misc]
    """The system hub has no hot-tunable options (F9).

    Its shared-plant settings are structural and are edited via Reconfigure, so the
    options flow aborts immediately rather than showing an empty form.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_abort(reason="hub_no_options")
