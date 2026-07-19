"""Phase 0 — Effect-Sequenz-Tests (Refactoring-Plan Befund 11), glue/CI-only.

Plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md, Phase-0-Punkt
"Effect-Sequenz-Tests (Befund 11)": die drei Effect-Sequenz-Semantiken des
Koordinator-Ticks werden hier als HEUTIGES Verhalten eingefroren, damit der
spaetere ``ActuatorExecutor`` sie EXAKT erhalten muss:

1. **Frost-Rescue** (``coordinator.py`` Z. 3270–3326): ZWEI getrennte trys
   (Nudge Z. 3287, Floor-Write Z. 3302) — "Nudge and write are INDEPENDENT"
   (Z. 3284–3285). Ein fehlgeschlagener ``climate.set_hvac_mode`` ueberspringt
   den Sicherheits-Setpoint-Write NICHT.
2. **Unavailable-Safe** (``_write_unavailable_safe_state``, Z. 1929–1986):
   EIN gemeinsames try (Z. 1958) um Mode- UND Setpoint-Write — ein
   Mode-Fehler ueberspringt den Setpoint-Write (F-SAFESEQ erst Phase 10).
3. **Ext-Temp Select/Feed** (ADR-0029, Z. 3191–3240): bedingte Sequenz —
   Select-Erfolg -> ``switched=True`` -> Feed in DIESEM Tick uebersprungen
   (das Geraet soll sich setzen); Select-Fehler -> Feed trotzdem.

Fehler-Injektion (wichtig): alle drei Service-Calls laufen mit
``blocking=False``. Ein via ``hass.services.async_register`` registrierter
Handler, der wirft, propagiert dabei NIE zum Aufrufer — HA faengt den Fehler
im Hintergrund-Task (``_run_service_call_catch_exceptions``). Der einzige
Weg, den jeweiligen ``await`` im Koordinator-try wirklich werfen zu lassen,
ist ein Dispatch-Fehler: ``ServiceNotFound`` wird synchron in ``async_call``
geworfen, bevor der Task erzeugt wird. Deshalb injizieren die Fehlerfaelle
den fehlenden Service (``hass.services.async_remove`` bzw. Select-Service
gar nicht erst registrieren) statt eines raising Handlers.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
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
    CONF_TRV_EXTERNAL_TEMP,
    DOMAIN,
    FROST_FLOOR_C,
    UNAVAILABLE_SAFE_AFTER_S,
)

EXT = "number.trv_external_temperature"
SELECT = "select.trv_sensor_mode"


class _FakeClock:
    """A monotonic clock whose value the test advances by hand."""

    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _base(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
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


def _actuator(
    hass: HomeAssistant,
    *,
    state: str,
    sp: float,
    modes: list[str],
    room: float = 18.0,
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": modes,
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, **extra: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_base(**extra), title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _trv_temps(calls: list[Any]) -> list[float]:
    return [
        c.data.get("temperature")
        for c in calls
        if c.data.get("entity_id") == "climate.trv"
    ]


# --- (1) Frost-Rescue: Nudge und Floor-Write sind UNABHAENGIG -----------------


async def test_frost_rescue_failed_mode_nudge_still_writes_floor(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Disabled Zone unter dem Frost-Floor, der Mode-Nudge schlaegt fehl
    (Service fehlt -> ServiceNotFound im try Z. 3287) — der Floor-Write im
    ZWEITEN, getrennten try (Z. 3302) wird TROTZDEM dispatcht."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, state="off", sp=5.0, modes=["heat", "off"])
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # Injektion: der Mode-Service verschwindet -> der Nudge-await wirft
    # synchron ServiceNotFound. (Ein registrierter Handler, der wirft, wuerde
    # bei blocking=False den try NIE erreichen — siehe Modul-Docstring.)
    hass.services.async_remove("climate", "set_hvac_mode")
    # Recorder NACH dem Setup re-armen (platform forward clobbert Vorab-Mocks).
    set_temp = async_mock_service(hass, "climate", "set_temperature")

    coord.set_enabled(False)
    await coord.async_refresh()
    await hass.async_block_till_done()

    # der Nudge wurde versucht und ist gescheitert ...
    assert "frost rescue nudge failed" in caplog.text
    # ... aber der Sicherheits-Floor-Write ging TROTZDEM raus
    temps = _trv_temps(set_temp)
    assert temps, "floor write must be dispatched despite the failed mode nudge"
    assert all(t >= FROST_FLOOR_C for t in temps)
    assert "frost rescue write failed" not in caplog.text
    assert coord.last_update_success is True  # der Tick ueberlebt beide Faelle


# --- (2) Unavailable-Safe: EIN gemeinsames try um Mode + Setpoint -------------


async def _to_unavailable_safe_edge(
    hass: HomeAssistant,
) -> tuple[MockConfigEntry, _FakeClock]:
    """Setup + Sensorausfall + einen Tick; die Uhr steht kurz VOR dem Timeout."""
    _actuator(hass, state="off", sp=5.0, modes=["heat", "off"])
    entry = await _setup(hass)
    coord: Any = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord._clock = clock
    hass.states.async_set("sensor.room_temp", "unavailable", {})
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord._unavailable_since == 1000.0  # Ausfall ab fake t0 gestempelt
    assert (coord.data or {}).get("available") is False
    return entry, clock


async def test_unavailable_safe_mode_failure_skips_setpoint_write(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Raumsensor unavailable + Timeout ueberschritten, der Mode-Write wirft
    (Service fehlt): das GEMEINSAME try (Z. 1958–1986) bricht ab, der
    Setpoint-Write (Z. 1969–1978) wird NICHT mehr ausgefuehrt."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    entry, clock = await _to_unavailable_safe_edge(hass)
    coord: Any = entry.runtime_data

    hass.services.async_remove("climate", "set_hvac_mode")  # Injektion (s. Docstring)
    set_temp = async_mock_service(hass, "climate", "set_temperature")  # re-arm

    clock.t = 1000.0 + UNAVAILABLE_SAFE_AFTER_S + 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert (coord.data or {}).get("unavailable_safe") is True  # Zweig erreicht
    assert "unavailable-safe write failed" in caplog.text  # Mode-Write warf
    # gemeinsames try: der Mode-Fehler hat den Setpoint-Write uebersprungen
    assert _trv_temps(set_temp) == []


async def test_unavailable_safe_success_writes_mode_and_setpoint(
    hass: HomeAssistant,
) -> None:
    """Gegenprobe: ohne Fehler dispatcht derselbe Zweig BEIDE Writes — den
    Mode-Nudge auf heat und den Floor-Setpoint (>= Frost-Floor, hier 7.0, da
    min_temp 5 unter dem Floor liegt)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    entry, clock = await _to_unavailable_safe_edge(hass)
    coord: Any = entry.runtime_data

    set_temp = async_mock_service(hass, "climate", "set_temperature")  # re-arm
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")

    clock.t = 1000.0 + UNAVAILABLE_SAFE_AFTER_S + 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert (coord.data or {}).get("unavailable_safe") is True
    modes = [
        c.data.get("hvac_mode")
        for c in set_mode
        if c.data.get("entity_id") == "climate.trv"
    ]
    assert "heat" in modes  # Mode-Nudge dispatcht ...
    temps = _trv_temps(set_temp)
    assert temps and all(t == FROST_FLOOR_C for t in temps)  # ... und der Floor auch


