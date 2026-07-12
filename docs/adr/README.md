# Architecture Decision Records (ADR)

Entscheidungsregister für Poise. Format/Prozess: [`ADR-0000`](ADR-0000-Format-und-Prozess.md).

**Ablageort:** Dieses Verzeichnis (`docs/adr/`) ist der **alleinige, maßgebliche Ort** für ADRs. Frühere Streukopien (Projektordner `ADR/`, Repo-Wurzel `ADR/`) sind aufgelöst, damit Reviewer die ADRs direkt im Repo prüfen können.

## Status-Konventionen

Der Status jedes ADR wird **gegen den Code** bestimmt — nicht nur gegen die getroffene Entscheidung:

- **Implementiert** — vollständig und erfolgreich umgesetzt und durch Tests/Gate abgesichert.
- **In Arbeit (xx %)** — begonnen, aber noch nicht abgeschlossen; *xx %* ist der abgeleitete Umsetzungsgrad. Typische Fälle: reine Logik + Tests vorhanden, aber noch nicht verdrahtet; oder als *Shadow* berechnet/diagnostisch ausgegeben, während die Aktuierung noch gated/inaktiv ist.
- **Vorgeschlagen** — Entscheidung dokumentiert, Umsetzung noch nicht begonnen.
- **Ersetzt durch ADR-XXXX** — durch einen neueren ADR abgelöst; Inhalt nicht mehr maßgeblich.
- **Veraltet** — nicht mehr gültig, ohne direkten Nachfolger.

Reine Prozess-/Meta-Records (z. B. ADR-0000) tragen **Gültig**. Der frühere reine Entscheidungsstatus „akzeptiert" wird durch die umsetzungsbezogenen Stufen oben ersetzt. Der Status in der Tabelle entspricht dem Status-Header im jeweiligen ADR.

### Wirkungs-Konventionen (Aktuierungswirkung)

Zusätzlich zum **Status** (*wie weit umgesetzt*) trägt jeder ADR eine **Wirkung** (*ob und wie er den Aktor bewegt*) — die beiden Dimensionen sind **orthogonal**. Die Wirkung steht auf der Status-Zeile direkt hinter dem Status-Token (`**Status:** … · **Wirkung:** <Token> · **Datum:** …`) und ist genau **ein** Token aus:

- **Live-A** — aktuiert im **Live-Schreibpfad** (bewegt Aktor/Sollwert echt).
- **Live-D** — läuft jeden Tick, aber rein **diagnostisch** (berechnet/exponiert, kein Write).
- **Shadow** — berechnet, schreibt **nie** (gated Schatten-Pfad, ADR-0026-Politik).
- **teilw.** — **teilweise** verdrahtet (einzelne Stufen live, andere Shadow/offen).
- **Harness** — nur **Test-/Harness-Pfad**, nicht im Produktions-Tick.
- **Doku** — reine **Dokumentations-/Abgrenzungs-/Entscheidungs**-Entscheidung ohne Laufzeit-Code.
- **Gültig** — **Meta-/Prozess**-Record (kein Aktuierungsbezug).
- **n.a.** — **nicht anwendbar** / noch nicht gebaut.

Der Linter (`tests/test_adr_status_lint.py`) erzwingt, dass jeder ADR-Header ein `**Wirkung:**`-Feld mit einem Token aus dieser Menge trägt.

