"""Repairs platform — the ADR-0060 L2 suggestion fix flow (apply / dismiss).

The coordinator mirrors a detected override pattern into a fixable issue
(``_sync_suggestion_issue``); this flow is the visible decision point the ADR
mandates: **apply** performs the config write over the options path
(``async_update_entry(entry, options=…)``, hot-applied by the options-update
listener — never a silent store mutation), **dismiss** stamps the 30-day
suppression for exactly this pattern key. The cool-down is stamped on BOTH
paths — after an apply too, because the old evidence stays in the L1
statistic and would otherwise immediately re-raise the just-applied pattern.

P1.5 adds a second, deliberately simpler kind: ``trv_calibration``
(``CalibrationOptInFixFlow``) — apply-only, no cool-down, no dismiss step
(rejection is HA's built-in "ignore issue").
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .comfort.schedule import parse_hhmm
from .const import (
    CLO_OFFSET_MAX,
    CONF_CLO_OFFSET,
    CONF_COMFORT_BASE,
    CONF_COMFORT_START,
    CONF_TRV_CALIBRATION,
)
from .control.feedback import CLO_SUGGEST_STEP
from .control.suggestion import SUGGEST_EARLIER_MIN, SUGGEST_STEP_K

# The comfort-base write stays inside the options-flow selector range; the
# engine's norm envelope (ADR-0027/0035) clamps further at runtime.
_BASE_MIN_C = 16.0
_BASE_MAX_C = 26.0


class OverrideSuggestionFixFlow(RepairsFlow):  # type: ignore[misc]
    """Two-choice flow: apply the suggested config change, or dismiss."""

    def __init__(self, hass: HomeAssistant, data: dict[str, Any]) -> None:
        self._hass = hass
        self._data = data

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        return self.async_show_menu(step_id="init", menu_options=["apply", "dismiss"])

    async def async_step_apply(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        entry = self._hass.config_entries.async_get_entry(self._data["entry_id"])
        if entry is not None:
            merged = {**entry.data, **entry.options}
            options = dict(entry.options)
            if self._data["kind"] == "clo_offset":
                current = float(merged.get(CONF_CLO_OFFSET, 0.0))
                new_off = current + float(self._data["direction"]) * CLO_SUGGEST_STEP
                options[CONF_CLO_OFFSET] = round(
                    min(max(new_off, -CLO_OFFSET_MAX), CLO_OFFSET_MAX), 2
                )
            elif self._data["kind"] == "comfort_base":
                base = float(merged.get(CONF_COMFORT_BASE, 21.0))
                new_base = base + float(self._data["direction"]) * SUGGEST_STEP_K
                options[CONF_COMFORT_BASE] = round(
                    min(max(new_base, _BASE_MIN_C), _BASE_MAX_C), 1
                )
            else:  # comfort_earlier
                start = parse_hhmm(merged.get(CONF_COMFORT_START))
                if start is None:
                    # No configured window (stale pattern): nothing to apply —
                    # fall through to the dismiss semantics below.
                    return await self.async_step_dismiss()
                new_start = max(0, start - SUGGEST_EARLIER_MIN)
                options[CONF_COMFORT_START] = (
                    f"{new_start // 60:02d}:{new_start % 60:02d}"
                )
            self._hass.config_entries.async_update_entry(entry, options=options)
            self._stamp_cooldown(entry)
        return self.async_create_entry(title="", data={})

    async def async_step_dismiss(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        entry = self._hass.config_entries.async_get_entry(self._data["entry_id"])
        if entry is not None:
            self._stamp_cooldown(entry)
        return self.async_create_entry(title="", data={})

    def _stamp_cooldown(self, entry: Any) -> None:
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None and hasattr(
            coordinator, "record_suggestion_decision"
        ):
            coordinator.record_suggestion_decision(self._data["key"])


class CalibrationOptInFixFlow(RepairsFlow):  # type: ignore[misc]
    """P1.5 D1: the ``trv_calibration`` fix kind — a confirm/apply step ONLY.

    Deliberately unlike the three learning kinds above: no ``direction``, no
    ``record_suggestion_decision`` and no learning cool-down (there is no L1
    statistic behind this issue that would re-raise it), and explicitly NO
    ``async_step_dismiss`` — rejection is Home Assistant's built-in "ignore
    issue" on the repair itself, which keeps the idempotent per-tick mirror
    (``HealthReporter.sync_calibration_available_issue``) hidden for good.
    Apply writes the option over the OPTIONS path, so the update listener
    hot-applies it like any options submit.
    """

    def __init__(self, hass: HomeAssistant, data: dict[str, Any]) -> None:
        self._hass = hass
        self._data = data

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        if user_input is not None:
            entry = self._hass.config_entries.async_get_entry(self._data["entry_id"])
            if entry is not None:
                options = dict(entry.options)
                options[CONF_TRV_CALIBRATION] = True
                self._hass.config_entries.async_update_entry(entry, options=options)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """HA repairs hook — the three L2 suggestion kinds plus the P1.5 opt-in."""
    if (data or {}).get("kind") == "trv_calibration":
        schema = vol.Schema(
            {
                vol.Required("entry_id"): str,
                vol.Required("kind"): "trv_calibration",
            },
            extra=vol.ALLOW_EXTRA,
        )
        return CalibrationOptInFixFlow(hass, schema(data or {}))
    schema = vol.Schema(
        {
            vol.Required("entry_id"): str,
            vol.Required("kind"): vol.In(
                ["comfort_base", "comfort_earlier", "clo_offset"]
            ),
            vol.Required("direction"): vol.In([1, -1]),
            vol.Required("key"): str,
        },
        extra=vol.ALLOW_EXTRA,
    )
    return OverrideSuggestionFixFlow(hass, schema(data or {}))
