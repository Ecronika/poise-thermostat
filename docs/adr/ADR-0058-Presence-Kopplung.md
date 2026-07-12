# ADR-0058: Presence-Kopplung — hierarchische Belegung (Haus-Gate + Raum-Eco)

**Status:** In Arbeit (70 %) · **Wirkung:** Live-A · **Datum:** 2026-07-05 · **Bezug:** ADR-0023 (Dual-Setpoint/Setback als `occupied`-Konsument, V3), ADR-0025 (Zeitplan/Optimal-Start), ADR-0042 (Preset/Override, Away), ADR-0052 (Aktor-Dynamikprofil), ADR-0053 (Lüfterumwälzung — `occupied`-Vorbedingung), ADR-0048 (Nicht-Ziele: kein Ortungsdienst), ADR-0008 (Config) · **Verifizierung:** Wettbewerb (Versatile Thermostat Presence/Motion nativ; Better Thermostat keine; tado Auto-Assist als v2-Referenz); EN 16798-1 (Bänder gelten für die Nutzungszeit); PIR/mmWave-Sensorik-Asymmetrie

## Umsetzungsstand
**v0.150.0 — Glue gelandet (live).** Pure `comfort/presence.py` (`resolve_presence`
hierarchisch + `step_room_absence` asymmetrischer Anker, 8 Tests) + `decide()`-Nachtrag
(`eco_widen`/`cool_ceiling_override`, 5 Regressionstests) sind verdrahtet:
- **Config:** `presence_home` (person/tracker/binary_sensor/group), `occupancy_sensor`
  (binary_sensor), `absence_after_min` (Default 30) — beide Entities optional, unkonfiguriert
  = heutiges Verhalten (fail-safe anwesend), null Regression.
- **Coordinator:** Haus-Gate wird **vor** `plan_preheat` aufgelöst; ein leeres Haus (oder
  Away-Preset) heizt nicht mehr vor und speist eine **neutrale** Basis in `mode_comfort_base`
  (kein `override.py`-Eingriff), sodass die Tiefe allein `eco_widen` trägt (kein Double-Dip).
  Raum-Absenz-Anker ist transient (Neustart → anwesend, Latch greift neu).
- **Level→Parameter:** COMFORT → (`occupied` wie bisher, 0, `COOLING_UPPER`); ROOM_ECO →
  (`False`, `eco_offset` 2 K, Decke `cool_hard_cap`); AWAY → (`False`, `away_offset` 4 K,
  Decke `device_max`), **ohne Basisverschiebung** → schließt den Away-Kühl-Bug (Nachtrag unten).
- **Nebenwirkung:** `fan_circulation` (ADR-0053) bekommt jetzt echtes `occupied`.
- **Diagnose:** `occupied`/`presence_level`/`room_absent_min`/`home_present`.

Offen bis 100 %: Card-Anzeige des Presence-Levels · Coordinator-Integrationstest (CI) ·
Live-Verifikation am Büro/Home-HA · optional Persistenz des Absenz-Ankers (bewusst transient).

## Kontext
Presence ist die letzte große Lücke der Wettbewerbsmatrix gegenüber Versatile Thermostat. Das Fundament steht bereits: `occupied` ist seit v0.122 ein echter, **live** wirkender Steuer-Eingang — `dual_setpoint.decide(occupied=…)` erlaubt bei `False` die V3-Absenk-Drift (Bandunterkante relaxt bis zum Health-Floor), heute gespeist rein aus dem Away-Preset: `_occupied = (sched.is_comfort ∨ preheating) ∧ ¬away` → `comfort_decide(occupied=_occupied)`. `fan_circulation` (ADR-0053) wartet direkt auf genau dieses `occupied`-Signal (heute hart `None` übergeben → nur Shadow). Es fehlt allein die **Auflösung eines Presence-Entities → `occupied`**; die Steuerwirkung reitet auf dem bestehenden Pfad.

## Entscheidung: hierarchisch, nicht OR
Zwei optionale Eingänge mit **unterschiedlicher Semantik, Zeitkonstante und Fehlercharakteristik** werden NICHT per OR verknüpft — OR erbt die Fehler beider (Person daheim, Raum unbetreten → Einsparung verschenkt; Raumsensor feuert durch Katze/Saugroboter/mmWave-Artefakt bei allen Trackern abwesend → heizt fürs Nichts). Stattdessen:

