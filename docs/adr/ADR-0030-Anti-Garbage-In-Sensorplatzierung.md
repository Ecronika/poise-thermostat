# ADR-0030: Anti-Garbage-In — Erkennung falscher Sensorplatzierung

**Status:** akzeptiert · **Datum:** 2026-06-20 · **Bezug:** Charta G17 („schlechte Sensorik wird erkannt, nicht geglaubt"), ADR-0002/0024 (EKF), ADR-0012 (Repair-Issues), externe Review #2 · **Verifizierung:** EKF-`tau_hours`/`identified`

## Kontext
Das ganze Lernmodell hängt an einem **gut platzierten, freistehenden** Raumsensor. Nutzt jemand den **eingebauten TRV-Sensor** (am Heizkörper), reagiert die Messtemperatur fast sofort auf Heizen → das 1R1C-Modell lernt eine unplausibel kurze Zeitkonstante und der ganze Komfort/Vorhersage-Stack degradiert („Garbage In"). Das ist der laut Review kritischste Massentauglichkeits-Fallstrick.

## Entscheidung
1. **Pure Detektor** `safety/sensor_watchdog.sensor_at_heat_source(tau_hours, identified, min_plausible_tau_h)`: `identified ∧ tau < Schwelle`. Gated auf `identified`, damit nur eine **vertrauenswürdige** Schätzung beurteilt wird (keine Fehlalarme während des Lernens). Schwelle `MIN_PLAUSIBLE_TAU_H = 1.0 h` — reale Räume liegen bei Stunden, ein Heizquellen-Sensor bei Minuten; konservativ unter jeder realen Raum-τ (auch kleine Bäder ~1,5–2 h).
2. **Coordinator:** Repair-Issue `sensor_at_heat_source` (mit Sensor-Entity), Attribut `sensor_placement_suspect`. Rein beratend — keine Regeländerung.
3. **Onboarding-Hinweis:** `data_description.temp_sensor` im Config-Flow („freistehender Sensor, NICHT der eingebaute TRV-/Thermostat-Sensor").

## Begründung
Nutzt die bereits gelernte `tau` (kein neuer Schätzer) und die bestehende Repair-Issue-Infrastruktur. Saisonunabhängig nur insoweit, als `identified` erreicht sein muss (echte Heizzyklen) — der Detektor schlägt also genau dann an, wenn das Modell reif genug ist, um die Fehlplatzierung sicher zu erkennen. Alleinstellung: kein Wettbewerber prüft die Sensorplatzierung physikalisch.

## Konsequenzen
**Positiv:** verhindert das „kaputt gelernte" Raummodell, reduziert Frust/Support (Review-Ziel); proaktiver Onboarding-Hinweis. **Negativ/Offen:** (a) greift erst nach EKF-Identifikation (kalte Saison) — für die Sofort-Prävention dient der Onboarding-Text; (b) Schwelle fix konservativ, ggf. später konfigurierbar; (c) sehr untypische Räume (winziges, schlecht gedämmtes Bad mit Heizkörper) könnten theoretisch nahe an die Schwelle kommen — 1,0 h hält dafür Sicherheitsabstand.