| ADR | Titel | Status |
|---|---|---|
| [0000](ADR-0000-Format-und-Prozess.md) | ADR-Format und -Prozess | Gültig |
| [0001](ADR-0001-MPC-Solver.md) | MPC-Solver: greedy variable Trajektorie + BT-Robustheitsbausteine | In Arbeit (80 %) |
| [0002](ADR-0002-Schaetzer-Optimierer-Trennung.md) | Ein Schätzer (EKF) speist reinen Optimierer | Implementiert |
| [0003](ADR-0003-Residual-Heat-Advisory.md) | Residual-Heat / Optimal-Stop als advisory Dienst | In Arbeit (85 %) |
| [0004](ADR-0004-TPI-Koeffizienten-Lernen.md) | TPI-Lernen: physikalischer Seed + Online-Nachführung | In Arbeit (45 %) |
| [0005](ADR-0005-Datenvertraege-und-Schichtgrenzen.md) | Datenverträge & Schichtgrenzen (frozen dataclass, ABC, DI) | Implementiert |
| [0006](ADR-0006-Ausfuehrungs-und-Nebenlaeufigkeitsmodell.md) | Atomarer Tick, Event-Coalescing, monotone Uhr | Implementiert |
| [0007](ADR-0007-Persistenz-Migration-Bootstrap.md) | Persistenz, Migration & koordinierter Bootstrap | In Arbeit (75 %) |
| [0008](ADR-0008-Config-Schema-und-Defaults.md) | Config-Schema & begründete Default-Herleitung | In Arbeit (45 %) |
| [0009](ADR-0009-EKF-Tuning-und-Konfidenz-Gating.md) | EKF-Tuning + weiche MPC-Gate-Überblendung | In Arbeit (80 %) |
| [0010](ADR-0010-Solar-Buchhaltung.md) | Solar als ein β_s-Pfad, Anti-Oszillation | Implementiert |
| [0011](ADR-0011-Simulations-Harness-und-Test-Pyramide.md) | Replay-Harness + 5-Ebenen-Test-Pyramide | Implementiert |
| [0012](ADR-0012-Fehlerbehandlung-Logging-Repair-Issues.md) | Fehler-Taxonomie, Repair-Issues, Logging, Diagnostics | Implementiert |
| [0013](ADR-0013-Mehrzonen-Ausfuehrung-und-Koordination.md) | Zwei-Phasen-Mehrzonen + Smallest-Gap-Shedding | In Arbeit (70 %) |
| [0014](ADR-0014-Determinismus-und-Referenzfaelle.md) | Determinismus + Norm-Referenz-Fixtures | Implementiert |
| [0015](ADR-0015-Aktorpfad-Capability-Matrix.md) | Exklusive Capability-Matrix + coef_ext | In Arbeit (70 %) |
| [0016](ADR-0016-Entity-Modell-und-Card-Vertrag.md) | Entity-Modell + climate-Attribut-Card-Vertrag | Implementiert |
| [0017](ADR-0017-Operativ-zu-Luft-Transformation.md) | Operativ→Luft-Transformation (eine Stelle, geglättet) | Implementiert |
| [0018](ADR-0018-Versionierung-Semver-Deprecation.md) | SemVer + kumulative Migration + Deprecation | In Arbeit (60 %) |
| [0019](ADR-0019-KNX-Norm-Expose.md) | KNX-/Norm-Expose als optionales Status-Modul | Vorgeschlagen |
| [0020](ADR-0020-Performance-Budget.md) | Performance-Budget: 60 s + eventgetrieben + Caching | In Arbeit (80 %) |
| [0021](ADR-0021-i18n-und-Einheiten.md) | strings.json-Quelle, generierte Sprachen, Einheiten | In Arbeit (70 %) |
| [0022](ADR-0022-Security-und-Supply-Chain.md) | Null schwere Deps, lokal, anonymisiert, redigiert | In Arbeit (75 %) |
| [0023](ADR-0023-Komfort-Dual-Setpoint-Totband.md) | Capability-aware Dual-Setpoint + Totband + Priorität | Implementiert |
| [0024](ADR-0024-EKF-Identifizierbarkeit.md) | EKF-Identifizierbarkeit: α-Dämpfung, Modus-Zähler, ID-Konfidenz | Implementiert |
| [0025](ADR-0025-Zeitplan-Nachtabsenkung-Optimal-Start.md) | Komfort-Zeitplan, Nachtabsenkung & Optimal-Start | Implementiert |
| [0026](ADR-0026-Schatten-Schaetzer-immer-rechnen.md) | Schatten-Schätzer — intern immer rechnen, extern nur Vorrang | Implementiert |
| [0027](ADR-0027-Norm-Compliance-Grenzwerte.md) | Norm-Compliance — unkonditionale Sollwert-Grenzen (ASR A3.5) | Implementiert |
| [0028](ADR-0028-Seasonless-Rate-EKF-Prior.md) | Seasonless-Rate als EKF-Cold-Start-Prior | Implementiert |
| [0029](ADR-0029-Generische-Geraete-Quirks.md) | Generische Geräte-Quirks (devices/model_fixes) | Implementiert |
| [0030](ADR-0030-Anti-Garbage-In-Sensorplatzierung.md) | Anti-Garbage-In — Erkennung falscher Sensorplatzierung | Implementiert |
| [0031](ADR-0031-Coordinator-Refactor-Pure-Extraktion.md) | `_run_once`-Refactor — pure Extraktion statt UseCase-Klassen | Implementiert |
| [0032](ADR-0032-Closed-Loop-Harness-Validierung.md) | Closed-Loop-Validierung des prädiktiven Kerns im Harness | Implementiert |
| [0033](ADR-0033-MPC-Live-Verdrahtung-Shadow.md) | MPC Live-Verdrahtung — Stufe 1 (Shadow) | In Arbeit (70 %) |
| [0034](ADR-0034-Optimal-Stop-Coast.md) | Optimal-Stop — vorausschauendes Ausrollen (Coast-down) | Implementiert |
| [0035](ADR-0035-Praezedenz-Constraint-Solver.md) | Präzedenz-expliziter Constraint-Solver (ADR-0013 Stufe 1) | Implementiert |
| [0036](ADR-0036-TPI-Direktventil-TRVZB.md) | TPI-Direktventilansteuerung (Sonoff TRVZB-Klasse) | In Arbeit (70 %) |
| [0037](ADR-0037-PI-Setpoint-Kompensator-Shadow.md) | PI-kompensierter Sollwert (Shadow) für setpoint-only-TRVs | In Arbeit (65 %) |
| [0038](ADR-0038-Mehrzonen-Hub-und-Zwei-Phasen-Tick.md) | Mehrzonen-Hub & Zwei-Phasen-Tick | Implementiert |
| [0039](ADR-0039-Kesselbedarf-Aggregat.md) | Kesselbedarf-Aggregat (Heizquellen-Synchronisation) | Implementiert |
| [0040](ADR-0040-Bedienkarte-gebuendelt-und-autoregistriert.md) | Bedienkarte — eigene Lit/TS-Card, gebündelt & auto-registriert | Implementiert |
| [0041](ADR-0041-Fenster-Auto-Erkennung-Slope-und-Bypass.md) | Fenster-Auto-Erkennung per Temperatur-Slope + Bypass | Implementiert |
| [0042](ADR-0042-Override-Modus-Modell-mit-Auto-Rueckkehr.md) | Override-Modus-Modell — Kategorie/Offset mit Auto-Rückkehr | Implementiert |
| [0043](ADR-0043-Praediktive-Solar-Verschattung.md) | Prädiktive Solar-Verschattung (Cover-Shading) | In Arbeit (60 %) |
| [0044](ADR-0044-Outcome-Scoring-ts-vs-obs.md) | Outcome-Scoring — ts-vs-obs-Selbstvalidierung | Implementiert |
| [0045](ADR-0045-Effizienz-Report-HDH-kWh-Euro.md) | Effizienz-Report — Heating-Degree-Hours → kWh/€ | Implementiert |
| [0046](ADR-0046-Multi-Aktor-Arbitrierung.md) | Mehrere Klimaaktoren je Raum — Arbitrierung (thermisch/Feuchte/Lüften) | In Arbeit (30 %) |
| [0047](ADR-0047-Aussen-Lockout-Konfigurierbar.md) | Konfigurierbarer Außen-Temperatur-Lockout (Heizen/Kühlen) | Implementiert |
| [0048](ADR-0048-Abgrenzung-Luftqualitaet-und-Hygiene.md) | Abgrenzung Luftqualität & Hygiene (Nicht-Ziele); Nachträge 0027/0046 | Implementiert |
| [0049](ADR-0049-Card-Monitoring-Ampel.md) | Card-Monitoring-Ampel (Temp/Feuchte/CO₂) + optionaler CO₂-Sensor (Anzeige) | In Arbeit (75 %) |
| [0050](ADR-0050-Feuchte-Management-Dry-Pfad.md) | Feuchte-Management — Dry-Guard + aktive Entfeuchtung (shadow-first) | In Arbeit (85 %) |
| [0051](ADR-0051-Thermoschock-Delta-Hitzetag-Kuehlband.md) | Thermoschock-Delta & Hitzetag-Kühlband (adaptiver Kühl-Sollwert) | In Arbeit (80 %) |
| [0052](ADR-0052-Aktor-Dynamik-Profile.md) | Aktor-Dynamik-Profile — Regler-Zeitkonstanten je HVAC-Typ (PI/MPC) | In Arbeit (85 %) |
| [0053](ADR-0053-Leerlauf-Belegt-Luefterumwaelzung.md) | Leerlauf-/Belegt-Lüfterumwälzung (Fan-Low im besetzten Totband) | In Arbeit (40 %) |
| [0054](ADR-0054-PMV-PPD-Behaglichkeitsbewertung.md) | PMV/PPD-Behaglichkeitsbewertung (ISO 7730) — Diagnose + begrenzter Offset | In Arbeit (35 %) |
| [0055](ADR-0055-Regelguete-Metrik-Control-Accuracy.md) | M1 Regelgüte-Metrik (EN 15500-1 CA) — Komfortabweichung + Pendel-Detektor als Flip-Gate | In Arbeit (40 %) |
| [0056](ADR-0056-Referenzrahmen-Abgleich-Aktor-Raum.md) | Referenzrahmen-Abgleich Aktor-Interntemperatur ↔ Raumfühler (Offset-Kompensation self-regulating) | In Arbeit (25 %) |
| [0057](ADR-0057-Card-Layout-Konfiguration.md) | Card-Layout & Konfiguration (Dichte, Bedienung dial/buttons/none, Abschnitte, Schimmel-Tick, UI-Editor) | Implementiert (v0.138.0) |
| [0058](ADR-0058-Presence-Kopplung.md) | Presence-Kopplung — hierarchische Belegung (Haus-Gate + Raum-Eco) | In Arbeit (70 %) |
| [0059](ADR-0059-Override-Lebenszyklus.md) | Override-Lebenszyklus — Gültigkeit, Rückkehr, Feedback, L1-Erfassung (manuelle Eingriffe) | Implementiert (v0.163.0) |
| [0060](ADR-0060-Override-Vorschlags-Lernen.md) | Override-Vorschlags-Lernen (L2) + Modus-Saison-Hinweis | Vorgeschlagen |
| [0061](ADR-0061-Kuehlkante-Anwesenheit-vs-FreeRunning.md) | Kühlkante — fest bei Anwesenheit, adaptiv nur free-running | Implementiert (v0.165.0) |

