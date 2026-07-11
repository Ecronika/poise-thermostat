# ADR-0047: Konfigurierbarer Außen-Temperatur-Lockout (Heizen/Kühlen)

**Status:** Implementiert · **Datum:** 2026-06-27 · **Bezug:** ADR-0023 (Außen-Gating), ADR-0041 (Fenster), ADR-0008 (Config/Defaults), ADR-0046 (Free-Cooling) · **Verifizierung:** Wettbewerber-Code (RoomMind/dual_smart/VTherm/BT/climate_group/Adaptive Climate) + Nutzer-Feedback, zusammengefasst in `Meinungsbild_Fenster-Kuehlen-Aussen-Lockout.md`

## Kontext
ADR-0023 übernahm RoomMinds symmetrisches Außen-Gating als **feste Designkonstanten** in `control/cooling.py:decide_mode` (`cool_min_outdoor = 16 °C`, `heat_max_outdoor = 22 °C`) und führte ausdrücklich nur **drei** Config-Werte ein (`comfort_base`, `climate_mode`, `comfort_weight`) — die Lockouts sind **nicht** einstellbar. Auch ADR-0008 (Config-Schema/Defaults) nennt sie nicht. Problem: **lastdominierte Räume** (Sonnenraum West/Süd, Küche, Technik-/Server-/Grow-Raum, Dachgeschoss, Büro mit Geräten) brauchen Kühlung **trotz kühler Außenluft**; ein fixer 16-°C-Kühl-Lockout sperrt sie aus. Der eigentliche „nicht gegen Außenluft konditionieren"-Schutz ist ohnehin **Fenster→`off`** (ADR-0041, `tick_resolve.py:resolve_write_target`), nicht der Wetter-Proxy.

## Entscheidungstreiber
Korrektes Verhalten für interne-Last-Räume; keine Regression im Allgemeinfall; Normtreue/Effizienz (kein Verdichter, wenn frei kühlbar); Wettbewerbs-Parität; minimale Erst-Abfragen (Defaults setzen, nicht fragen — G16/G19, ADR-0008).

