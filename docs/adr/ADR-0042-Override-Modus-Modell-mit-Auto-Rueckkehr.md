# ADR-0042: Override-Modus-Modell — Kategorie/Offset auf der Komfortbasis mit Auto-Rückkehr

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-23 · **Bezug:** ADR-0012 (Override/State-Maschine), ADR-0023 (Capability-aware Dual-Setpoint), ADR-0025 (Schedule/Nachtabsenkung), ADR-0027/0035 (Norm-Floors & Constraint-Solver), ADR-0014 (Safety/Watchdog), ADR-0011 (Test-first) · **Grundlage:** `Meinungsbild_Override-und-Fenster-Slope.md`

## Kontext
Poise kennt heute genau **einen** manuellen Sollwert-Override — kein Anlass, keine Dauer, keine definierte Rückkehr. **Feld (verifiziert):** Versatile Thermostat bietet Presets (Frost/Eco/Comfort/Boost + versteckte Power/Safety), `*_away`/`*_ac`-Kontext, Activity/Bewegung, Safety-Notlast bei totem Sensor, Window-Bypass — aber als **freie Preset-Temperaturen**. **Community-Meinungsbild:** meistgewünscht ist ein **zeitlich begrenzter manueller Override mit Auto-Rückkehr** [VT#1875] („damit nicht die ganze Nacht hoch geheizt wird"); Timed-/Boost-Presets haben Steck-Bugs [VT#1961]; Presets sind nur Temperatur, Nutzer wollen explizite „Aus"-Aktion [VT#1979]; UI-Wert weicht von gespeichertem Preset ab [VT#1980].

## Entscheidung
1. **Modi = Kategorie/Offset auf der Komfortbasis, nicht freie Temperatur.** `Eco`/`Komfort`/`Boost`/`Frost`/`Abwesend` verschieben Basis bzw. EN-16798-Kategorie (I/II/III); der **Constraint-Solver** (ADR-0035) clamped weiterhin auf Frost-/Schimmel-Floor und ASR-Deckel. Jeder Modus ist damit **normkonform** — der Alleinstellungs-Vorteil ggü. VTherms freien Preset-Temps.
2. **Timed auto-revert (Pflicht-Feature).** Jeder Override/Modus trägt eine **Rückkehrregel**: feste Dauer, „bis nächster Schedule-Punkt" (ADR-0025) oder „bis Anwesenheitswechsel". Adressiert direkt den meistgewünschten Punkt [VT#1875].
3. **Pure, test-first Zustandsautomat** (`control/override.py`), der `original_mode`/Ablaufzeit korrekt verwaltet — bewusst gegen die Klasse der Boost-Steck-Bugs [VT#1961] (doppelter Timed-Set darf den Ursprungszustand nicht überschreiben).
4. **„Aus"/Frost als Modus** möglich (deckt [VT#1979]); Übergänge laufen durch denselben Solver, keine Sonderpfade.
5. **Safety = sichtbarer Modus, nicht neu gebaut.** Der bestehende Frozen-Sensor-Watchdog + Degradationsleiter (ADR-0012/0014) liefern das Verhalten; dieses ADR macht es nur als Override-Zustand sichtbar.
6. **Ein Wahrheitswert.** Effektiver Modus + Ablauf werden als Attribut exponiert, das die Card 1:1 liest (gegen die „Karte ≠ Attribut"-Divergenz [VT#1980]).

## Konsequenzen
**Positiv:** verständliche, automatisierbare Modi; normgebunden (kein Floor-Bruch); kein klebender Override; saubere Card-Kopplung (ADR-0016/0040). **Negativ:** mehr Zustandslogik (durch pure Test-first-Maschine beherrscht); Reihenfolge nach ADR-0041 (Fenster-Slope zuerst), weil „Frost/Eco" als Modus dann bereits existiert und der Solver-Pfad eingespielt ist.

## Nachtrag — umgesetzt (v0.69.0)

Pure `control/override.py` (getestet): `OverrideMode` (none/eco/comfort/boost/away, Werte = HA-PRESET_* → Frontend übersetzt nativ), `mode_comfort_base(mode, base, cfg)` = **Offset auf der Komfortbasis** (Eco −2K, Away −4K, Boost +1.5K), `manual_override_expired(set_at, now, cfg)` (Auto-Rückkehr nach 2h, VT#1875). Coordinator: Preset verschiebt `comfort_base` VOR `plan_preheat` → läuft durch Solver → jeder Modus normgeclampt (Frost/Schimmel/ASR). Manueller Sollwert-Override merkt sich Setzzeitpunkt (`_override_set_mono`) und wird im Tick nach Ablauf automatisch gelöscht. Persistenz `preset` in Save-Payload. Climate: `ClimateEntityFeature.PRESET_MODE` + `preset_modes` + `preset_mode`-Property + `async_set_preset_mode`. Diagnose-Attrs `preset`/`override_active`. Gate grün (pytest 354/mypy60/card13). OFFEN (bewusst): zusätzliche Ablauf-Typen „bis nächster Schedule-Punkt"/„bis Anwesenheitswechsel" (derzeit nur Dauer); Frost-Modus; Card-Preset-Chips.

## Nachtrag — override_clamped (v0.130.0, Review V10)
Der manuelle Sollwert-Override wird in `resolve_write_target` auf `[heat_sp, cool_sp]` geklemmt (`tick_resolve.py:83`) — bisher **still**, ohne Rückmeldung. Neu: `WriteTarget.override_clamped` meldet True, wenn der gesetzte Wert außerhalb des Komfortbandes lag; der Coordinator exponiert `override_clamped = wt.override_clamped and not frozen` als Climate-Attribut. Adressiert die „Karte ≠ erwarteter Wert"-Klasse [VT#1980] für den band-limitierten Override: im engen EN-Kategorie-Band des Komfortfensters sichtbar, außerhalb (ADR-0023/V3-relaxiertes Setback-Band) meist False. 3 Tests (`test_tick_resolve`).
