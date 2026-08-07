"""Glue tests for the ADR-0067 feedback channel and the suggestion fix flow.

Drives the two F1 buttons and the ``poise.comfort_feedback`` service the way a
user does and asserts the observe-only fold (accepted vs. masked); then drives
``repairs.OverrideSuggestionFixFlow`` directly (the flow object needs only the
manager-assigned ``flow_id``/``handler`` attributes stubbed) and asserts the
visible options writes, the clamps and the per-family cool-down routing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_CLO_OFFSET,
    CONF_COMFORT_BASE,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)
from custom_components.poise.repairs import (
    OverrideSuggestionFixFlow,
    async_create_fix_flow,
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


def _states(hass: HomeAssistant, *, room: float, sp: float) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup_zone(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# ---------------------------------------------------------------------------
# F1: buttons + service fold into the observe-only statistic
# ---------------------------------------------------------------------------


async def test_feedback_button_and_service_fold_or_mask(hass: HomeAssistant) -> None:
    """A clean press folds one event; an active hold masks the press (F1).

    Room 23 °C sits close to neutral for every clo the prior can assume
    (0.5..1.0), so the |PMV| <= 1 gate deterministically accepts; the second
    half activates a manual hold — the deterministic ``override_active`` mask.
    """
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=23.0, sp=22.5)
    entry = await _setup_zone(hass)
    user = entry.runtime_data.runtime.user
    assert user.feedback_stats == []

    # Button press ("too cold") -> one accepted event with the tick context.
    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: "button.test_room_too_cold"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(user.feedback_stats) == 1
    event = user.feedback_stats[0]
    assert event["direction"] == "cold"
    assert event["phase"] == "comfort"  # always_comfort schedule
    assert event["clo_used"] is not None

    # The service path is the automation/voice channel for the same fold.
    await hass.services.async_call(
        DOMAIN, "comfort_feedback", {"direction": "warm"}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(user.feedback_stats) == 2
    assert user.feedback_stats[-1]["direction"] == "warm"

    # An active manual hold masks further feedback (override_active).
    entry.runtime_data.set_override(23.0)
    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: "button.test_room_too_warm"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(user.feedback_stats) == 2  # discarded, not folded


# ---------------------------------------------------------------------------
# F2/L2: the suggestion fix flow (apply / dismiss)
# ---------------------------------------------------------------------------


async def _flow(hass: HomeAssistant, data: dict[str, Any]) -> OverrideSuggestionFixFlow:
    flow = await async_create_fix_flow(hass, "test_issue", data)
    # The repairs manager normally assigns these; stub them so the flow's
    # result dicts can be built when the flow object is driven directly.
    flow.hass = hass
    flow.flow_id = "test-flow"
    flow.handler = DOMAIN
    return flow  # type: ignore[return-value]


def _data(
    entry: MockConfigEntry, kind: str, direction: int, key: str
) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "kind": kind,
        "direction": direction,
        "key": key,
    }


async def test_fix_flow_menu_and_comfort_base_apply(hass: HomeAssistant) -> None:
    """Apply writes the base visibly (Reconfigure path) and stamps the L2 slot."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=18.0)
    entry = await _setup_zone(hass)

    flow = await _flow(hass, _data(entry, "comfort_base", 1, "comfort_base:+1"))
    menu = await flow.async_step_init(None)
    assert menu["type"] is FlowResultType.MENU
    assert set(menu["menu_options"]) == {"apply", "dismiss"}

    result = await flow.async_step_apply(None)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_COMFORT_BASE] == 21.5  # 21.0 + 0.5, visible write
    user = entry.runtime_data.runtime.user
    # The accept stamps the SAME cool-down as a rejection (old evidence must
    # not immediately re-raise the just-applied pattern).
    assert user.suggestion_rejected_key == "comfort_base:+1"
    assert user.suggestion_rejected_at is not None
    # Hot-applied onto the live coordinator, not just stored.
    assert entry.runtime_data._comfort_base == 21.5


async def test_fix_flow_clo_offset_apply_routes_its_own_slot(
    hass: HomeAssistant,
) -> None:
    """The clo family writes clo_offset and stamps ITS slot, never the L2 one."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=18.0)
    entry = await _setup_zone(hass)

    flow = await _flow(hass, _data(entry, "clo_offset", -1, "clo_offset:-1"))
    result = await flow.async_step_apply(None)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_CLO_OFFSET] == -0.1
    user = entry.runtime_data.runtime.user
    assert user.clo_suggestion_rejected_key == "clo_offset:-1"  # own slot
    assert user.suggestion_rejected_key is None  # L2 slot untouched


async def test_fix_flow_dismiss_only_stamps(hass: HomeAssistant) -> None:
    """Dismiss changes no option, it only mutes the pattern for 30 days."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=18.0)
    entry = await _setup_zone(hass)
    options_before = dict(entry.options)

    flow = await _flow(hass, _data(entry, "comfort_base", -1, "comfort_base:-1"))
    result = await flow.async_step_dismiss(None)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(entry.options) == options_before
    assert entry.runtime_data.runtime.user.suggestion_rejected_key == "comfort_base:-1"


async def test_fix_flow_comfort_earlier_apply_and_stale_fallback(
    hass: HomeAssistant,
) -> None:
    """With a window the start moves 30 min earlier; without one the apply
    degrades to the dismiss semantics (stale pattern, nothing to write)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=18.0)
    entry = await _setup_zone(hass)

    # No configured comfort window: apply falls through to dismiss semantics.
    flow = await _flow(hass, _data(entry, "comfort_earlier", 1, "comfort_earlier:+1"))
    result = await flow.async_step_apply(None)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_COMFORT_START not in entry.options
    user = entry.runtime_data.runtime.user
    assert user.suggestion_rejected_key == "comfort_earlier:+1"

    # With a configured window the start moves 30 minutes earlier.
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_COMFORT_START: "06:30"}
    )
    await hass.async_block_till_done()
    flow = await _flow(hass, _data(entry, "comfort_earlier", 1, "comfort_earlier:+1"))
    result = await flow.async_step_apply(None)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_COMFORT_START] == "06:00"
