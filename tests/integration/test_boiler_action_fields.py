"""Structured boiler actions in the hub config flow (roadmap 6 / ADR-0039).

The two boiler actions are no longer typed as ``entity_id/domain.service`` free
text: the form renders an ``ObjectSelector`` with declared fields (entity picker
+ service + optional service data) and stores that mapping. Entries created
before still carry the free-text spec, so BOTH forms have to keep working —
these tests pin that contract at the flow boundary.

Kept in a file of its own (rather than appended to ``test_config_flow.py``) so
the change stays reviewable next to the parallel work in that file.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import selector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poise.config_flow import _validate_boiler_actions
from custom_components.poise.config_schema import _system_schema
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)

ON_FIELDS: dict[str, Any] = {
    "entity_id": "switch.boiler",
    "action": "switch.turn_on",
}
OFF_FIELDS: dict[str, Any] = {
    "entity_id": "switch.boiler",
    "action": "switch.turn_off",
}


def _add_room(hass: HomeAssistant) -> None:
    """AR-30: the 'system' menu entry only appears once a room entry exists."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.existing",
        data={
            CONF_NAME: "Test Room",
            CONF_TEMP_SENSOR: "sensor.room_temp",
            CONF_ACTUATOR: "climate.trv",
        },
        title="Existing Room",
    ).add_to_hass(hass)


def _add_hub(hass: HomeAssistant, **extra: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, **extra},
        title="Poise System",
    )
    entry.add_to_hass(hass)
    return entry


async def _open_system_step(hass: HomeAssistant) -> Any:
    _add_room(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "system"}
    )


def _suggested(schema: vol.Schema, key: str) -> Any:
    """The suggested value HA rendered for ``key`` (None when the key is gone)."""
    for marker in schema.schema:
        if marker == key:
            description = getattr(marker, "description", None) or {}
            return description.get("suggested_value")
    return None


def test_boiler_actions_use_a_field_editor_not_free_text() -> None:
    """The selector is the structured one, with an entity picker among its
    fields — a plain TextSelector would put the slash syntax back on the user."""
    schema = _system_schema().schema
    for key in (CONF_BOILER_ON_ACTION, CONF_BOILER_OFF_ACTION):
        sel = next(v for k, v in schema.items() if k == key)
        assert isinstance(sel, selector.ObjectSelector)
        fields = sel.config["fields"]
        assert set(fields) == {"entity_id", "action", "data"}
        # Only the selector TYPE is pinned: from HA 2026.x the nested configs
        # are schema-validated and come back with their defaults filled in.
        assert set(fields["entity_id"]["selector"]) == {"entity"}
        assert fields["entity_id"]["required"] is True
        assert fields["action"]["required"] is True
        # A free-text service stays possible: HA has no service selector, so the
        # curated list must not become a cage.
        assert fields["action"]["selector"]["select"]["custom_value"] is True
        assert sel.config["translation_key"] == "boiler_action"


async def test_system_setup_accepts_structured_actions(hass: HomeAssistant) -> None:
    """Field input is stored verbatim as a mapping — the hub parses it."""
    result = await _open_system_step(hass)
    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BOILER_ON_ACTION: ON_FIELDS, CONF_BOILER_OFF_ACTION: OFF_FIELDS},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BOILER_ON_ACTION] == ON_FIELDS
    assert result["data"][CONF_BOILER_OFF_ACTION] == OFF_FIELDS


