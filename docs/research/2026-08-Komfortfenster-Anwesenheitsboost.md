# Meinungsbild: Komfortfenster & Anwesenheits-Boost (Bad-Fokus)

**Datum:** 2026-08-09 · **Anlass:** Bad-Lückenanalyse (Nutzung bimodal morgens/abends, ein einziges Poise-Komfortfenster erzwingt heute 17-h-Dauerkomfort oder Handarbeit) · **Methode:** Web-Recherche HA-Community, deutschsprachige Smart-Home-/Haustechnik-Foren (homematic-forum, KNX-User-/Professionals-Forum, ELV), Hersteller-Dokumentation (tado, Homematic IP, Controme, Loxone) · **Zweck:** Entscheidungsbasis für den Zuschnitt „Mehrfach-Zeitfenster vs. präsenzgeführtes Heizen" (Folge-ADR).

## 1. Befunde je Cluster

### 1.1 Home-Assistant-Community

- **Mehrfach-Zeitfenster pro Tag ist die Grunderwartung.** Die dominante Community-Lösung ist die Scheduler-Card/-Component mit „Scheme"-Modus (beliebig viele Temperaturblöcke pro Tag); verbreitete Eigenbauten fahren 7-Tage-Pläne mit bis zu 8 Slots/Tag. Das Bad wird in Threads ausdrücklich als *der* Fall genannt, den Home/Away-Presets nicht abdecken: „bathroom cool most of the day, only warm in the evening for showering".
- **Feature-Requests an `generic_thermostat`** verlangen seit Jahren integrierte Schedules — die Erwartung ist, dass ein Thermostat-Feature Zeitpläne mitbringt, statt sie an externe Automationen auszulagern.
- **Präsenz-Heizen wird diskutiert, aber differenziert:** Muster ist „heizen, wenn belegt UND unter Schwelle" für *schnelle* Aktoren (Panel-/Elektroheizer). Für Bad-Belegung ist das Sensorik-Problem bekannt: Bewegungsmelder verlieren stille Personen (Wanne, Dusche hinter Glas) — die Community-Antwort sind „Wasp-in-Box"-Konstrukte (Tür-zu + Bewegung = belegt halten) und multisensorische Occupancy-Aggregation (Area Occupancy Detection u. ä.), teils mit Feuchte als Verlängerungssignal fürs Licht — exakt das Co-Signal-Muster, das Poise mit dem RH-Spike bereits besitzt.

### 1.2 Kommerzielle Systeme (tado, Homematic IP, Netatmo-Klasse)

- **Homematic IP: bis zu 6 Heizphasen pro Tag, drei Wochenprofile.** Multi-Phasen-Zeitprofile sind dort Standard und werden für Bäder genau bimodal genutzt (Morgen-/Abendphase). Dokumentierter Frust: Es fehlt eine „heize für x Stunden"-Funktion — Nutzer behelfen sich mit Alexa-Befehlen und Skript-Krücken für den spontanen Bad-Boost.
- **tado: Zeitblöcke (Smart Schedule) + Boost-Taste (30 min) + Geofencing.** Geofencing ist Haus-Ebene (Home/Away via Handy-GPS), *kein* Raum-Präsenz-Heizen; der Boost ist die manuelle Sofort-Antwort. Die Kombination „Plan + Boost + Anwesenheit als Haus-Gate" ist der kommerzielle Konsens — Raum-Melder-geführtes Heizen bietet praktisch kein Massenprodukt.

### 1.3 KNX / Profi-Haustechnik

