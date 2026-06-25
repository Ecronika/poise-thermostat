# ADR-0023: Capability-aware Dual-Setpoint mit Totband

**Status:** akzeptiert · **Datum:** 2026-06-19 · **Bezug:** Livetest v0.6.0, ADR-0010/0016/0017 · **Verifizierung:** EN 16798-1 (Web), RoomMind/Versatile/BT-Code, eigenes Smart-Setpoint-Gist v5.3.1

## Kontext
Livetest: Poise setzte den Sollwert = adaptive Neutraltemperatur `0.33·T_rm+18.8` → 24 °C bei T_rm 15,7 — zu warm fürs Heizen, und es heizte einen bereits 23,5 °C warmen Raum. Ein **einzelner** geklemmter Sollwert ist falsch: er kann ein Nur-Kühlen-Gerät im Sommer an die untere Grenze zwingen (Energieverschwendung) und ignoriert die Gerätefähigkeit.

## Entscheidungstreiber
Normtreue (Heizen ≠ freilaufend); kein unnötiges Konditionieren; Gerätefähigkeit (heizen/kühlen/beides); Nutzer-Priorität Komfort↔Effizienz; harte Sicherheits-/Gesundheitsgrenzen.

## Befund (verifiziert)
- **EN 16798-1:** Auslegung nutzt **„den unteren Wert in der Heizsaison für das Heizsystem und den oberen Wert in der Kühlsaison für das Kühlsystem"** → **zwei getrennte Sollwerte** mit **neutralem Totband** dazwischen. Das Adaptivmodell gilt nur für *freilaufende* Gebäude (keine aktive Heizung/Kühlung).
- **RoomMind = Referenz:** `TargetTemps(heat,cool)` (Komfortkosten 0 im Band), `get_can_heat_cool()` aus `hvac_modes`+`climate_mode`, **symmetrisches Außen-Gating** (`heating_max=22` **und** `cooling_min=16` — „NEVER cool if outdoor < this") → Nur-Kühlen+kalt = idle, kein Heizen; Slider `comfort_weight`→`w_comfort/w_energy`+approach_rate.
- **Eigenes Gist:** löst die Sollwertwahl bereits gut (fester Profilwert ins Band, feste EN-Heiz/Kühl-Bänder Kat. II heat 20–24 / cool 23–26), **aber kein echtes Totband** (ein Sollwert je Richtung) und **kein Winter-Lockout** für Nur-Kühlgeräte.
- **Poise hat das Fundament:** `comfort/cooling.py` (`DualSetpoint`+`decide_mode` mit beidseitigem Gating) — nur nicht verdrahtet.

## Entscheidung
Die Comfort-Schicht liefert je Zone eine **`ComfortDecision`** statt eines Einzel-Sollwerts:
1. **Dual-Setpoint:** `heat_sp` (fester Heiz-Auslegungswert, `comfort_base` ∈ EN-Heizband, ~21) und `cool_sp` (fester Kühl-Auslegungswert, ~26). Dazwischen das **Totband**. Im **free-running**-Regime (10 ≤ T_rm ≤ 30, keine aktive Konditionierung) **erweitert** das EN-Adaptivband das Totband (senkt heat_sp / hebt cool_sp), aber es erzwingt nie einen warmen Heizsollwert.
2. **Capability** aus `hvac_modes` des Aktors → `can_heat`, `can_cool`; Nutzer-Override `climate_mode` (auto/heat_only/cool_only).
3. **Richtung = `decide_mode`** (RoomMind-Muster): heizen nur wenn `room<heat_sp ∧ can_heat ∧ outdoor≤heat_max`; kühlen nur wenn `room>cool_sp ∧ can_cool ∧ outdoor≥cool_min`; sonst **idle**.
4. **Priorität (`comfort_weight`):** verschiebt die Totbandbreite — Effizienz verbreitert (später/sparsamer), Komfort verengt (früher/präziser); Mapping auf die vorhandenen MPC-Gewichte.
5. **Idle = kein Energieaufwand:** der geschriebene Sollwert ist **kapazitätskorrekt** — heizfähig → `heat_sp` (TRV idlet oberhalb), nur-kühlfähig → `cool_sp` (idlet unterhalb). Nie an die falsche Bandgrenze klemmen.
6. **Harte Grenzen:** Frost + Schimmel-Mindesttemp als Heiz-Untergrenze; **Taupunkt-Cap** als Kühl-Obergrenze (gegen Kondensat).
7. **MPC-Kosten totband-bewusst:** Komfortkosten = 0 innerhalb `[heat_sp, cool_sp]` (RoomMind), asymmetrischer Overshoot-Penalty je Richtung.

## Begründung
Der Dual-Setpoint + Totband ist die normkonforme Lösung und behebt beide Live-Fehler (24 °C; Heizen eines warmen Raums). RoomMinds symmetrisches Gating schließt den vom Nutzer benannten Fehlfall (Nur-Kühlen+kalt) aus — die Lücke der eigenen Lösung. Poises `cooling.py` ist die fertige Basis.

## Konsequenzen
**Positiv:** normtreu; keine Energieverschwendung im Totband; gerätekorrekt; kein Heizen in der Kühlsaison und umgekehrt; Priorität steuert Effizienz/Komfort.
**Negativ/Kosten:** Comfort-Schicht von Einzel-Korridor auf Dual-Setpoint umgestellt (berührt `corridor.py`/Pipeline/MPC-Kosten); Capability-Erkennung aus `hvac_modes` nötig; drei neue Config-Werte (`comfort_base`, `climate_mode`, `comfort_weight`).

## Compliance
Norm- und gerätemuster eigenständig umgesetzt; generisch (Fähigkeit aus Standard-`hvac_modes`).

## Verknüpfungen
Erweitert ADR-0010 (Kühlung) und ADR-0017 (Operativ→Luft je Richtung); nutzt ADR-0015 (Capability) und ADR-0009 (MPC-Gewichte). Ersetzt die naive Einzel-Korridor-Zielbildung aus der ersten Comfort-Implementierung.
