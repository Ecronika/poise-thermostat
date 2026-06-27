# ADR-0008: Config-Schema & Default-Herleitung

**Status:** In Arbeit (45 %) · **Datum:** 2026-06-18 · **Bezug:** E10, E11, G16, G19 · **Verifizierung:** Code-Review Vesta/ThermoSmart/Versatile/RoomMind/BT (Thema D)

## Kontext
Charta-Ziel ist ein „Zero-Question-Default"-Onboarding mit Progressive Disclosure (G19) und begründeten Defaults (G16/E11). Offen: Flow-Struktur, Auto-Discovery, Vererbung, Default-Herleitung.

## Entscheidungstreiber
Minimale Erst-Abfragen; automatische Erkennung vor manueller Eingabe; abrufbare Tiefe; jeder Default begründet und sicher.

## Befund am Code (Belege)
- **RoomMind:** **Zero-Question-Hub** — Single-Step (`async_step_user`, `data={}`, `_abort_if_unique_id_configured`); gesamte Raumkonfiguration über UI/WebSocket, nicht über den Flow.
- **Vesta:** **bestes Area-Auto-Discovery** — `_discover_entities_for_area` matcht Entities per `entry.area_id` **oder** Geräte-Area-Vererbung (`device.area_id`), filtert per `effective_dc = entry.device_class or entry.original_device_class` (Heater: climate/switch/water_heater; Temp: sensor+temperature; Fenster: binary_sensor+window), Ergebnis als `include_entities` → Nutzer sieht nur Raum-Entities.
- **Versatile:** **Central-Config-Vererbung** — `use_*_central_config`-Flags (alle `default=True`) je Feature; Merge in `base_thermostat.clean_central_config_doublon`: `entry_infos = central_config.data.copy(); entry_infos.update(cfg)` (Zentralwerte füllen Lücken, lokale überschreiben); `NoCentralConfig`-Validierung.
- **ThermoSmart:** 4-Schritt-Zonenflow (`add_zone→schedule→presence→weather`) + Cross-Field-Validierung (`night<comfort`, `away<=night`) + durchgängig `device_class`-gefilterte Selektoren + `_defaults_from_existing()`.
- **Defaults/Herleitung:** **RoomMind+BT** am besten — physikalische Startwerte mit Inline-Kommentar-Herleitung (`_DEFAULT_ALPHA=0.15 ~7h τ`, Bounds `_ALPHA_MIN=0.005 → 200h heavy building`) + **Profil-Tabelle `HEATING_SYSTEM_PROFILES`** (radiator/underfloor: `tau_minutes`, `initial_fraction`, `tau_charge_minutes`, `min_run_minutes`); Schimmel-Defaults `MOLD_SURFACE_RH_CRITICAL=80.0`. BT: `MIN_HEATING_POWER=0.005 (°C/min)` mit Kommentar.
- **Korrekturen:** ThermoSmart hat **keine** „typische-deutsche-Wohnung"-Heatrate-Tabelle (Heat-Rate gelernt) und **keine** Mold/DIN-Defaults (Frost=12 °C); Versatile hat **keine** `device_class`-Filter; Vesta-Defaults liegen inline im Flow, nicht in `const.py`.

## Entscheidung
1. **Einstieg = RoomMind-Zero-Question-Hub** (Single-Step, keine Pflichtfragen, Unique-ID-Abort).
2. **Auto-Discovery = Vesta** (`_discover_entities_for_area` mit Geräte-Area-Vererbung + `device_class || original_device_class`-Filter, `include_entities` in vorbelegte Selektoren) — Nutzer bestätigt statt zu suchen.
3. **Progressive Disclosure + Vererbung = Versatile** (globaler Central-Config-Entry mit `use_*_central_config`-Flags `default=True`; pro Raum nur Abweichungen; Merge `central.data.copy(); .update(local)`).
4. **Begründete Default-Herleitungstabelle = RoomMind+BT** (physikalische Startwerte mit Herleitungskommentar + **Profil-Tabelle** radiator/underfloor mit τ/min_run/charge als E11-Vorlage) — kein unbelegter Hardcode.
5. **Cross-Field-Validierung minimal** (ThermoSmart `night<comfort<…` + Vesta „Feature an ⇒ Entity erforderlich").

## Begründung
Jedes Element ist der am Code belegte Bestwert seiner Kategorie; zusammengesetzt ergeben sie genau das Charta-Ziel: leerer erster Schritt (RoomMind), automatische Raum-Vorauswahl (Vesta), Tiefe nur bei Bedarf (Versatile), nachvollziehbare sichere Defaults (RoomMind/BT). Die Profil-Tabelle ersetzt den (nicht existenten) ThermoSmart-Heatrate-Hardcode und verteidigt zugleich den eigenen Norm-/Operativtemperatur-Vorsprung.

## Konsequenzen
**Positiv:** niedrigste Adoptionsschwelle; korrektes Verhalten ohne jede Anpassung; Tiefe bleibt verfügbar; Defaults auditierbar.
**Negativ/Kosten:** Central-Config-Merge + Area-Discovery sind nicht trivial; die Default-Herleitungstabelle (E11) muss gepflegt werden; UI/WS-Konfiguration (RoomMind-Stil) ist Mehraufwand gegenüber reinem Flow.

## Compliance
Flow-/Discovery-/Vererbungsmuster allgemeingültig, eigenständig umgesetzt; generisch (keine geräte-/herstellerspezifischen Sonderwege im Kern).

## Verknüpfungen
Defaults speisen ADR-0009 (EKF-Startwerte/Bounds) und ADR-0004 (TPI-Seed); Profil-Tabelle berührt ADR-0003 (τ_charge/min_run). Persistenz/Migration der Config: ADR-0007.