# --- (3) Ext-Temp Select/Feed: bedingte Sequenz (ADR-0029) --------------------


def _room_with_ext(hass: HomeAssistant, *, room: float = 20.0) -> None:
    _actuator(hass, state="heat", sp=21.0, modes=["heat", "off"], room=room)
    # plausible External-Temp-Number (device_class temperature), damit die
    # F2-Validierung den konfigurierten Feed behaelt.
    hass.states.async_set(EXT, "21", {"device_class": "temperature"})


async def _setup_feed_zone(hass: HomeAssistant) -> MockConfigEntry:
    """Zone mit External-Temp-Number + (nachtraeglich gepinntem) Sensor-Select.

    Die Select-Discovery laeuft ueber die Entity-Registry des Aktor-Devices
    (``_resolve_device_guards``, Z. 1255–1260); der Mock-Aktor hier hat kein
    Registry-Device, also wird ``_sensor_select`` direkt gepinnt — die
    Sequenz-Semantik unter Test (Z. 3193–3240) liest nur den State.
    ``_guards_resolved`` ist nach dem Setup-Tick True, der Pin bleibt stehen.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=_base(**{CONF_TRV_EXTERNAL_TEMP: EXT}),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord: Any = entry.runtime_data
    assert coord._trv_ext_temp == EXT  # von der F2-Validierung behalten
    coord._sensor_select = SELECT
    hass.states.async_set(SELECT, "internal", {"options": ["internal", "external"]})
    # Feed-Buchhaltung zuruecksetzen: ein Feed ist damit definitiv faellig,
    # ein ausbleibender Feed ist also eindeutig dem Select-Zweig zuzuordnen.
    coord._clock = _FakeClock(1000.0)
    coord._last_fed = None
    coord._last_fed_ts = 0.0
    return entry


def _feed_writes(calls: list[Any]) -> list[Any]:
    return [c for c in calls if c.data.get("entity_id") == EXT]


async def test_ext_select_success_skips_feed_this_tick(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Fall A: Select-State != 'external', select.select_option gelingt ->
    ``switched=True`` -> number.set_value wird in DIESEM Tick NICHT gerufen
    (Z. 3213: das Geraet soll sich erst setzen). Folgetick (Select steht auf
    'external'): der Feed laeuft normal."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_with_ext(hass, room=20.0)
    entry = await _setup_feed_zone(hass)
    coord: Any = entry.runtime_data
    select_calls = async_mock_service(hass, "select", "select_option")
    set_value = async_mock_service(hass, "number", "set_value")

    await coord.async_refresh()
    await hass.async_block_till_done()

    switches = [c for c in select_calls if c.data.get("entity_id") == SELECT]
    assert switches and all(c.data.get("option") == "external" for c in switches)
    assert "sensor-select switch failed" not in caplog.text
    assert _feed_writes(set_value) == []  # Feed im Switch-Tick uebersprungen

    # das Geraet folgt: Select meldet jetzt 'external' -> naechster Tick feedet
    hass.states.async_set(SELECT, "external", {"options": ["internal", "external"]})
    coord._clock.t += 30.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    feeds = _feed_writes(set_value)
    assert feeds and feeds[-1].data["value"] == 20.0


async def test_ext_select_failure_feeds_anyway(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Fall B: select.select_option wirft (Service nie registriert ->
    ServiceNotFound im try Z. 3200–3212) -> ``switched`` bleibt False ->
    number.set_value wird TROTZDEM in diesem Tick gerufen."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_with_ext(hass, room=20.0)
    entry = await _setup_feed_zone(hass)
    coord: Any = entry.runtime_data
    # Injektion: KEIN select.select_option-Service (kein Select-Platform-Setup,
    # kein Mock) -> der Dispatch selbst wirft im Koordinator-try.
    assert not hass.services.has_service("select", "select_option")
    set_value = async_mock_service(hass, "number", "set_value")

    await coord.async_refresh()
    await hass.async_block_till_done()

    assert "sensor-select switch failed" in caplog.text  # Switch wurde versucht
    feeds = _feed_writes(set_value)
    assert feeds, "feed must still be dispatched when the select switch fails"
    assert feeds[-1].data["value"] == 20.0
