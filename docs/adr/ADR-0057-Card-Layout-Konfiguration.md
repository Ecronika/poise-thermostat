# ADR-0057: Card-Layout & Konfiguration (Dichte, Bedienung, Abschnitte, Schimmel-Tick, UI-Editor)

**Status:** Implementiert (Card v0.138.0) · **Wirkung:** Live-A · **Datum:** 2026-07-03 · **Bezug:** ADR-0040 (Card-Vertrag/Auto-Registrierung), ADR-0016 (Entity-/Card-Vertrag), ADR-0049 (Monitoring-Ampel), ADR-0054/0055 (PMV-/CA-Lampen), ADR-0050/0051 (Schimmel-/Frostschutz-Floor), ADR-0012 (Diagnostics/Redaction), ADR-0026 (Shadow-first: Card ist reine Anzeige) · **Verifizierung:** pure `card-config` Unit-Tests (node --test), tsc, Bundle-Build; Backend-Attribut `mould_floor`/`dewpoint` CI-verdrahtet; Nutzer-Designentwürfe (Wohnzimmer-/Büro-Mockup)

## Umsetzungsstand (v0.138.0 — implementiert)

**Pure Kern (getestet):** `card/src/card-config.ts` — `resolveConfig(raw) → ResolvedConfig` faltet die Roh-Config auf ein normalisiertes Modell mit **stillen Fallbacks** (ungültig/unbekannt → sinnvoller Default, Doktrin wie ADR-0049 §6): `density` (comfortable|compact), `controls` (dial|buttons|none), `history` ({show, hours ∈ 12|24|48}), `chips` (Set aus hvac|window|temperature|humidity|co2|ca), `pmv`/`presets`/`shadowPill`/`learning` (Booleans). Legacy-`compact` aliast `density:compact`, Legacy-`show_shadow` aliast `sections.shadow_pill`. `hours` wird numerisch koerziert (ha-form kann Strings liefern). **9 neue Unit-Tests** (`test/card-config.test.ts`) → tsc clean, 36/36 Card-Tests grün.

**Render (`poise-card.ts`):** jeder Abschnitt einzeln gegated — `controls` schaltet zwischen interaktivem Ring (dial), statischer Gauge + `+/−`-Steppern (buttons) und reiner Anzeige (none, Wandtablet-Schutz: Pointer/Keyboard aus, `role=img`); `history.show`/`hours` steuern den Verlaufs-Chart; `chips`/`pmv` filtern die Zustands-/Lampenreihe; `shadowPill`/`learning` das Lern-/Shadow-Band; `density=compact` verdichtet Abstände + Hero-Größe. **Schimmel-Tick:** oranger Radial-Strich + Zahl bei `valueToAngle(mould_floor)` auf dem Dial (nur wenn im sichtbaren Bogen, sonst still übersprungen). **Preset-Abschnitt:** Buttons aus `preset_modes` der Entität, aktueller `preset_mode` hervorgehoben, Klick → `climate.set_preset_mode`.

**Backend-Glue:** der Coordinator veröffentlicht `mould_floor` (= `mold_min`) und `dewpoint` im Return-Dict + `_ATTRS` (Anzeige, keine Steuerung).

**UI-Editor (`poise-card-editor.ts`):** `ha-form` mit Selects (density/controls), Expandables *History*/*Sections*/*Advanced*, Chips-Multiselect, Section-Booleans, i18n-Labels — alles per UI einstellbar (kein YAML nötig).

## Kontext

Die Card exponierte bis v0.137.0 nur `entity`/`show_shadow`/`compact`; alle neuen Bewertungsgrößen (PMV, CA) und Zustände waren fest verdrahtet. Nutzerwunsch: (a) granulare Kontrolle über jedes Anzeige-Element — per YAML **und** UI; (b) Bedien-Modus wählbar (Dial vs. Stepper vs. reine Anzeige für Wandtablets); (c) die Schimmelgrenze als Marke auf dem Dial (Vorbild: vertikale Thermometer-Skala des Büro-Mockups); (d) Optik Richtung des Wohnzimmer-Entwurfs. Die Dial-Geometrie (270°-Bogen, Lücke unten) ist bereits topologisch identisch zum Entwurf → Feinschliff statt Neubau.