## Betrachtete Optionen (mit Quelle)
1. **Status quo (hartcodiert 16/22).** Verwirft die belegte Setup-Klasse lastdominierter Räume.
2. **Konfigurierbar, Default 16/22, richtungsgetrennt, deaktivierbar.** Code-Beleg RoomMind: `DEFAULT_OUTDOOR_COOLING_MIN = 16` („Hard block: NEVER cool if outdoor < this") / `DEFAULT_OUTDOOR_HEATING_MAX = 22`, konfigurierbar über Settings, richtungsgetrennt. — **gewählt.**
3. Default gleich niedriger/aus. Verliert die sinnvolle Allgemein-Leitplanke (in Räumen ohne interne Last verhindert der Lockout unnötiges Kühlen bei kühlem Wetter).
4. Lockout durch echte **Free-Cooling-Verfügbarkeit** ersetzen (Adaptive-Climate-Muster: HVAC-off bei passender Außenluft + Feuchte-Check). Braucht einen steuerbaren Außenluft-Aktor (Fan/KWL/Bypass), den der Bestandsfall nicht hat → gehört in **ADR-0046**, nicht hierher.

## Entscheidung
1. `cool_min_outdoor` und `heat_max_outdoor` werden **per-Zone konfigurierbare Optionen** (Options-Flow, unter „Erweitert").
2. **Begründete Defaults `16 °C` / `22 °C`** (aus ADR-0023/RoomMind, jetzt explizit dokumentiert statt still hartcodiert).
3. **Deaktivierbar** (Wert leer/aus) → „kühle bzw. heize **unabhängig** von der Außentemperatur" für lastdominierte Räume.
4. **Richtungsgetrennt** (Kühl- und Heizgrenze unabhängig einstellbar).
5. Festgehalten als Richtung: **Fenster→`off` (ADR-0041) ist der maßgebliche „nicht gegen Außenluft"-Schutz**; der Außen-Lockout ist eine **optionale Effizienz-Leitplanke**, kein Sicherheits-Feature. Der **Geräte-Eigenschutz** (AC-Mindest-Außentemperatur fürs Kühlen) bleibt Sache der AC-Firmware.
6. **Free-Cooling** (außenluftbasiert, feuchte-/enthalpie-bewusst) bleibt **ADR-0046** und greift nur mit steuerbarem Aktor.

Umsetzung: die reine `decide_mode` nimmt `cool_min_outdoor`/`heat_max_outdoor` bereits als Parameter an; es bleibt **Glue** — `CONF_*`-Keys + `DEFAULT_*` in `const.py`, Felder im Options-Flow, Durchreichen `coordinator → comfort.decide → decide_mode`. Test-first.

## Begründung
RoomMind — laut Wettbewerbs-Analyse der stärkste Mitbewerber — fährt exakt diese konfigurierbare, richtungsgetrennte Lösung; die vier anderen geprüften Regler (dual_smart, VTherm, climate_group, Better Thermostat) haben **gar keinen** Außen-Kühl-Lockout. Das Nutzer-Feedback belegt eine ganze Setup-Klasse (interne/solare Lasten), die ein fixer Wert nachweislich fehlsteuert; Serverraum-Nutzer erwarten ausdrücklich keinen Außen-Kühl-Lockout. Der Default 16/22 hält den Allgemeinfall unverändert: in Räumen ohne interne Last steigt die Raumtemperatur bei <16 °C Außenluft selten über die Kühlkante, der Lockout beißt dort praktisch nie.

## Konsequenzen
**Positiv:** löst lastdominierte Räume ohne Workaround; Wettbewerbs-Parität (RoomMind); die früher stille Konstante wird auditierbar; keine Verhaltensänderung bei Default. **Negativ/Kosten:** zwei neue Optionen (UI-Fläche — über Progressive Disclosure/`advanced` gering gehalten, ADR-0008/0046-R3); der Default 16 kann im Grenzfall (mildes Wetter **und** interne Last) ohne Anpassung noch sperren → Onboarding-/Doku-Hinweis „bei lastdominierten Räumen Kühl-Lockout senken/aus".

## Verifizierung
Test-first umgesetzt + grün: `control/cooling.py:decide_mode` ist `float | None`-fähig (None = Lockout aus); `comfort/dual_setpoint.py:decide` reicht `cool_min_outdoor`/`heat_max_outdoor` durch; `const.py` (`CONF_*`/`DEFAULT_*_C` = 16/22); `coordinator.py` (Init + Hot-Apply `async_apply_options` + Durchreichen an `comfort_decide`); `config_flow.py` Options-Feld (Erweitert, NumberSelector, `cool_min` −30…30 / `heat_max` 0…45); strings/en/de-Labels. **Tests:** `test_cooling.py` (`test_configurable_cool_lockout`, `test_configurable_lockout_is_direction_separated`) + `test_dual_setpoint.py` (`test_configurable_cool_lockout_threads_through`, inkl. Default-16/22-Regression) — **20 Pure-Tests grün**. `ruff check` + `ruff format --check` + `mypy --strict` auf allen editierten Dateien (cooling/dual_setpoint/const/config_flow) sauber.

**Version 0.90.0 + Card-Lockstep umgesetzt:** `const`/`manifest`/`pyproject`/`card/package.json`/README-Badge = 0.90.0; **Card neu gebaut** (`node build.mjs` → `frontend/poise-card.js`: Banner + `CARD_BUILD_VERSION` = 0.90.0, 0× „0.89.0"); **Card-Gate grün** (`tsc --noEmit` sauber + `node --test`: 14/14). Damit sind alle vier Versionsquellen + Bundle konsistent (kein v0.85-Mismatch).

*Sandbox-Vorbehalt (ehrlich):* Der voll-paketige `mypy` über `coordinator.py` und die HA-Runtime-Integrationstests laufen in CI (die OneDrive-Dehydrierung der Sandbox verhinderte den /tmp-Voll-Gate; die `coordinator.py`-Änderung ist rein mechanisch — zwei `float`-Config-Reads + Durchreichen).

## Compliance
Methode generisch (Außen-Schwellwert je Richtung), eigenständig umgesetzt; kein geräte-/herstellerspezifischer Sonderweg im Kern (G29/G30).

## Verknüpfungen
**Erweitert ADR-0023** (macht dessen feste Gating-Werte konfigurierbar); **ADR-0008** (Config-Schema/Defaults); **ADR-0041** (Fenster = eigentlicher „nicht gegen Außenluft"-Schutz). **Abgegrenzt:** feuchte-bewusstes Free-Cooling, `fan_only`-Fensteraktion und Verdichter-Min-Run/Off sind in **ADR-0046** (bzw. ADR-0041) verortet, nicht hier — Begründung siehe Meinungsbild. Quelle/Beleg: `Meinungsbild_Fenster-Kuehlen-Aussen-Lockout.md` (Projekt-Arbeitsstand).

## Nachtrag (v0.161): Deaktivierung über richtungsgetrennte Enable-Toggles
Die in Punkt 3 zugesagte Deaktivierbarkeit (`None` = Lockout aus) wird **nicht** durch Leeren des Zahlenfelds realisiert, sondern über zwei richtungsgetrennte Schalter `heat_lockout_enabled` / `cool_lockout_enabled` (Default: an). Steht ein Schalter auf „aus", reicht der Coordinator für die betreffende Richtung `None` an `decide_mode` durch — der Schwellwert bleibt als sichtbarer Zahlenwert erhalten (eine 0 im Feld wäre nur ein verwirrendes Fast-Aus, kein echtes Aus). So ist die Außen-Grenze je Richtung eindeutig ein- oder ausschaltbar, ohne den konfigurierten Wert zu verlieren.
