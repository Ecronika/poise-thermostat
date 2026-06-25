# ADR-0026: Schatten-Schätzer — intern immer rechnen, extern nur Anzeige-/Verwendungsvorrang

**Status:** akzeptiert · **Datum:** 2026-06-20 · **Bezug:** ADR-0007 (Persistenz), ADR-0010 (Solar), ADR-0017 (Operativ/MRT), Phase 1/2 (Fahrplan), v0.9.0 (T_rm) · **Verifizierung:** Coordinator-Code (`coordinator.py`), `running_mean.py`

## Kontext
Optionale Eingangssensoren (T_rm, MRT, Solar …) können nachträglich entfernt werden. Wenn der zugehörige **interne Schätzer nur dann läuft, wenn der externe Sensor fehlt**, startet die Integration beim Entfernen **kalt** (keine Historie, schlechte erste Werte). Das ist vermeidbar.

## Entscheidung — Grundprinzip „Schatten-Schätzer"
1. **Interne Schätzer rechnen in jedem Tick mit — unabhängig davon, ob ein externer Sensor konfiguriert ist.** Ihr Zustand wird **immer persistiert** (ADR-0007).
2. Der externe Sensor hat Vorrang **nur für Anzeige und Regelung** (Auswahlkette: *extern (falls konfiguriert & gültig) → intern → Fallback*).
3. Der jeweilige **Schattenwert** und ein `*_source`-Indikator werden als Diagnose-Attribut exponiert, damit man sieht, dass intern bereits Daten gesammelt werden.
4. Folge: Wird der externe Sensor entfernt, übernimmt der interne Schätzer **warm** (mit Historie) ohne Sprung.

## Anwendbarkeits-Analyse (Stand v0.9.0) — „Auf welche Features trifft das zu?"

**Bereits konform (Schätzer vorhanden, läuft immer):**
- **T_rm-Laufmittel** — `RunningMeanTracker` beobachtet jeden Tick unbedingt, persistiert, `t_rm_source` + `t_rm_internal` sichtbar. ✅ (v0.9.0/0.9.1)
- **Gebäudemodell (EKF)** — `_learn` läuft immer (nur bei offenem Fenster physikalisch pausiert), persistiert. Es gibt ohnehin keinen externen „Modell-Sensor". ✅

**Anwendbar, aber Schätzer fehlt noch (Folge-Features):**
- **Solar-Einstrahlung** — derzeit `q_solar = 0` im EKF-`predict`, β_s also untrainierbar (tot). Ein **analytischer Clear-Sky-Schätzer** aus Sonnenstand (`sun.sun`-Elevation + Tageszeit) ist rein rechnerisch (keine Extra-Hardware) und sollte **immer** laufen; ein optional konfigurierter Globalstrahlungssensor überschreibt nur Anzeige/Verwendung. **Stärkster nächster Kandidat** (schaltet zugleich β_s scharf). (ADR-0010, Phase 2)
- **Virtuelle MRT / Operativtemperatur** — intern aus Luft + Solar + Wandmodell schätzbar; hängt am Solar-Schätzer. Heute fällt `operative` ohne MRT-Sensor auf die Lufttemperatur zurück. Mittlerer Aufwand. (ADR-0017)

**Nicht anwendbar (keine interne physikalische Basis):**
- **Luftfeuchte** — ohne Sensor nicht seriös schätzbar (speist Taupunkt-Cap + Schimmel).
- **Fensterkontakt** — reiner Zustand, nicht berechenbar.
- **Rohe Außentemperatur** — ist die Primärmessung selbst; ein „Spiegeln" eines Wetter-Entity wäre nur ein Fallback, kein eigenständiger Schätzer.

## Konsequenzen
**Positiv:** Nahtloser Wechsel extern↔intern ohne Kaltstart; Diagnose-Sichtbarkeit der Schattendaten; konsistentes Designmuster für alle künftigen optionalen Eingänge. **Negativ:** minimaler Mehraufwand für Rechnung + Persistenz pro Tick (vernachlässigbar). **Risiko:** Schätzqualität ≠ externe Messqualität → durch `*_source`-Kennzeichnung transparent gemacht, externe Quelle behält Vorrang.

## Nächster Schritt (empfohlen)
Analytischen Solar-Schätzer als Schatten-Schätzer bauen (immer aktiv, `q_solar` in EKF/MPC, optionaler Messsensor mit Vorrang) — schließt zugleich die tote β_s-Achse.
