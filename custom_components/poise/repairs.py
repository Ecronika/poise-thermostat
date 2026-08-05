"""Repairs platform — the ADR-0060 L2 suggestion fix flow (apply / dismiss).

The coordinator mirrors a detected override pattern into a fixable issue
(``_sync_suggestion_issue``); this flow is the visible decision point the ADR
mandates: **apply** performs the config write over the Reconfigure path
(``async_update_entry`` — never a silent store mutation), **dismiss** stamps
the 30-day suppression for exactly this pattern key. Both paths also stamp the
cool-down after an APPLY, because the old evidence stays in the L1 statistic
and would otherwise immediately re-raise the just-applied pattern.
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
)
from .control.feedback import CLO_SUGGEST_STEP
from .control.suggestion import SUGGEST_EARLIER_MIN, SUGGEST_STEP_K

# The comfort-base write stays inside the options-flow selector range; the
# engine's norm envelope (ADR-0027/0035) clamps further at runtime.
_BASE_MIN_C = 16.0
_BASE_MAX_C = 26.0


class OverrideSuggestionFixFlow(RepairsFlow):
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


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """HA repairs hook — every fixable Poise issue today is an L2 suggestion."""
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