## Umsetzungsstand (gegen Code verifiziert)

**Live/implementiert:** Datenverträge & Architektur (0005/0006/0031), EKF-Lernen & Identifizierbarkeit (0002/0024), Solar-β_s (0010), Komfort-Dual-Setpoint als **Live-Writer** (0023), Norm-Grenzen (0027), Zeitplan/Optimal-Start + Coast (0025/0034), Schatten-Schätzer-Politik (0026), Seasonless-Prior (0028), Geräte-Quirks/Anti-Garbage-In (0029/0030), Constraint-Solver (0035), Mehrzonen-Hub + Kessel-Opt-in-Aktuierung (0038/0039), Card (0040), Fenster-Slope (0041), Override (0042), Diagnostics/Repair (0012), Determinismus/Harness/CI (0014/0011/0032).

**In Arbeit — prädiktiver Kern läuft durchgängig als Shadow** (berechnet & diagnostisch ausgegeben, schreibt aber den Aktor **nicht**, aktiv gated auf Kaltsaison-Validierung): MPC-Solver & Live-Verdrahtung (0001/0009/0033), TPI-Direktventil (0004/0036), PI-Sollwert-Kompensator (0037), prädiktive Verschattung (0043). Mehrzonen-Shedding/Vorlauf/Verdichter (0013) ist teils Shadow. Querschnittsthemen teilweise offen: Migration/Deprecation (0007/0018), Config-Auto-Discovery (0008), Performance-Budget (0020), i18n-Vollständigkeit (0021), anonymisierter Export (0022).