```
occupied = home ∧ ((is_comfort ∧ (raum_belegt_kürzlich ∨ kein_raumsensor)) ∨ preheating)
```

`home` ist das **äußere Gate**; Preheat übersteuert nur die Raum-Ebene, **nie** das Haus-Gate — sonst würde Optimal-Start ein leeres Haus vorheizen (Klammerung ist bewusst so, nicht `… ∨ preheating` auf oberster Ebene). Zeitkonstante des Gates: Stunden, symmetrisch verlässlich, kein Nachlauf nötig.

**Ein Bool trägt aber keine zwei Absenktiefen.** Die Klemme `occupied = False` löst die *volle* V3-Drift zum Health-Floor aus; die geforderte Eco-Zwischenstufe braucht eine **dritte** Stufe, und die Tiefe steuert der **Offset**, nicht die Klemme. Der Resolver liefert daher ein Level:

- **`COMFORT`** — `occupied` wie heute (der Zeitplan entscheidet).
- **`ROOM_ECO`** — Haus belegt, Raum leer ≥ `absence_after_min` → `occupied = False` **und** Basis − `eco_delta`. `occupied` MUSS hier `False` sein: bei `True` klemmt `HEATING_LOWER[cat]` den Offset weg (aus −2 K würden bei Cat II real −1 K, bei Cat I null). Die Sicherung gegen „zu tief" ist der **flache Offset selbst**, nicht die Kategorie-Klemme — die Health-Floors liegen ohnehin darunter. Mechanisch identisch zur Nachtabsenkung, nur mit anderer Offset-Quelle → null neue Regelmechanik.
- **`AWAY`** — `home = False` → `occupied = False`, bestehender Away-/Setback-Pfad (volle Drift). „Raum leer" ist das schwächere Signal (PIR-Asymmetrie — „belegt" sicher, „leer" bei stillem Sitzen falsch) und der Wiedereintritt unangekündigt (3 K bei trägem Heizkörper = ½ h Diskomfort) — deshalb *nicht* die volle Tiefe.

Die Eco-Relaxierung ist **richtungsneutral** (Band-Aufweitung um `eco_delta` über `dual_setpoint`): im Winter sinkt die Heizkante, im Sommer steigt die Kühlkante — dasselbe Modul, beide Richtungen, keine Kühl-Sonderlogik. EN-16798-konform, weil die Bänder für die Nutzungszeit gelten.

