"""P2 audit bundle — glue regressions (R5, R9).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips
these at collection. The pure logic each finding rests on is pinned separately in
``tests/test_p2_pure.py`` and ``tests/test_p2_valve_harness.py``; here we pin the
coordinator wiring that only a real entity graph can exercise.

R9 — a mid-dry latch survives a restart: ``_save_payload`` persists ``dry_active``
and ``async_bootstrap`` restores it, so a humid room that had already entered the
dry cycle does not silently drop it (and re-thrash the compressor min-off) on the
first tick after HA restarts.

R5 — the auto-detected direct valve stays shadow-only: a device whose sibling
``number.*_valve_opening_degree`` is picked up by the device-guard must NOT be
written during a normal control tick. Live valve actuation is gated on cold-season
validation (README roadmap); today only ``tpi_valve_percent`` is *published*. This
is the safety guard that keeps that promise honest.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)
from custom_components.poise.storage import STORAGE_VERSION

# --------------------------------------------------------------- R9 --

R9_ENTRY = "p2dry"


def _room(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        **extra,
    }


def _set_ac(hass: HomeAssistant, *, room: float = 24.0) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "dry", "fan_only", "off"],
            "temperature": 24.0,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 30,
        },
    )


def _seed(hass_storage: dict[str, Any], **payload: Any) -> None:
    # ``async_bootstrap`` gates the restore on ``"ekf" in data`` (see the B5
    # baseline test), so the empty ekf dict is load-bearing, not decoration.
    hass_storage[f"{DOMAIN}_{R9_ENTRY}_ekf"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}_{R9_ENTRY}_ekf",
        "data": {"ekf": {}, "enabled": True, **payload},
    }


async def _setup_room(hass: HomeAssistant, **extra: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        entry_id=R9_ENTRY,
        data=_room(**extra),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_dry_active_persist_and_restore_wiring(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """R9: the dry latch is persisted by ``_save_payload`` and restored by
    ``async_bootstrap``.

    Setup runs bootstrap against a seeded latch, exercising the restore branch.
    The *post-tick* ``_dry_active`` is recomputed from live RH every tick (the
    restored value only feeds ``prev_dry_active`` into the next tick's
    hysteresis, which the pure humidity tests pin), so it is deliberately NOT
    asserted here -- the deterministic check is the ``_save_payload`` round-trip,
    the persist half the finding adds.
    """
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _seed(hass_storage, dry_active=True)  # exercises the async_bootstrap restore
    _set_ac(hass)

    entry = await _setup_room(hass)
    coord = entry.runtime_data

    coord._dry_active = True
    assert coord._save_payload()["dry_active"] is True
    coord._dry_active = False
    assert coord._save_payload()["dry_active"] is False


# --------------------------------------------------------------- R5 --


async def test_autodetected_valve_is_never_written(hass: HomeAssistant) -> None:
    """R5: the sibling valve-open ``number`` is detected but shadow-only.

    A normal control tick must not call ``number.set_value`` on it -- direct valve
    actuation is roadmap-gated. We register the mock service and assert no call
    ever targets the valve entity, while confirming the guard actually resolved it
    (otherwise the assertion would pass vacuously)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    number_calls = async_mock_service(hass, "number", "set_value")

    dev_entry = MockConfigEntry(domain="demo", title="TRV Device")
    dev_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=dev_entry.entry_id, identifiers={("demo", "trv1")}
    )
    ent_reg = er.async_get(hass)

    def _reg(domain: str, obj: str, uid: str, **kw: Any) -> str:
        return ent_reg.async_get_or_create(
            domain,
            "demo",
            uid,
            config_entry=dev_entry,
            device_id=device.id,
            suggested_object_id=obj,
            **kw,
        ).entity_id

    act = _reg("climate", "trv", "act")
    valve = _reg("number", "trv_valve_opening_degree", "valve")

    hass.states.async_set("sensor.room_temp", "19.0", {"device_class": "temperature"})
    hass.states.async_set(
        act,
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 18.0,
            "current_temperature": 19.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set(valve, "0", {"unit_of_measurement": "%"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=act,
        data=_room(**{CONF_ACTUATOR: act}),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # the device-guard resolved the sibling valve (test is meaningful) ...
    assert entry.runtime_data._valve_entity == valve
    # ... but no tick wrote it.
    assert all(c.data.get("entity_id") != valve for c in number_calls)