**Befund (Ehrlichkeit, Stand v0.163.0):** Die frühere Warnung zu **ADR-0044/0045** ist erledigt — beide sind seit v0.97.0 im Coordinator verdrahtet (Outcome-/Savings-Diagnose live) → „Implementiert". **ADR-0046 (Multi-Aktor)** ist über P0–P2 (Thermal-Shadow + Per-Device-Lifecycle) plus **live** Verdichterschutz (§8, v0.141) fortgeschritten → „In Arbeit (30 %)". Neu als Shadow-Messschicht (berechnet/diagnostisch, keine Writes, gated): Regelgüte-Metrik (0055), PMV/PPD (0054), Referenzrahmen-Offset inkl. Laufzustands-Konditionierung (0056), Aktor-Dynamik-Profile (0052), Feuchte/Thermoschock (0050/0051). **ADR-0019 (KNX-Expose)** weiter nicht begonnen (P2/optional) → „Vorgeschlagen".

## Verifizierungs-Notizen (Wettbewerber, in ADRs eingearbeitet)

- **Versatile** zieht ungepinnte numpy/scipy, die der Komponenten-Code **nie** direkt importiert (nur transitiv über `vtherm_api`) → Anti-Pattern (ADR-0022).
- **ThermoSmart**-Export-Anonymisierung (gesalzener SHA-256) = Goldstandard; Restschwäche: Timestamps bleiben (ADR-0022).
- **RoomMind**-Diagnostics dumpt Personen-IDs/Skript-Pfade **ungeschwärzt** (kein `async_redact_data`) → Redaktion ist Pflicht (ADR-0022).
- Sprachen: ThermoSmart **24**, Versatile/BT **10**, RoomMind/Vesta **2** (ADR-0021).
