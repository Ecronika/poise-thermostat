"""Phase 8 (S3) — presenter contract pins for ``ha/presenter.py``.

Two deliverables of the S3 presenter split (plan phase 8, "Kompatibilitätstest
gegen ``_ATTRS``" + the 6a-S1 object-identity chain):

* **``_ATTRS`` compatibility** — the entity platforms select their published
  attributes via ``data.get`` over tuples that must stay serveable:
  ``climate._ATTRS`` selects from the ZONE coordinator payload (the 156-key
  ``EXPECTED_AVAILABLE_KEYS`` snapshot of ``test_phase0_data_contract``);
  ``binary_sensor._ATTRS`` selects from the HUB coordinator payload (a
  different coordinator — its keys are deliberately NOT in the zone
  snapshot). Both subset relations are pinned mechanically, so a key rename
  in either payload assembly can no longer silently blank an entity
  attribute (``data.get`` would just return ``None``).

* **Object identity of the available form** (binding, 6a-S1 aliasing): the
  presenter returns ``outcome.diagnostics`` AS THE SAME OBJECT the finalize
  assembly built and the trace consumed, and ``_async_update_data`` attaches
  ``tick_ms*`` onto that same object. The chain
  ``_tick_data`` ≡ trace input ≡ ``coordinator.data`` is what keeps the
  published payload byte-identical to the traced one; a presenter that
  copies or rebuilds the dict would pass every key/value test and still
  break it — only an ``is`` pin catches that.

The key-SHRINK behaviour of the available form (phase-0 finding 3) is already
pinned by ``test_phase0_fault_shadow_domain``/``test_phase0_fault_climate_domain``
and the exact unavailable minimal forms by ``test_phase0_data_contract`` —
not duplicated here.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.binary_sensor import _ATTRS as HUB_ATTRS
from custom_components.poise.climate import _ATTRS as CLIMATE_ATTRS
from custom_components.poise.const import (
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from tests.integration.test_phase0_data_contract import (
    EXPECTED_AVAILABLE_KEYS,
    _FakeClock,
    _set_room,
    _setup,
)


def test_climate_attrs_are_subset_of_the_available_key_snapshot() -> None:
    """Every attribute key the climate entity publishes exists in the frozen
    156-key available-form snapshot — the presenter's served key set covers
    the entity surface (a drift shows up here BEFORE it blanks an attribute)."""
    missing = sorted(set(CLIMATE_ATTRS) - set(EXPECTED_AVAILABLE_KEYS))
    assert not missing, (
        "climate._ATTRS keys not served by the available payload "
        f"(entity attributes would silently read None): {missing}"
    )


def test_climate_attrs_do_not_claim_hub_or_minimal_keys() -> None:
    """Sanity for the subset pin: the zone entity tuple names none of the
    hub-owned keys and not the ``unavailable_safe`` marker — the two payload
    contracts stay disjoint surfaces."""
    assert not set(CLIMATE_ATTRS) & set(HUB_ATTRS)
    assert "unavailable_safe" not in CLIMATE_ATTRS


async def test_binary_sensor_attrs_are_subset_of_the_hub_payload(
    hass: HomeAssistant,
) -> None:
    """Every attribute key the hub binary_sensor publishes exists in the hub
    coordinator's payload (its own data contract, distinct from the zone
    snapshot — all 16 keys are hub-assembled, none appear in the zone form)."""
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_COUNT_THRESHOLD: 1,
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    data = hub.runtime_data.data
    assert data is not None
    missing = sorted(set(HUB_ATTRS) - set(data))
    assert not missing, (
        "binary_sensor._ATTRS keys not served by the hub payload "
        f"(entity attributes would silently read None): {missing}"
    )
    # and none of them leaked into the zone snapshot (hub-owned surface)
    assert not set(HUB_ATTRS) & set(EXPECTED_AVAILABLE_KEYS)


async def test_available_payload_is_the_traced_object(hass: HomeAssistant) -> None:
    """6a-S1 identity chain, end to end: the dict handed to the trace step is
    the SAME object ``coordinator.data`` publishes, and the ``tick_ms*``
    attach in ``_async_update_data`` lands on that same object (the trace-side
    reference sees the keys appear)."""
    _set_room(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord._clock = _FakeClock(1000.0)

    captured: list[dict[str, Any]] = []
    orig = coord._maybe_record_trace

    async def _spy(data: dict[str, Any], **kwargs: Any) -> None:
        captured.append(data)
        await orig(data, **kwargs)

    coord._maybe_record_trace = _spy
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.last_update_success is True
    assert coord.data["available"] is True
    assert len(captured) == 1
    # the identity pin: no copy, no rebuild — the traced dict IS the payload
    assert captured[0] is coord.data
    # the timing attach ran AFTER the trace append, on the same object:
    # the trace-side reference gained the tick_ms* keys
    assert "tick_ms" in captured[0]
    assert "tick_over_budget" in captured[0]
