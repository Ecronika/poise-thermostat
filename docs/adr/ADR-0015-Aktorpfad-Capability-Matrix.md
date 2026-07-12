# ADR-0015: Aktorpfad-Capability-Matrix & coef_ext

**Status:** In Arbeit (70 %) · **Datum:** 2026-06-18 · **Bezug:** E12, E21, K7 · **Verifizierung:** Code-Review ThermoSmart/BT (Thema K)

> **Nachtrag (2026-06-22):** Der Ausschluss von `valve_opening_degree` in §1 der Entscheidung ist durch **ADR-0036** überholt. Recherche (Zigbee2MQTT, Versatile Thermostat, HA-Community) hat gezeigt, dass `valve_opening_degree` (Sonoff TRVZB, FW ≥ 1.1.4) eine **schreibbare Live-Open-Position (0–100 %)** ist, kein Max-Limit — der schreibbare Ventilöffnungs-Pfad wurde daraufhin für den Sonoff TRVZB übernommen. `valve_closing_degree` bleibt ausgeschlossen (Firmware-Bug). Maßgeblich ist der Code: `valve_opening_degree` steht in `AUTO_VALVE_PATTERNS` in `devices/capability.py`.

## Kontext
ADR-0004 verlangt einen **exklusiven** Aktorpfad je Gerät (tpi / kalibrierung / pi). Offen: wie die Gerätefähigkeit erkannt wird und wie `coef_ext` final behandelt wird.

## Entscheidungstreiber
Eindeutige, robuste Pfadwahl ohne Stapelung (K7); Umgang mit Geräte-Eigenheiten; keine Fehlsteuerung durch falsch interpretierte Entities.

## Befund am Code (Belege)
- **ThermoSmart** (`trv_control.py`): Pattern-Matching gegen `number.*` mit `AUTO_VALVE_PATTERNS = ["valve_position","pi_heating_demand","heating_demand","level"]`; **`valve_opening_degree` bewusst ausgeschlossen** (`const.py`: auf TRVZB ein **Max-Limit**, keine Live-Position — „writing TPI duty caps heating capacity instead of modulating"). Kalibrierung: `AUTO_CALIBRATION_PATTERNS`. Fallback: `set_temperature`. HVAC-Tauglichkeit über `hvac_modes`-Check + Profil-Flag.
- **Better Thermostat:** Adapter-Probe `{support_offset, support_valve}`; `find_valve_entity` **scort** `valve_opening_degree:100 > valve_position:90 > pi_heating_demand:80` (+10 writable). **Divergenz:** BT scort `valve_opening_degree` am höchsten, ThermoSmart schließt es aus — gegensätzliche Gerätekenntnis.

## Entscheidung
**Exklusive Capability-Matrix, top-down, erste Treffer-Zeile gewinnt:**
1. **Direkte Ventilsteuerung** — schreibbare `number.*` mit **Live-Positions-Semantik** (`valve_position`/`pi_heating_demand`/`heating_demand`/`level`) **und** Profil ≠ `VALVE_MAX_LIMIT`. **`valve_opening_degree` ausgeschlossen** (ThermoSmarts Gerätekenntnis gewinnt die Divergenz gegen BT: es ist ein Max-Limit, keine Live-Position; es wird auf 100 % gesetzt, nicht moduliert).
2. **Offset-Kalibrierung** — kein Ventil-Helper, aber schreibbare Kalibrier-Entity **und** zuverlässiges `heat` in `hvac_modes`.
3. **PI-kompensierter Sollwert** — sonst jede `climate`-Entity mit `set_temperature` (Mode-Lock auf `heat`).

Primärer Diskriminator = Präsenz einer **schreibbaren** number-Entity mit Live-Semantik; **Geräteprofil/Modell** löst Mehrdeutigkeit (Profil-Override schlägt Namensheuristik). Pfade sind **nie gleichzeitig** aktiv.

**`coef_ext` (E21 final):** **konservativ aus dem EKF-Verlustterm ableiten**, **nicht** Versatiles fragile Kext-Umverteilung (nur Nahfeld `gap<1.0`, identifizierbarkeits-anfällig — V2) übernehmen. `coef_int` bleibt physikalischer Seed + Online-Nachführung (ADR-0004).

## Begründung
Die Top-down-Matrix mit „erste Zeile gewinnt" garantiert Exklusivität (K7). Die `valve_opening_degree`-Entscheidung zugunsten ThermoSmarts ist code-begründet: das Schreiben der TPI-Duty auf ein Max-Limit deckelt die Heizleistung statt zu modulieren — ein konkreter Fehlsteuerungs-Beleg. Die EKF-basierte `coef_ext`-Ableitung nutzt das ohnehin vorhandene Verlustmodell (ADR-0002) und vermeidet die belegte Identifizierbarkeitsschwäche.

## Konsequenzen
**Positiv:** eindeutige, fehlsteuerungsarme Pfadwahl; nutzt Gerätekenntnis (Profil) statt blinder Heuristik; stabile `coef_ext` ohne fragiles Zusatzlernen.
**Negativ/Kosten:** Profil-/Capability-Tabelle muss gepflegt werden (neue TRV-Modelle); Grenzfälle (Gerät mit mehreren schreibbaren number-Entities) brauchen eine klare Profil-Regel.

## Compliance
Erkennungslogik eigenständig; gerätespezifische Eigenheiten leben in der `model_fixes`/Profil-Schicht (ADR-0005), nicht im Regelkern (G29).

## Verknüpfungen
Konkretisiert ADR-0004 (Pfadwahl + coef_ext) und K7. Profil-Schicht = `devices/` aus ADR-0005. Capability-Erkennung gehört in den Config-Flow (ADR-0008).