## Entscheidung

1. **Konfiguration deklarativ + normalisiert.** Ein einziger, unit-getesteter `resolveConfig` bildet die gesamte Roh-Config (inkl. Legacy-Aliasse) auf ein `ResolvedConfig` ab; die LitElement liest **nur** das aufgelöste Modell. Ungültige Werte werfen nie, sondern fallen still auf Defaults (Card muss immer rendern).
2. **`controls` trennt Anzeige von Bedienung.** Die Gauge ist immer sichtbar; nur Interaktivität + Stepper variieren. `none` = harte Wandtablet-Sperre (kein versehentliches Verstellen).
3. **`sections` per Element.** `chips` als Teilmenge (Zustands-Chips + Lampen vereinheitlicht); `pmv` als eigener Schalter (Kopf-Behaglichkeitsmetrik); `shadow_pill`/`learning`/`presets` als Booleans. Defaults = alles an → keine Regression für Bestandsnutzer außer dem bewusst geänderten `compact` (jetzt rein visuell).
4. **Schimmel-Tick display-only.** `mould_floor` ist ein Anzeige-Attribut; die Card interpretiert nicht und steuert nicht (Monitoring-vs-Control, ADR-0048/0026). Farbe an Theme-Variable `--warning-color`.
5. **Presets über den HA-Standardpfad** (`preset_modes`/`set_preset_mode`), nicht über Poises interne `preset`-Diagnose.

## Konsequenzen

**Positiv:** volle, aber sichere Konfigurierbarkeit (YAML + UI); Wandtablet-Schutz; Schimmelgrenze at-a-glance; pure, getestete Auflösungslogik hält `poise-card.ts` schlank; keine zusätzliche Recorder-Last (Card-seitig, ADR-0049-Linie). **Negativ/Kosten:** mehr Config-Felder (über Editor-Expandables gebändigt); **Verhaltensänderung** — Legacy `compact:true` blendet keine Abschnitte mehr aus, sondern verdichtet nur (Sichtbarkeit steuern jetzt `controls`/`sections`); zwei neue Entitäts-Attribute (`mould_floor`, `dewpoint`).

## Verifizierung

Pure `resolveConfig`/`resolveChips`/`resolveHistory`/`chipEnabled` unit-getestet (Defaults, Legacy-Aliasse, Koerzierung, unbekannte Tokens); tsc + node --test grün (36); Bundle-Build 0.138.0 mit den neuen Render-Pfaden (String-Literale `set_preset_mode`/`mould_floor`/`Schimmelgrenze`/`Voreinstellungen` im Bundle verifiziert). Backend-Attribut-Verdrahtung ist **CI-verdrahtet, nicht selbst ausgeführt** (HA-Imports + Sandbox-Dehydrierung des OneDrive-Mounts). Live-Verifikation am Dashboard nach Deploy (Schimmel-Tick, Preset-Schalten, `controls:none`-Sperre).

## Compliance

Rein card-seitige Auflösungs-/Render-Logik, generisch, eigenständig (G29/G30). Farben an Theme-Variablen (Barrierefreiheit, ADR-0040-Linie). Schimmel-Tick strikt monitor-only (ADR-0048/0026). Presets über den dokumentierten HA-`climate`-Servicevertrag.

## Verknüpfungen

**Erweitert ADR-0040/0016** (Card-/Entity-Vertrag um Layout-Config, `mould_floor`/`dewpoint`), **ADR-0049/0054/0055** (die Ampel-/PMV-/CA-Lampen sind jetzt per `sections` schaltbar). **Belege:** Nutzer-Designentwürfe (Wohnzimmer-/Büro-Mockup); HA `ha-form` Expandable/Selector-Vertrag; `climate.set_preset_mode`.
