"""AR-46 — the disable/unload quiescence race (review 2026-08-26, CI-only).

Before the fix, ``async_unload_entry``'s room path ran the final save and the
actuator park while the coordinator's input listeners were still attached and
the ``DataUpdateCoordinator`` was not shut down (both are ``on_unload``
callbacks, which HA runs only AFTER ``async_unload_entry`` returns). The
park's own actuator writes then fired the state listener ->
``async_request_refresh()`` -> one last REAL tick of the dying instance,
which could re-write setpoint/mode against the park and — on the live
calibration path — even a fresh offset AFTER the store's calibration
ownership was cleaned. ``PoiseCoordinator.async_quiesce`` (detach listeners
-> ``async_shutdown`` -> tick-lock drain) now runs as the FIRST step of the
room unload path, mirroring the hub's AR-02 tick-cancel.

COUNTERFACTUAL (why this test fails without the fix): remove the
``await entry.runtime_data.async_quiesce()`` call from ``async_unload_entry``
and the mid-park actuator state change in ``_poking_park`` reaches the still-
attached listener; the listener requests a refresh, the (not shut down)
debouncer executes it immediately, and ``_async_update_data`` of the old
instance runs — the ``assert ticks == ticks_before_disable`` below fails
(and ``listeners_at_park`` is not ``None``). With the fix, the listener is
detached and the coordinator shut down before any teardown I/O, so nothing
the park does can start a tick.

Harness: the real disable path via ``async_set_disabled_by`` (pattern of
``test_review_ar_coverage``), the registry TRV device with a calibration
number (pattern of ``test_p1_calibration_stage``).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryDisabler
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
    CONF_TRV_CALIBRATION,
    DOMAIN,
)
from custom_components.poise.storage import PoiseStore

TRV = "climate.trv"
CAL = "number.trv_local_temperature_calibration"
ENTRY_ID = "arq46001"


def _register_trv_device(hass: HomeAssistant) -> None:
    """Registry TRV device owning the actuator + its calibration number."""
    dev_entry = MockConfigEntry(domain="demo", title="TRV Device")
    dev_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=dev_entry.entry_id, identifiers={("demo", "trv1")}
    )
    ent_reg = er.async_get(hass)

    def _reg(domain: str, obj: str, uid: str) -> str:
        return ent_reg.async_get_or_create(
            domain,
            "demo",
            uid,
            config_entry=dev_entry,
            device_id=device.id,
            suggested_object_id=obj,
        ).entity_id

    assert _reg("climate", "trv", "act") == TRV
    assert _reg("number", "trv_local_temperature_calibration", "cal") == CAL


async def test_disable_is_quiescent_before_park_and_final_save(
    hass: HomeAssistant,
) -> None:
    """AR-46: during the disable teardown NO tick of the old instance runs.

    A watched-actuator state change fired mid-park (standing in for the
    park's own write echo) must be inert: the listener is already detached
    and the coordinator already shut down BEFORE the final save / calibration
    restore / park I/O. Without ``async_quiesce`` in the unload path the tick
    counter below increments (see the module docstring's counterfactual).
    """
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "number", "set_value")
    _register_trv_device(hass)
    hass.states.async_set("sensor.room_temp", "19.0", {"device_class": "temperature"})
    hass.states.async_set(
        TRV,
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 20.0,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set(CAL, "0.0", {"min": -5.0, "max": 5.0, "step": 0.5})
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TRV,
        entry_id=ENTRY_ID,
        data={
            CONF_NAME: "AR46 Room",
            CONF_TEMP_SENSOR: "sensor.room_temp",
            CONF_ACTUATOR: TRV,
            CONF_CATEGORY: "II",
            CONF_COMFORT_BASE: 21.0,
            CONF_CLIMATE_MODE: "auto",
            CONF_COMFORT_WEIGHT: 70,
            CONF_SETBACK_DELTA: 3.0,
            CONF_OPTIMAL_START: False,
            CONF_OPERATIVE_INPUT: False,
            CONF_CONTROLS_BOILER: False,
            CONF_TRV_CALIBRATION: True,
        },
        title="AR46 Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data

    # Calibration ownership + the teardown-park gate, as a previous live run
    # left them; the number reports exactly the baseline, so the teardown
    # restore confirms state-based without a dispatch.
    coord.runtime.actuator.has_actuated = True
    coord.runtime.actuator.cal_baseline = 0.0
    coord.runtime.actuator.cal_entity = CAL

    # Tick counter: entered on EVERY real tick of this instance.
    ticks = 0
    orig_update = coord._async_update_data

    async def _counting_update() -> dict[str, Any]:
        nonlocal ticks
        ticks += 1
        return await orig_update()

    coord._async_update_data = _counting_update  # instance attr shadows method
    ticks_before_disable = ticks
    writes_before_disable = len(set_temp)
    listeners_at_park: object = "park never ran"

    async def _poking_park(*args: object, **kwargs: object) -> None:
        """Stand-in for the park I/O: fire the write echo the real park's
        blocking service calls produce, then yield so a (wrongly) triggered
        listener/refresh task would get to run before the unload returns."""
        nonlocal listeners_at_park
        listeners_at_park = coord._unsub_listeners
        hass.states.async_set(
            TRV,
            "off",
            {
                "hvac_modes": ["heat", "off"],
                "temperature": 18.0,
                "current_temperature": 20.0,
                "target_temp_step": 0.5,
                "min_temp": 5,
                "max_temp": 30,
            },
        )
        # Deliberately NOT async_block_till_done (the unload itself may be a
        # tracked task); 50 loop passes are ample for the listener -> refresh
        # -> _async_update_data chain to at least ENTER the counting wrapper.
        for _ in range(50):
            await asyncio.sleep(0)

    with patch(
        "custom_components.poise.ha.actuator_lifecycle.execute_park",
        side_effect=_poking_park,
    ) as park:
        await hass.config_entries.async_set_disabled_by(
            entry.entry_id, ConfigEntryDisabler.USER
        )
        await hass.async_block_till_done()

    # The park ran (disable leg, AR-03) — and by then the listeners were
    # already detached: quiesce ordered BEFORE the teardown I/O.
    assert park.call_count == 1
    assert listeners_at_park is None
    # THE race assertion: no tick of the old instance ran during teardown,
    # and no actuator write beyond the (patched-out) park's own.
    assert ticks == ticks_before_disable
    assert len(set_temp) == writes_before_disable
    # The final save + teardown restore cleaned the calibration ownership in
    # the store, and nothing re-wrote it afterwards.
    stored = await PoiseStore(hass, ENTRY_ID).load() or {}
    assert stored.get("cal_baseline") is None
    assert stored.get("cal_entity") is None

    # Belt and braces (passes with on_unload detach alone, so NOT the
    # load-bearing assertion): a post-unload actuator change stays inert too.
    hass.states.async_set(
        TRV,
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 18.0,
            "current_temperature": 19.5,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    await hass.async_block_till_done()
    assert ticks == ticks_before_disable
