# ADR-0060: Override-Vorschlags-Lernen (L2) & Modus-Saison-Hinweis

**Status:** In Arbeit (L2 + §2 umgesetzt, Emission opt-in bis §3-Tuning) · **Wirkung:** Live-D · **Datum:** 2026-07-12 · **Bezug:** ADR-0059 (Override-Lebenszyklus — liefert die L1-Statistik, auf der L2 aufsetzt; dort als „v2" abgegrenzt), ADR-0012 (Repair-Issues / Fix-Flow), ADR-0027 (Norm-Klemme), ADR-0042 (Offset-Modell), ADR-0008 (Config-Reconfigure-Pfad), ADR-0011 (Golden-Replay über Feld-Traces) · **Grundlage:** `docs/Meinungsbild_Manueller-Eingriff-Sollwert-und-Modus.md` (ThermoCoach/Nest-Zweiphasen-Prinzip, verifiziert 2026-07-11)

> **Warum ein eigener ADR:** ADR-0059 hat den Override-**Lebenszyklus** (Gültigkeit, Rückkehr, Feedback) als v1 vollständig implementiert und die L1-Statistik (beobachten, nicht lernen) bereits mitgeliefert. Der **Vorschlags**-Teil (L2) und der optionale **Saison-Hinweis** wurden dort ausdrücklich als v2 abgegrenzt („die Statistik-/Vorschlagsmechanik erhält bei Umsetzung von L2 einen Nachtrag oder Folge-ADR", ADR-0059 §7). Dieser ADR ist dieser Folge-ADR. Er ändert **nichts** am ausgelieferten v1-Verhalten.

## Umsetzungsstand (2026-08-03 — L2, test-first)

**Implementiert (L2 §1 + §3-Sequenzierung):** pures `control/suggestion.py` — `detect_override_pattern` (§1-Prädikat: ≥ 3 gleichgerichtete ≥ 0,5-K-Eingriffe derselben Schedule-Phase in 14 Tagen, (phase, direction)-Buckets, stärkster Bucket gewinnt, malformed Events übersprungen) mit den zwei ADR-Deutungen: Comfort-Phase → `comfort_base` ± 0,5 K; Setback-Phase aufwärts → `comfort_earlier` 30 min (Setback abwärts hat **keine** ADR-Deutung → still); `suggestion_suppressed` (Ablehnung unterdrückt exakt diesen Muster-Key 30 Tage, wall-clock-persistent: `UserControlState.suggestion_rejected_key/-_at`, Codec 34→36 Keys re-frozen). 9 pure Tests + Persistenz-Vertragstests.

**Shadow immer, Emission opt-in:** Die Erkennung läuft jeden Tick und publiziert `suggestion_kind/-_direction/-_value/-_evidence/-_suppressed` als Diagnose-Keys (Datenvertrag +5) — **die §3-Feld-Tuning-Runde bekommt ihre Would-be-Vorschläge damit auch bei abgeschalteter Emission.** Die Repair-Emission selbst (`coordinator._sync_suggestion_issue`, idempotent, Issue verschwindet mit dem Muster) ist am `override_suggestions`-Toggle gegated: jetzt im Options-Flow (Manuelle-Eingriffe-Sektion) sichtbar, **Default bewusst `False`** — bewusste Abweichung vom §1-Text („Default an"), bis die §3-Golden-Replay-Runde die Schwellen mit Falsch-Positiv-Rate ≈ 0 bestätigt hat; der Flip auf Default-an ist danach ein Einzeiler in `const.py` (dort begründet).

**Fix-Flow (neu: `repairs.py`, erste fixable Issues der Integration):** Menü Übernehmen/Ablehnen. **Übernehmen** schreibt sichtbar über `async_update_entry` (Reconfigure-Pfad, ADR-0008): `comfort_base` ± 0,5 K (geklemmt 16–26, Norm-Hülle greift ohnehin) bzw. `comfort_start` − 30 min (ohne konfiguriertes Fenster → Dismiss-Semantik); **zusätzlich stempelt auch die Annahme den 30-Tage-Cooldown** — die Alt-Evidenz bleibt in der L1-Statistik und würde das gerade übernommene Muster sonst sofort erneut vorschlagen (Ergänzung zu §1, im Code begründet). **Ablehnen** stempelt nur. i18n EN/DE (3 Issue-Texte mit Fix-Flow-Menü, Options-Feld). Suite 1205 grün, ruff check/format clean (mypy + HA-Runtime-Integrationstest: CI).

**§2 Modus-Saison-Hinweis (2026-08-03, test-first):** pures `season_mode_hint` in `control/suggestion.py` — „saisonwidrig" ist über die **zoneneigenen Lockout-Schwellen** definiert (ADR-0023: `heat_only` bei T_rm ≥ `heat_max_outdoor`, `cool_only` bei T_rm ≤ `cool_min_outdoor`), und **T_rm ist als mehrtägiges Laufmittel selbst die „dauerhaft"-Bedingung** — kein eigener Dwell-Timer, nur 1-K-Hysterese gegen Schwellen-Flattern (Anker transient in `DiagnosticsRuntime.season_hint_prev`; nach Neustart re-raist T_rm den Hinweis, solange er klar jenseits der Schwelle liegt). 4 pure Tests (beide Richtungen, Hysterese beidseitig, auto/kein-T_rm/Modus-Wechsel still). Glue: Diagnose-Key `season_hint` (Datenvertrag +1) + **nicht-fixbares** Repair-Issue (rein beratend — Poise stellt nie selbst um), gegated auf denselben `override_suggestions`-Toggle („dieselben Vertrauensregeln wie L2"), Issue verschwindet mit Saison- oder Moduswechsel; i18n EN/DE. Suite 1209 grün, ruff check/format clean.

**Offen:** §3 Golden-Replay-Tuning an Feld-Traces → danach Default-Flip; HA-Runtime-Integrationstests für Fix-Flow und Saison-Hinweis (CI); ADR-0067-F2-Kollisionsregel konsumiert künftig die publizierten `suggestion_*`-Keys.

## Kontext

Poises Grundsatz ist normativ (ADR-0059 §5): **manuelle Eingriffe sind Ausnahmen, keine Trainingssignale.** Kein Mechanismus verschiebt *still* die Komfortbasis, den Zeitplan oder Preset-Offsets. Der einzige quantitative Feldbeleg für Mehrwert (ThermoCoach: +12,4 % vs. Nests stilles Lernen) und Googles eigene Kurskorrektur sprechen aber dafür, aus wiederholten, gleichgerichteten Eingriffen einen **sichtbaren Vorschlag** abzuleiten — nie eine stille Änderung.

Die dafür nötige Datengrundlage existiert seit v0.162.0 (ADR-0059 §5, Stufe L1): eine pro Zone kontextgefilterte, persistierte Override-Statistik (Zeitpunkt, Richtung, `override_requested`-Delta zur effektiven Basis, Schedule-Phase, Presence-Level; AWAY/Urlaub/Fenster-offen markiert und ausgeschlossen; nur der Nutzerpfad zählt, nie eigene Writes; cap 50). Sie liegt heute rein diagnostisch in `build_diagnostics` — es fehlt die Auswertung.

## Entscheidungstreiber

- **Vertrauen vor Bequemlichkeit:** ein Vorschlag muss ablehnbar, abschaltbar und norm-geklemmt sein; nichts ändert sich ohne sichtbare Nutzerzustimmung.
- **Konservativ gegen Spam:** ein einzelner oder zweideutiger Eingriff darf nichts auslösen; die Schwellen brauchen eine Feld-Trace-Tuning-Runde, sonst Vorschlags-Müdigkeit.
- **Norm bleibt unumgehbar:** jeder angenommene Vorschlag bleibt durch ADR-0027/0035 geklemmt (Offset-Modell ADR-0042 §1) — Poises Alleinstellung.
- **Kein neues Regelrisiko:** L2 ist reine Auswertung + Repair-Flow; der Regelkreis (EKF/MPC/Solver) bleibt unberührt.

## Entscheidung

### 1. L2 — Vorschlagen (aus der L1-Statistik)

Erkennt die L1-Statistik ein **Mehr-Tages-Muster** — **≥ 3 gleichgerichtete Eingriffe von je ≥ 0,5 K in derselben Schedule-Phase innerhalb von 14 Tagen** (Nest-Patent-Zweiphasenprinzip, bewusst konservativ) — erzeugt Poise ein **Repair-Issue mit Fix-Flow** (ADR-0012):

- „Abends wurde 3× auf +1 K erhöht — Komfortbasis um 0,5 K anheben?" bzw.
- „Komfortfenster 30 min früher beginnen?" (wenn das Muster ein Vorzieh-Wunsch ist, aus der Schedule-Phase/Uhrzeit abgeleitet).

Regeln:

- **Vorschlags-Schrittweite ≤ 0,5 K bzw. ≤ 30 min**; das Ergebnis bleibt **norm-geklemmt** (ADR-0027), auch wenn das beobachtete Delta größer war.
- **Annahme** ändert die Config **sichtbar** über den Reconfigure-Pfad (ADR-0008) — kein stiller Write; der Nutzer sieht die neue Komfortbasis/Zeit.
- **Ablehnung** unterdrückt genau dieses Muster **30 Tage** (kein Wiedervorschlag).
- **Als Ganzes abschaltbar** über `override_suggestions` (Default an; die const liegt seit v0.162.1 latent bereit, aus der UI genommen). Löschen der Statistik löscht sie wirklich (Nest-Artefakt-Lehre).
- **Nie EKF/MPC:** die physikalischen Schätzer lernen weiterhin ausschließlich Physik; die CA-Metrik pausiert bei Override (Bestandsverhalten).

### 2. Modus-Saison-Hinweis (optional)

Ein rein **beratender** Repair-Hinweis, wenn ein Gerät dauerhaft auf einem saisonwidrigen festen Modus steht (z. B. `heat_only`, während das Außenmittel klar im Kühlregime liegt, oder umgekehrt) — analog zum HmIP-„MANU"-Hinweismuster. Kein Auto-Umschalten, keine Regelwirkung: nur „Dieses Gerät steht auf Nur-Heizen, obwohl gekühlt werden müsste — umstellen?". Abschaltbar; unterliegt denselben Vertrauensregeln wie L2.

### 3. Schwellen-Feld-Tuning

Die L2-Schwellen (3 Eingriffe / 0,5 K / 14 Tage / Schrittweiten) sind **Startwerte**. Vor der Live-Schaltung von L2 wird eine Tuning-Runde an echten Feld-Traces (ADR-0011 Golden-Replay) gefahren: Ziel ist eine Falsch-Positiv-Rate nahe null (kein Vorschlag aus Einzel-/Urlaubs-/Fenster-Eingriffen), belegt durch Replay über die aufgezeichneten Zonen.

## Konsequenzen

**Positiv:** aus wiederkehrenden Eingriffen wird ein sichtbarer, norm-geklemmter Vorschlag statt stiller Drift; Poise bleibt das einzige System, dessen Vorschläge die Norm nicht verlassen können; die L1-Datenbasis ist bereits vorhanden, sodass L2 rein additiv ist.

**Negativ / Kosten:** L2 braucht die Tuning-Runde, sonst Vorschlags-Spam (das dokumentierte Nest-Risiko); ein weiterer Repair-Flow + Reconfigure-Pfad; die Mustererkennung ist Zustandslogik über die Statistik (test-first, Golden-Replay). Reihenfolge: nach ausreichend Feld-Traces aus dem v1-Betrieb.

## Verifizierung (geplant)

- Pure Mustererkennung über die L1-Statistik: Schwellen-Prädikat (≥3/≥0,5 K/14 d/gleiche Phase) test-first; Einzel-/Away-/Fenster-Eingriffe lösen nie aus (Nest-Fehlerklasse).
- Repair-Fix-Flow (ADR-0012): Annahme → sichtbarer Reconfigure-Write, norm-geklemmt; Ablehnung → 30-Tage-Unterdrückung; Feature-Toggle greift.
- Golden-Replay über Feld-Traces (ADR-0011): kein Vorschlag aus Poise-eigenen Writes; Falsch-Positiv-Rate am realen Trace.

## Verknüpfungen

Setzt ADR-0059 fort (konsumiert dessen L1-Statistik `override_stats` und den Grundsatz „beobachten → vorschlagen → bestätigen, nie still"). Nutzt ADR-0012 (Repair-Issue-Fix-Flow), ADR-0008 (Reconfigure-Pfad als sichtbarer Write), ADR-0027/0035 (Norm-Klemme jedes Vorschlags), ADR-0042 §1 (Offset-Modell), ADR-0011 (Golden-Replay fürs Schwellen-Tuning). Berührt den Regelkreis (EKF/MPC/Solver) **nicht**.