## Präzisierungen
1. **Beide Felder einzeln optional; fehlen beide → exakt heutiges Verhalten (null Regression).** v1: je genau **eine** Entity (mehrere Personen → HA-Gruppen-Helper; idiomatisch, spart Multi-Entity-Logik).
2. **Asymmetrisches Debouncing nur am Raumsensor:** belegt → sofort wirksam; leer → erst nach `absence_after_min` (Default **30 min**, Bereich 5–120; PIR-sicher, mmWave-Besitzer drehen runter). `home` braucht keine Haltezeit (Tracker sind selbst träge). Die `room_absent_since`-Uhr ist **transient**: nach Neustart konservativ als *belegt* starten und die Haltezeit frisch anlaufen (Latch-Muster — level-basiert, rastet selbst wieder ein).
3. **Eintritts-Reaktion an das Dynamikprofil (ADR-0052) gekoppelt:** `slow_hydronic` → Belegung wirkt nur als **Abwesenheits-Sparer** (Heizen-auf-Bewegung ist bei thermischer Trägheit sinnlos — der Raum wird warm, wenn der Besuch vorbei ist). `fast_air` (Split-AC) + Fan → Reaktion in Minuten real, Belegung darf Komfort **auslösen** — und ist genau die ADR-0053-Vorbedingung (Umwälzung nur im *belegten* Totband). Dieselbe Semantik, geräteklassenabhängig scharf.
4. **Health-Floors unberührt** — Belegung bewegt nur die COMFORT-Ebene im Präzedenz-Solver; Frost/Schimmel liegen unverändert darunter. Kein neuer Sicherheitspfad → risikoarm genug für **direkt live** (opt-in pro Zone) ohne Shadow-Saison, aber mit Transparenz-Attributen `occupied_source` (`schedule|home|room|preheat`) + `room_absent_since`, damit die Card erklärt, *warum* gerade Eco gilt.
5. **Rückkehr:** `home` False→True setzt sofort auf den Zeitplan zurück (Trigger ist der Eintritt selbst; kein Optimal-Start). **Geofencing-Proximity** („heizt schon auf dem Heimweg", tado-Auto-Assist-Parität) ist der saubere v2-Ausbau: dieselbe Schnittstelle, nur ein früherer Trigger — NICHT in v1.
6. **Fail-safe bei `unavailable`/`unknown` (Degradationsleiter):** ein nicht verfügbares Presence-Entity wird wie **anwesend** behandelt (Komfort), NIE wie abwesend — ein toter Tracker darf das Haus nicht kalt stellen. Zustandsauswertung: `person`/`device_tracker` → `state == "home"` (benannte Zonen wie „Arbeit" zählen NICHT als home); `binary_sensor`/`group` → `on`.
7. **`eco_delta` = bestehender ECO-Preset-Offset**, kein neuer Wert: die Raum-Eco greift denselben −2 K wie der ECO-Preset (`override.py`). Ein Produkt, eine Eco-Tiefe — die Card zeigt ehrlich „Eco (Raum leer)", zwei divergierende „Eco"-Begriffe entfallen. 2 K passt beide Richtungen: darunter verschwindet der Effekt im Deadband-/Hysterese-Rauschen, 3 K wäre vom Setback ununterscheidbar.
8. **Schlafraum-Vorbehalt (Doku, kein Blocker):** PIR erkennt Schlafende nicht → Schlafzimmer-PIR + Nacht-Komfortfenster ⇒ Eco, während jemand im Bett liegt (keine Haltezeit überbrückt 8 h Schlaf). Empfehlung: Schlafräume mit mmWave oder ganz ohne Raumsensor; `occupied_source` macht den Fall wenigstens diagnostizierbar. Betrifft primär die Heizsaison.
9. **Bekannte Grenze des Haus-Gates:** Gast/Reinigungskraft ohne getracktes Phone bleibt bei `home = False` unsichtbar — Ausweg ist der bestehende Preset/Override (manuell Komfort erzwingen), kein neuer Mechanismus.

## Nicht-Ziele (ADR-0048-kohärent)
Kein Ortungs-/Geofencing-**Dienst**, kein Standort-Tracking, keine Persistenz einer Anwesenheits-Historie (nur die aktuelle `room_absent_since`-Uhr, transient). Poise **konsumiert** bestehende HA-Presence-Entities, es erzeugt sie nicht.

## Folgeschritt (Roadmap, nicht v1)
Das Raum-Belegungssignal ist zugleich der natürliche `q_occ`-Eingang für den EKF (β_o wird heute nie angeregt) — erst anschließen, wenn das Flag eine Saison stabil läuft, sonst lernt der Filter Sensor-Artefakte.

## Konsequenzen
**Positiv:** schließt die letzte große VTherm-Lücke; nutzt den bestehenden **live**-`occupied`-Pfad (kein neuer Regelmechanismus); schaltet zugleich ADR-0053 von Shadow auf live; physikalisch ehrlicher als VTherms flaches Motion-Preset-Modell (hierarchisch + dynamik-bewusst); im Sommer sofort messbar (Kühlung setzt aus, wenn niemand da ist). **Negativ:** eine weitere Config-Fläche (durch „beide optional" abgefedert); Eco-Tiefe (`eco_delta`) und Haltezeit (`absence_after_min`) brauchen Feldkalibrierung. **Risiko:** minimal — Comfort-Ebene only, Health-Floors unberührt, opt-in, reversibel.

## Nachtrag (2026-07-05): Richtungsneutrale Eco-Relaxierung in `decide()`

**Befund (v0.149.0-verifiziert):** `dual_setpoint.decide()` (Z. 79–85) relaxt bei `occupied=False` **nur die Heizkante** (`heat_lower = frost_floor`); die Kühlkante bleibt bedingungslos auf `COOLING_LOWER…COOLING_UPPER[cat]` geklemmt. Eine abgesenkte Basis (Nacht-Setback *oder* Away-Preset) senkt zudem `cool_op = base + Totband + widen` → **niedrigeres** `cool_sp`. Konkret Away 17 °C → `cool_op = 17,5` → Clamp auf `COOLING_LOWER` = 23,0 (Kat. II): **Away kühlt heute schärfer als Komfort** (~23,0 statt ~23,5–24,5 adaptiv). Der Clamp begrenzt den Schaden auf 0,5–1,5 K, aber die Richtung ist falsch — im Sommer ein echter Energie-Bug. „Basis − eco_delta" als ROOM_ECO-Mechanik hätte denselben Fehler. Die im Entscheidungsteil geforderte **Richtungsneutralität** braucht daher einen Eingriff in `decide()`, nicht im Coordinator.

**Formel (beide Kanten symmetrisch aufgeweitet):**
```
heat_op = clamp(base − widen − eco_widen, heat_lower, HEATING_UPPER[cat])   # heat_lower = frost_floor bei occupied=False
cool_op = clamp(base + Totband + widen + eco_widen, COOLING_LOWER[cat], cool_ceiling)
```

- **Kein Double-Dip:** mit `eco_widen > 0` verschiebt der Aufrufer die **Basis nicht** — die Basisabsenkung war immer nur ein Heiz-Setback-Proxy und kämpft auf der Kühlseite gegen `eco_widen`. Die Tiefe trägt allein `eco_widen`; die Heizseite landet über den unveränderten `occupied=False`-Pfad ohnehin am `frost_floor`. **ROOM_ECO braucht weiterhin `occupied=False`**, sonst klemmt `HEATING_LOWER` (20,0) die 2-K-Heiz-Relaxierung weg.
- **Deckel-Stufung (`cool_ceiling`):** `None` → `COOLING_UPPER[cat]` (heutiges Verhalten). **ROOM_ECO → `cool_hard_cap`** (jemand ist im Haus, ASR-26 bleibt die Schmerzgrenze). **AWAY → `device_max`** (Kühlung faktisch aus). Bewusst NICHT `cool_hard_cap` als Away-Deckel: bei Kat. II ist `COOLING_UPPER` = 26 = cap-Default → No-op, und es invertierte die ASR-A3.5-Semantik (Deckel für *besetzte* Arbeitsplätze).
- **Kompositionsreihenfolge:** `eco_widen` VOR dem `adaptive_cool_edge`-Aufruf in die feste Kante einrechnen → automatisch `max(feste Kante + eco_widen, adaptive Kante)`; eine adaptive Anhebung darf eine Eco-Relaxierung nie wieder absenken. Taupunkt+2-Floor und `cool_sp = max(cool_sp, heat_sp)` bleiben die letzten Schritte.
- **HEALTH-Floors levelunabhängig:** Taupunkt+2, `mold_min`, `frost_floor` und der Dry-/Entfeuchtungspfad liegen hinter den Kanten und greifen auch bei Abwesenheit — hohe RH im leeren Haus muss weiter Dry auslösen.

**Signatur:** `decide(..., eco_widen: float = 0.0, cool_ceiling_override: float | None = None)` — die reine Mathematik bleibt frei von Preset-Wissen, die Deckel-Entscheidung trägt der Coordinator (der Presets UND Presence kennt). **Level→Parameter-Mapping:** COMFORT → `(0.0, None)`; ROOM_ECO → `(eco_delta, cool_hard_cap)` + `occupied=False`; AWAY → `(eco_delta_or_more, device_max)` + `occupied=False`, ohne Basisverschiebung.

**Regressionsnetz (test-first, vor dem Umbau):** (i) Away-Raum 30 °C → `cool_sp` MUSS über dem Komfort-`cool_sp` liegen (schlägt am v0.149-Stand fehl — Red-Green-Nachweis des Bugs); (ii) `eco_widen = 0` → bitidentisch zum v0.149-Verhalten über die ganze bestehende Testmatrix (Nachtabsenkung/Preheat unangetastet); (iii) Dry-/Taupunkt-Pfad feuert auch mit `eco_widen > 0`.