def test_validate_boiler_actions_covers_both_stored_forms() -> None:
    """Called directly, because WHICH layer catches a bad action is HA-version
    dependent: from HA 2026 the object selector validates its declared fields
    itself (a missing entity or service never reaches the flow), while on the
    supported MINIMUM (2025.10) it hands anything through and this function is
    the only check. A legacy free-text spec is still accepted here — the hub
    reads that form from entries created before the field editor."""
    assert _validate_boiler_actions({}) == {}
    assert _validate_boiler_actions({CONF_BOILER_ON_ACTION: ""}) == {}
    assert _validate_boiler_actions({CONF_BOILER_ON_ACTION: ON_FIELDS}) == {}
    assert (
        _validate_boiler_actions(
            {CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off"}
        )
        == {}
    )
    # Free-text typo -> the free-text message (that form has no fields to name).
    assert _validate_boiler_actions({CONF_BOILER_ON_ACTION: "typo"}) == {
        "base": "invalid_boiler_action"
    }
    # Structured but unusable -> the field message ("use the slash format"
    # would be wrong advice for a form that has no slash in it).
    assert _validate_boiler_actions({CONF_BOILER_ON_ACTION: {"action": "x.y"}}) == {
        "base": "invalid_boiler_action_fields"
    }


async def test_system_setup_rejects_unusable_structured_action(
    hass: HomeAssistant,
) -> None:
    """A service that is not ``domain.service`` passes the selector (the action
    field is a combobox with a free-text escape) and must be caught by the flow."""
    result = await _open_system_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_BOILER_ON_ACTION: {
                "entity_id": "switch.boiler",
                "action": "turn_on",  # no domain
            }
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_boiler_action_fields"}


async def test_hub_reconfigure_prefills_legacy_spec_as_fields(
    hass: HomeAssistant,
) -> None:
    """A pre-existing free-text entry opens in the field editor, decomposed
    losslessly — including the ``attr:value`` extras."""
    legacy_on = "climate.boiler/climate.set_hvac_mode/hvac_mode:heat"
    entry = _add_hub(
        hass,
        **{
            CONF_BOILER_ON_ACTION: legacy_on,
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",
        },
    )

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert _suggested(result["data_schema"], CONF_BOILER_ON_ACTION) == {
        "entity_id": "climate.boiler",
        "action": "climate.set_hvac_mode",
        "data": {"hvac_mode": "heat"},
    }
    assert _suggested(result["data_schema"], CONF_BOILER_OFF_ACTION) == OFF_FIELDS


async def test_hub_reconfigure_prefill_drops_unusable_and_absent_actions(
    hass: HomeAssistant,
) -> None:
    """An unparseable stored value is already inert, so it is not pre-filled;
    an action that was never configured simply stays empty."""
    entry = _add_hub(hass, **{CONF_BOILER_ON_ACTION: "left over from a typo"})

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)

    assert _suggested(result["data_schema"], CONF_BOILER_ON_ACTION) is None
    assert _suggested(result["data_schema"], CONF_BOILER_OFF_ACTION) is None


async def test_hub_reconfigure_normalizes_a_legacy_entry_on_submit(
    hass: HomeAssistant,
) -> None:
    """No store migration is needed: reconfiguring a legacy entry writes the
    structured form back, and the entry keeps working either way."""
    entry = _add_hub(hass, **{CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on"})

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BOILER_ON_ACTION: ON_FIELDS, CONF_BOILER_OFF_ACTION: OFF_FIELDS},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BOILER_ON_ACTION] == ON_FIELDS
    assert entry.data[CONF_BOILER_OFF_ACTION] == OFF_FIELDS


async def test_hub_still_actuates_from_a_legacy_free_text_entry(
    hass: HomeAssistant,
) -> None:
    """The unmigrated store stays live: a hub whose entry carries the free-text
    spec must still resolve BOTH actions and count as actuating."""
    from custom_components.poise.control.hub_aggregate import parse_service_action

    entry = _add_hub(
        hass,
        **{
            CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on",
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",
        },
    )
    on = parse_service_action(entry.data[CONF_BOILER_ON_ACTION])
    off = parse_service_action(entry.data[CONF_BOILER_OFF_ACTION])
    assert on is not None and off is not None
    assert (on.domain, on.service) == ("switch", "turn_on")
    assert off.data["entity_id"] == "switch.boiler"