- **Das kanonische KNX-Muster ist Betriebsmodus-Umschaltung:** Zeitschaltuhr liefert das Grundprofil (Komfort/Standby/Nacht), der **Präsenzmelder schaltet bei Belegung Standby → Komfort** und fällt nach Ablauf zurück — Präsenz ist *Modifikator des Zeitplans*, nie sein Ersatz. Genau so beschreiben es RTR-Applikationen (Gira/ABB/Merten) und die Forumspraxis („wie schaltet ihr die Heizung von Standby auf Komfort?").
- **Trägheits-Konsens:** Im KNX-Professionals-Forum sind sich „fast alle einig", dass Fußbodenheizung **zu träge** für Präsenz-Heizen ist — Standard dort sind **2–3 Zeitzonen je Raum**. Präsenzsteuerung gilt als sinnvoll für schnell reagierende Heizkörper (Bad!) und wird von Systemen wie Controme explizit so vermarktet (Präsenz senkt ab/hebt an, Profil bleibt Rückgrat).

## 2. Präferenz-Synthese (als Entscheidungsbasis)

- **P1 — Zwei bis drei Komfortfenster pro Tag sind Marktstandard und Grunderwartung** (Homematic 6 Phasen, Scheduler-Card n Slots, KNX 2–3 Zeitzonen). Ein einzelnes Fenster ist die eigentliche Anomalie.
- **P2 — Präsenz ist Modifikator, nicht Ersatz des Zeitplans** (KNX-Kanon): Belegung hebt aus Standby in Komfort bzw. verlängert Komfort; das Zeitprofil bleibt wegen Vorheiz-Planbarkeit das Rückgrat. Niemand Ernsthaftes plant „heizen erst, wenn jemand drinsteht" für träge Systeme.
- **P3 — Trägheit entscheidet über den Präsenz-Nutzen:** schnelle Aktoren (Heizkörper, Elektro/Panel) ja; FBH nein. Ein Präsenz-Feature muss dynamikbewusst gegatet sein.
- **P4 — Ein manueller, getimter Boost ist die erwartete Sofort-Bedienung** (tado 30 min, Homematic-Wunsch „für x Stunden") für Nutzung außerhalb jedes Plans.
- **P5 — Bad-Belegung braucht mehr als PIR:** stille Belegung (Dusche/Wanne) verliert Bewegungsmelder; Tür-Logik („Wasp in Box") und Feuchte-Signale sind die akzeptierten Co-Signale.

## 3. Poise-Ist-Abgleich — **korrigiert 2026-08-09** (Code- + Recorder-Verifikation)

> **Korrektur:** Die ursprüngliche Fassung dieses Abschnitts behauptete, Presence-**Trigger** existiere bereits („Raum belegt → Komfortband gilt auch außerhalb des Fensters", empirisch ≈22:15 am 2026-08-08). Beides ist **falsch**. Code (`_stage_presence_level`: `occupied = sched.is_comfort or preheating`; `resolve_presence`: ROOM_ECO nur bei `is_comfort`) und Recorder (2026-08-08 20:17–22:41: `heat_sp` durchgehend **20,6**, nicht 24 — die Nacht-Kanten 22:41/23:00 sind free-running-/Schimmel-Floor-Bewegungen des Sommer-Regimes, kein Presence-Effekt) zeigen übereinstimmend: **Außerhalb des Komfortfensters hat Raum-Belegung keinen Einfluss auf das Band.** Die ≈22:15-Beobachtung hatte die EN-Band-Anzeige (`comfort_low/high` 24–26) mit den geschriebenen Sollwerten verwechselt.

- **Presence-Extend existiert** (ADR-0058-Occupancy-Schiene, nur **innerhalb** des Komfortfensters): Belegung hält das volle Band; erst nach `absence_after_min` (Bad: 30) Raum-Leere sinkt es flach um `eco_delta` (ROOM_ECO); Rückkehr stellt den Komfort **sofort** wieder her. Das ist der „Komfort-Nachlauf" — PIR-Lücken-fest.
- **Presence-Trigger existiert NICHT:** Das KNX-Standby→Komfort-Muster (P2 — Belegung außerhalb des Zeitprofils hebt auf Komfort) ist in Poise **nicht gebaut**; nachts gilt der Setback unabhängig von Raum-Belegung (nur Frost-/Schimmel-Floors halten dagegen; im Sommer das free-running-Band). Wer spontane Abend-Nutzung abdecken will, nutzt heute Boost/Override oder ein weiteres Komfortfenster.
- **Boost existiert** (Boost-Preset, konfigurierbare Dauer; Override-Timer-Policy) → P4 erfüllt.
- **Dynamik-Profile existieren** (ADR-0052 fast_air/slow_hydronic/very_slow) → das P3-Gate ist vorhanden; da es keinen reaktiven Trigger gibt, stellt sich die FBH-Trägheitsfrage nur für einen *künftigen* Trigger.
- **Echte Lücken:** (a) **nur EIN Komfortfenster** (P1 verfehlt) — geschlossen durch ADR-0070 (v0.187.0); (b) der Presence-**Trigger** (P2 außerhalb des Fensters) fehlt — offene Feature-Option, nicht Doku-Lücke; (c) kein Feuchte-Co-Signal für stille Belegung (P5) — dokumentierte Option (ADR-0058-Nachtrag N2).

## 4. Entscheidungsoptionen

- **Option A — Zweites (drittes) Komfortfenster** (`comfort_start_2/end_2`, pure schedule + Optimal-Start je Fensterstart): schließt P1, macht Morgen- UND Abendblock planbar/vorheizbar. Aufwand klein-mittel (Schedule pure + Config/i18n + Optimal-Start-Mehrtermin). *Kernstück.*
- **Option B — Presence-Schiene als Feature ausformulieren:** dokumentieren (README/ADR-0058-Nachtrag), `absence_after_min` als „Komfort-Nachlauf" beschreiben, optional RH-Spike als Belegungs-Co-Signal (Duschende hält Komfort trotz stillem Melder — Bausteine aus ADR-0066 vorhanden). Aufwand klein; der **Extend** (im Fenster) ist gebaut, der **Trigger** (außerhalb) nicht — er wäre ein eigenes, hier nicht beauftragtes Inkrement (siehe §3-Korrektur).
- **Option C — Gelernte Fenster (ADR-0060-Mechanik):** Nutzungszeiten aus Override-/Belegungsstatistik vorschlagen. Später; braucht Felddaten, ersetzt A nicht.

**Empfehlung:** **A + B zusammen** als ein Inkrement („Bad-Zeitprofil"): Das zweite Fenster liefert den planbaren Kern (P1) samt Optimal-Start, die dokumentierte Presence-Schiene die spontane Abdeckung (P2/P5) — zusammen genau das KNX-Kanon-Muster in Poise-Form. C als ADR-0060-Folgekandidat notieren.

## 5. Maintainer-Entscheidungen (2026-08-09, beantwortet)

1. **n Fenster im Datenmodell, progressive UI.** Datenmodell = Liste `comfort_windows` (praktisch unbegrenzt — Voraussetzung für spätere ADR-0060-Vorschläge, die Fenster direkt eintragen). UI nach dem n+1-Muster: Der Options-Dialog rendert alle *konfigurierten* Fenster plus genau EIN leeres optionales „weiteres Fenster (Start/Ende)"-Paar; ausgefüllt erscheint beim nächsten Öffnen Fenster n+1 plus ein neues leeres, geleert wird ein Fenster entfernt. Das ist im HA-Options-Flow machbar, weil das Schema bei jedem Öffnen aus der aktuellen Config gebaut wird — nie werden von Anfang an drei leere Fenster angeboten. Migration: bestehendes `comfort_start/end` = Fenster 1. Validierung: Überlappungen/Reihenfolge normalisieren (mergen oder abweisen — im ADR festlegen).
2. **Optimal-Start gilt, wenn aktiv, für ALLE Fenster** (jeder Fensterstart ist ein Vorheiz-Termin).
3. **RH-Belegungs-Co-Signal: nur als Option dokumentieren, nicht umsetzen** (Kandidat: Wiederverwendung der V5-Duschepisoden-Kante als „still belegt"-Halter).
4. **P3-Gate: kein hartes Gate.** Maintainer nutzt `actuator_dynamics: auto`; die Automatik klassifiziert das Bad (fernwärmegespeister wassergeführter Handtuchheizkörper, einzige Heizquelle) korrekt als **slow_hydronic** — Radiator-Klasse, für die der KNX-Konsens Präsenz-Hebung ausdrücklich als sinnvoll einstuft. Konsequenz: Presence-Extend bleibt für alle Klassen aktiv; lediglich dokumentarischer Hinweis, dass der reaktive Trigger bei `very_slow` (FBH) wirkungsarm ist.

## Quellen

HA-Community: [Multiple per Thermostat Schedules](https://community.home-assistant.io/t/multiple-per-thermostat-schedules/975718) · [Scheduler and thermostats](https://community.home-assistant.io/t/scheduler-and-thermostats/627685) · [Add schedules to generic thermostat (FR)](https://community.home-assistant.io/t/add-schedules-to-generic-thermostat/340092) · [Multi Zone Heating 7-day scheduling](https://community.home-assistant.io/t/multi-zone-heating-now-with-7day-scheduling/175719) · [Best practice motion sensor + heater](https://community.home-assistant.io/t/best-practice-for-motion-sensor-and-heater/773413) · [Best occupancy sensor for bathroom](https://community.home-assistant.io/t/best-occupancy-sensor-for-bathroom/113960) · [Area Occupancy Detection (Wasp in Box)](https://github.com/Hankanman/Area-Occupancy-Detection) — Kommerziell: [tado Quick Actions/Boost](https://support.tado.com/en/articles/4996736-what-are-quick-actions) · [tado V3+ Review (Geofencing)](https://www.choose.co.uk/guide/tado-smart-thermostat-v3-review/) · [homematic-forum: Bad via Alexa aufheizen](https://homematic-forum.de/forum/viewtopic.php?t=54776) · [homematic-forum: Lösung für Heizung im Bad](https://homematic-forum.de/forum/viewtopic.php?t=45423) · [Homematic IP Heizprofile (6 Phasen)](https://smarthomelabor.de/produkttests/https-smarthomelabor-de-produkttests-homematic-ip/) — KNX/Profi: [KNX-User-Forum: Standby→Komfort](https://knx-user-forum.de/forum/%C3%B6ffentlicher-bereich/knx-eib-forum/38137-wie-schaltet-ihr-die-heizung-von-standby-auf-komfort) · [KNX-Professionals: Präsenzmelder und FBH (Trägheit)](https://knx-professionals-forum.de/forum/showthread.php?1451-Pr%C3%A4senzmelder-und-Fu%C3%9Fbodenheizung=) · [Controme Präsenzmelder-Heizung](https://www.controme.com/heizungssteuerung-mit-praesenzmelder/) · [Gira RTR-Applikation (Betriebsmodi)](https://partner.gira.de/data3/21003410.pdf)
