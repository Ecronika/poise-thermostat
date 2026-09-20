# ADR-0074: Lüftungs-Empfehlung als Episoden-Zustandsmaschine

**Status:** Vorgeschlagen · **Wirkung:** n.a. · **Datum:** 2026-09-17, Rev. 8 (Abgleich mit dem Ablaufdiagramm: Schritt 4C „verbleibende Gründe merken" war im Entwurf nicht abgebildet — `pending_reason` nachgezogen, §5e). Rev. 7 (externer Prüfbericht 18.09.2026: eingerasteter Schutzgrund bleibt erhalten; Eskalation als Ereignis außerhalb der Quoten vertraglich festgelegt; Episodenende immer auf `airing_done`; Fenster-Normalisierung als Integrationsvertrag; `inferred` → `entry_inferred`). Rev. 6 (Nachprüfung zu Rev. 5: `request_ttl` verfällt nur gegen ein bekannt geschlossenes Fenster; `unknown` ist keine Inferenz und `inferred` klebt nicht mehr an späteren Phasen; Invariante präzisiert). Rev. 5 (zweites externes Review: Nummer 0072 war belegt → **0074**; ADR-0041-Status korrigiert (Live-A, nicht Shadow); Öffnungsnachweis, Episodendecke, Eskalationsereignis, gespeicherte Dringlichkeit; §0 Leitplanke). Rev. 4 (drittes Review zu v2a: eine Anforderung darf nur bei bestätigt geschlossenem Fenster still enden; epistemischer Ausstieg richtig benannt; Cooldown dämpft die Klingel, nicht den Rat; Soak als eingechecktes Testmodul). Rev. 3 (zweites Review zu v2a: der aktuelle Rat schlägt das Fensterereignis in `requested`; der Zeitausstieg gilt nur bei unbeobachtbarem Kontakt und endet im Schutz-Cooldown; Prompt-Budget je Aufforderungsphase. Rev. 2: Ein-Gewinner-Schnittstelle als Blocker erkannt, sechs Übergangsfehler belegt — v2a auf reine Episodenlogik verengt) · **Bezug:** ADR-0066 (Feuchte-Achse — die Regeltabelle, unverändert), ADR-0066 N6/N7/N9 (die drei Flicken, die dieser ADR strukturell ablöst), ADR-0041 (Fenster-Auto-Erkennung per Slope + Bypass — **Implementiert · Live-A**, Quelle des inferierten Kontakts), ADR-0050 (Komfort vs. Gebäudeschutz), ADR-0048 (Monitoring vs. Control), ADR-0049 (Ampel/Karte), ADR-0069 (Vorbild: `fan_first_decision` als pure, zustandsbehaftete Mehrtick-FSM) · **Grundlage:** [Ablaufdiagramm Lüftungsempfehlung (Nutzerdarstellung, 2026-09-15)](../design/2026-09-Lueftungsempfehlung-Ablaufdiagramm.md)

## §0 Leitplanke (bindend für dieses Paket)

> **Gebaut wird der entworfene Ablauf und die dafür nötige Episodenlogik. Grenzwerte, Formeln und funktionaler Umfang der Regeltabelle bleiben unverändert — es sei denn, eine Änderung behebt zwingend einen Logikfehler.**

Dieses Paket fasst `comfort/ventilation.py` **nicht** an. Bewusst zurückgestellt, weil jede davon Schwellen oder Funktionsumfang änderte:

| Zurückgestellt | Warum es hier nicht hineingehört |
|---|---|
| CO₂-Hysterese (heute eine Schwelle, 1000 ppm) | Schwellwertänderung. CO₂ ist ohnehin inert — `phase_prepare.py` übergibt `co2=None` |
| CO₂-Rang gegenüber Feuchte und Freikühlen | Präzedenzänderung |
| `dry_critical` auf `dry_alert_gm3` (5,0 g/m³, heute totes Feld) | neue Regel |
| Harter Schließgrund gegen `mold_risk` | Präzedenzänderung im Gebäudeschutzpfad |
| `mold_risk` nur als Eintritts- statt Haltebedingung | Funktionsänderung |
| Entkopplung der Schließprädikate vom Fensterkontakt | Eingriff in die Tabelle — die Doppelhypothese (Folgepaket) löst dasselbe ohne Eingriff |

**Bekannte Restwirkung, bewusst offen:** Das Modul deckelt die *Meldungen*, nicht die Grundschwingung. `moisture_protect` hat an `rh_pct > rh_max_safe_pct` keine Hysterese — ADR-0066 führt das als offenen Kalibrierpunkt. Ein Raum auf seiner Schimmelgrenze lässt die Tabelle jeden Tick kippen; der wechselnde Rat bleibt auf der Karte sichtbar, nur die Benachrichtigungen sind begrenzt.

## Geltungsbereich der Nachweise

Alle Zahlen unten gelten für **diesen Entwurf**, nicht für `main`. Ausgangsstand ist Commit `261b14cf` (v0.194.7); `vent_episode.py` und die beiden Testmodule liegen dort noch nicht.

## Kontext

Die Regeltabelle in `comfort/ventilation.py` beantwortet pro Tick genau eine Frage: **welcher Grund trägt gerade?** Sie ist zustandslos, mit 58 Regressionsfällen gepinnt und physikalisch gut abgesichert (N4 Datentor, N5 doppelte Feuchtelinien, N7.1/N8.1 Bezugsrahmen, N7 `moisture_protect`, N9 Schutzboden).

Was ihr fehlt, ist die zweite Frage, die der Nutzer tatsächlich erlebt: **ist das eine Bitte, eine laufende Lüftung oder eine Bitte zu schließen?** Bisher wurde „läuft eine Episode von uns" jeden Tick aus dem Grund-Token des Vorticks plus dem Fensterkontakt *rekonstruiert*. Jede Ecke dieser Rekonstruktion musste einzeln repariert werden:

- **N6** (2026-09-14): Der Rat kippte am Fensterkontakt — geschlossen „öffnen", offen „schließen", im selben Tick. Behoben durch einen Rückzug des Wächters, solange eine eigene Episode läuft.
- **N6b**: „läuft" reichte nicht, die Episode musste auch noch *gültig* sein — ein zweites Prädikat.
- **N9** (2026-09-14): Dieselbe Inversion überlebte in der Ecke mit durchgreifendem Schutzboden, weil der Komfort-Eintritt seine eigene Meinung behielt. Drei Revisionen, weil kein Test die Kombination abdeckte.

Drei Flicken auf demselben Loch sind ein Strukturbefund, kein Testlückenbefund. Die gemeinsame Ursache: **die Information „ich habe darum gebeten" existiert nicht, sie wird geraten.**

Parallel dazu ist die heutige Empfehlung an drei Stellen ärmer, als sie sein müsste:

1. **Zonen ohne Fensterkontakt sind halb blind.** `window_open` ist ein Boolean und ohne Kontakt immer `False`, also können `mold_guard`, `thermal_floor`, `target_reached`, `cooled_off` und der schließende `too_dry`-Arm dort **nie** feuern. Diese Zonen bekommen Öffnungsräte, aber nie einen Schließrat. ADR-0041 hat die Slope-Erkennung live im Steuerungspfad liegen (ADR-0041, Live-A) und nutzt sie hier nicht.
2. **Es gibt keine Ruhezeit und keine Frist.** Ein Rat steht unbegrenzt; nach `target_reached` kann der nächste Tick sofort wieder öffnen raten, sobald Δ die Eintrittsschwelle streift.
3. **Ein einziger stiller Endzustand.** `no_gain` deckt vier grundverschiedene Situationen ab. Der Bad-Befund vom 14.09. ist, was das kostet: 66 % rF auf der Karte, kein Rat, und für den Nutzer nicht unterscheidbar, ob das System zufrieden, blockiert oder blind ist.

## Entscheidung

**Zwei pure Schichten statt einer.** `comfort/ventilation.py` bleibt **unverändert** — dieselbe Signatur, dieselben Token, dieselben 58 Tests. Darüber kommt `comfort/vent_episode.py`, eine pure, zustandsbehaftete Mehrtick-FSM nach dem Vorbild von `fan_first_decision` (ADR-0069 U4).

### 1. Die Phasen

```
idle ──Grund──> requested ──Fenster auf──> ventilating
  │                  │                          │
  │                  │ Grund weg                │ Grund weg / Schutz-Abbruch
  │                  ▼                          ▼
  │                idle                   stop_requested
  │                  ▲                          │ Fenster zu / Frist
  └──────── cooldown ┴──────────────────────────┘
```

Fenster bereits offen und ein Grund entsteht → direkt `ventilating` (wer schon richtig handelt, wird nicht gebeten). Fenster fremd geöffnet und ein Schließgrund trägt → direkt `stop_requested`.

### 2. Der Zustand ist gespeichert, nicht rekonstruiert

`EpisodeState(phase, reason, level, owner, episode_id, episode_prompts, protected, opened_seen, escalations, phase_min, prompts, unknown_dwell_min, entry_inferred, emergency, cooldown_for_min, cooldown_scope)` — persistiert pro Zone. `level` ist die Dringlichkeit des **veröffentlichten** Rates und wird mit ihm gespeichert, `opened_seen` die Öffnungsevidenz der Episode, `entry_inferred` die Evidenz, auf der die **aktuelle Phase betreten** wurde (nicht die laufende Beobachtung — die steht in `EpisodeResult.window_seen`). `owner` ist der Öffnungsgrund, der die Episode **gerade trägt** (er folgt einem Grundwechsel, weil `oracle_flags` den Hystereseanker des tatsächlich haltenden Grundes braucht), `prompts` zählt innerhalb der laufenden Aufforderungsphase. Daraus leitet `oracle_flags()` die `prev_*`-Eingänge der Regeltabelle ab. Damit stammen `prev_advice_active`, `prev_moisture_airing`, `prev_moisture_protect` und `prev_heat_out` aus **einem** Lesevorgang **einer** Phase statt aus dem zuletzt veröffentlichten Token — die Quelle der N6b-Drift entfällt.

**Die Invariante, die die Fehlerklasse schließt** — und sie muss genauer formuliert werden, als es zunächst dastand: **der Fensterkontakt allein invertiert nie den physikalischen Rat.** Eine laufende Episode endet ausschließlich über einen expliziten Zustandsübergang; ein erkanntes manuelles Schließen ist dabei ein legitimes Nutzerereignis und beendet sie sehr wohl. Die frühere Fassung („ein laufender Vorgang wird nie durch den Kontakt beendet") war zu absolut und beschrieb den Code nicht.

Ehrlich abgegrenzt: die FSM beseitigt nicht die *Zustandsabhängigkeit* der Empfehlung — bei geschlossenem Fenster „öffnen" und bei einem fremd geöffneten Fenster „schließen" zu raten, ist bei unterschiedlicher Physik auch unterschiedlich richtig. Sie beseitigt die **Rücknahme**: dass Poise bittet, der Nutzer folgt, und Poise im nächsten Tick widerspricht.

### 3. Gebäudeschutz ist von jeder Komfortmechanik ausgenommen

`PROTECTION_OPEN = (mold_risk, moisture_protect)`, `PROTECTION_CLOSE = (mold_guard, thermal_floor)`. **`too_dry` gehört ausdrücklich nicht dazu:** die Regel feuert bei 7 g/m³ bzw. 35 % rF — die gewöhnliche Trockenheitswarnung, kein Gefahrenzustand. Ein wirklich kritischer Trockenheits-Stopp gehörte auf die strengere `dry_alert_gm3`-Linie (5,0 g/m³, heute totes Konfigurationsfeld) und wäre eine Präzedenzentscheidung der Regeltabelle — also v2b, nicht dieses Paket. Für sie gilt:

- die Anfrage **verfällt nicht** (`request_ttl` gilt nur für Komfort),
- ein laufender Cooldown wird **sofort gebrochen**,
- ein Not-Abbruch (`stop_requested` mit `emergency`) endet nicht durch Fristablauf — nur durch ein bestätigtes Schließen oder den epistemischen Ausstieg aus §5b,
- das Erinnerungsbudget ist das große (6 statt 2) und gehört der **Episode**, nicht dem Grund dieses Ticks.

Das ist ADR-0050s Trennung von Komfort und Gebäudeschutz, auf die UX-Schiene übertragen. Ohne diese Ausnahmen wäre eine Ruhezeit ein Maulkorb für eine Warnung, von der die Bausubstanz abhängt.

### 4. Fensterzustand ist fünfwertig

`open | closed | likely_open | likely_closed | unknown`. Eine Zone ohne Kontakt ist **nicht geschlossen**, sie ist unbekannt — und `unknown` ist weder Öffnungs- noch Schließnachweis: es lässt keine Episode als *ausgeführt* gelten und beendet keine als *abgeschlossen*. Eine Anforderung kann sehr wohl bei `unknown` beginnen, und ein stehender Schließrat endet dort über den epistemischen Ausstieg (§5b). Ein inferierter Zustand wirkt für die Regeltabelle wie ein gemessener (die Physik eines offenen Fensters hängt nicht davon ab, wie wir davon erfahren haben), wird aber auf der Episode als `inferred` vermerkt, damit Konfidenz und Timeouts daran hängen können.

### 5. Fristen und Ruhezeiten

| Größe | Default | gilt für |
|---|---:|---|
| `request_ttl_min` | 15 | Komfortanfrage **bei bestätigt geschlossenem Fenster**; bei unbekanntem Zustand läuft nur das Prompt-Budget aus, nicht die Anfrage |
| `reminder_every_min` | 7 | alle |
| `max_prompts_per_phase` | 2 | Komfort, je Aufforderungsphase, Erstbitte eingerechnet |
| `max_prompts_per_phase_protection` | 6 | Gebäudeschutz |
| `cooldown_min` | 10 | regulär beendet — **grundbezogen** |
| `cooldown_manual_min` | 10 | Nutzer hat abgebrochen — global |
| `cooldown_expired_min` | 20 | Anfrage verfallen — global |
| `cooldown_emergency_min` | 45 | nach Not-Abbruch — global |
| `unknown_stop_release_min` | 5 | Haltezeit des epistemischen Ausstiegs (§5b), nur bei `unknown` |
| `max_tick_min` | 10 | Kappung der Tick-Lücke (Neustart) |

`max_tick_min` übernimmt die Lückenkappung der Regelgüte-Minuten: ein Neustart oder ein hängender Coordinator darf die Maschine nicht um Stunden altern lassen.

**Aktion und Klingel sind unabhängig.** `action` ist die Wahrheit, `prompt` die Türklingel. Ist das Prompt-Budget erschöpft, wird die Maschine still — aber ein Fenster, das geschlossen gehört, sagt das auf der Karte weiter. Ein `stop_requested` geht deshalb **nicht** mehr nach Fristablauf in `idle`.

**Ein regulär erreichtes Ziel ruht nur seinen eigenen Grund** (`cooldown_scope`). Eine erledigte Feuchteepisode darf einen unabhängigen CO₂-Anlass zwei Minuten später nicht schlucken; gegen das Flattern desselben Grundes schützt die Sperre weiter. Abbruch, Verfall und Not-Abbruch behalten die pauschale Ruhezeit.

**Eine Ruhezeit dämpft die Klingel, nicht den Rat.** Ein Cooldown unterdrückt neue Öffnungs-Anforderungen — dafür ist er da. Einen *aktuellen* Schließrat blendet er nicht aus: er erscheint weiter auf der Karte, nur ohne Benachrichtigung. Alles andere stünde quer zum Grundsatz „`action` ist die Wahrheit".

**Ein neuer gültiger Öffnungsgrund bricht einen gewöhnlichen Schließrat ab** und führt zurück nach `ventilating` — „Gründe dürfen wechseln" gilt auch über die Schließbitte hinweg. Ein eingerasteter Not-Abbruch wird so nie überstimmt.

### 5a. Der aktuelle Rat schlägt das Fensterereignis

In `requested` entscheidet **die Antwort dieses Ticks**, nicht die Anforderung, die der Nutzer gerade ausführt. Öffnet jemand das Fenster in demselben Tick, in dem eine Schutz-Schließregel wahr wird, geht die Maschine direkt nach `stop_requested` — ein minutenalter Öffnungswunsch darf einen aktuellen Schutzentscheid niemals überschreiben.

**Und eine Anforderung darf nur still enden, wenn das Fenster als geschlossen bekannt ist.** Das gilt für beide Enden einer Anforderung — den entfallenen Anlass **und** den Ablauf der Frist. Entfällt der Anlass, entscheidet das Fensterwissen:

| Fensterzustand | Ende der Anforderung |
|---|---|
| `closed` / `likely_closed` | → `idle`. Wir wissen: niemand hat gehandelt. |
| `open` / `likely_open` | → `stop_requested`. Wir wissen: es wurde geöffnet. |
| `unknown` | → `stop_requested`. Wir wissen es nicht — und das ist der Fall, für den dieses Modul gebaut wurde. |

Ebenso beim Verlassen von `stop_requested` durch einen neuen Öffnungsgrund: nach `ventilating` nur bei beobachtetem `open`/`likely_open`, bei `unknown` zurück nach `requested`. **Angefordert** und **beobachtet** sind zwei verschiedene Aussagen.

Die Asymmetrie ist Absicht: nur ein bestätigtes „zu" rechtfertigt Schweigen. Der Feldfall ist das Bad ohne Kontakt — Rat befolgt, Slope blind, Feuchte abgebaut; vorher verdunstete die Episode und ließ ein offenes Fenster ohne ein Wort zurück.

Läuft dagegen die **Frist** ab, während der Anlass noch trägt, gilt dasselbe Wissen mit anderem Ausgang: bei bestätigt geschlossenem Fenster verfällt die Anfrage, sonst **steht sie weiter**. Ein Ende zu raten wäre dort falsch (der Grund gilt ja noch), die Anfrage zu vergessen ebenso (das spätere Ende ginge verloren). Was ausläuft, ist das Prompt-Budget, nicht die Anfrage.

Publiziert wird dabei `close/airing_done` — **der einzige Token, den dieses Modul selbst besitzt**. Er behauptet ausdrücklich **nicht** `target_reached`: der Anlass kann auch durch Datenverlust oder einen Belegungswechsel verschwunden sein, und ein erreichtes Ziel zu behaupten wäre eine Aussage über Physik, zu der die FSM nicht befugt ist. Die Karte muss den Token lernen (Schritt 8).

### 5b. Der Zeitausstieg gilt nur, wo Poise nichts wissen kann

**Jede** Schließregel der Tabelle verlangt `window_open`, und ein unbekannter Kontakt wird ihr als `False` übergeben. Ohne Kontakt **kann** der Resolver also gar keinen Gefahrenzustand melden, was immer die Bauteile tun. Der Zeitausstieg aus einem stehenden Schließrat ist deshalb **epistemisch** („wir können es nicht erfahren"), keine Entwarnung — und er gilt ausschließlich bei `unknown`. Ein Kontakt, der OFFEN meldet, ist Wissen: dort verfällt ein `close` nicht, sondern bleibt stehen, bis das Fenster wirklich zugeht. Sonst wäre die Türklingel wieder Herr über die Wahrheit.

Benannt ist er entsprechend: `unknown_stop_release_min` und `unknown_dwell_min`, nicht „hazard clear" — die alte Benennung hätte einen späteren Leser eingeladen, daraus eine bauphysikalische Entwarnung abzuleiten. Weil beim Ausstieg unbekannt bleibt, ob je geschlossen wurde, endet er in einer **pauschalen** Ruhezeit, nicht in gewöhnlicher Beobachtung — 45 min nach einem Not-Abbruch, 20 min sonst (dieselbe Länge wie eine verfallene Anfrage: beides sind unbestätigte Enden). Grundbezogen ruhen darf **nur ein bestätigter** Abschluss; sonst entstünde der Abbruch-und-gleich-wieder-Öffnen-Zyklus, den die Ruhezeit verhindern soll.

Was ein einzelner Gewinner-Token *tatsächlich* beweisen könnte, ist weniger als es scheint: `idle` steht am Ende des Wasserfalls, aber `discourage`/`too_dry` überholt nur `mold_guard` — **nicht** `thermal_floor`, das die Tabelle erst danach prüft. Kein einzelnes Token belegt also die Abwesenheit beider Schutz-Schließgründe. Diesen Beweis zu liefern ist die Aufgabe der Evaluationsschicht (Schritt 2b).

### 6. Vier Stillen statt einer

`idle_cause` ∈ `all_good | outside_not_drier | fabric_heated | no_data | cooldown`. Abgeleitet aus denselben Eingängen, die die Regeln lesen, und bewusst **kein** neuer Token in `ventilation.py` — dessen Vokabular ist ein gepinnter Anzeige-Contract. `fabric_heated` ist die N9-Ecke, sichtbar gemacht: „der Raum ist über seiner Grenze, aber die Heizung verteidigt das Bauteil bereits — Lüften würde dagegen arbeiten".

### 5c. Was eine Fensterlesung beweist (Rev. 5)

Der Fünfwert-Zustand allein reicht nicht — es zählt auch, **woher** er kommt und **wie alt** er ist. ADR-0041 liefert dafür zwei konkrete Fallen:

* die Slope-Erkennung stellt ein Öffnen am Temperaturabfall fest, kehrt aber nach **Maximaldauer von selbst** auf „zu" zurück — das ist ein Timeout, keine beobachtete Schließung;
* ein Nutzer-**Bypass** zwingt das steuerungswirksame Signal auf „zu" — eine Anweisung, keine Beobachtung.

Daher: **ein offenes Signal ist Nachweis aus jeder Quelle, ein geschlossenes nur vom Kontakt.** Alles andere — und jede Lesung älter als `window_stale_after_min` — wird zu `unknown` abgewertet, wo die vorsichtigen Ausgänge gelten. `effective_window()` macht das an einer Stelle, `EpisodeResult.window_seen` veröffentlicht das Ergebnis, damit die Karte nicht das rohe Signal zeigt.

**Integrationsvertrag (bindend für die Naht):** normalisiert wird **einmal**, und dasselbe Ergebnis geht an `episode_step` **und** über `oracle_window_open` an die Regeltabelle. Andernfalls glauben die beiden Schichten Verschiedenes über dasselbe Fenster — eine veraltete Lesung wäre der Tabelle „offen" und der Maschine „unbekannt". `age_min` ist das Alter der **Lesung** (wann die Quelle diesen Wert zuletzt geliefert hat), nicht die Zeit seit dem letzten Zustandswechsel: ein Kontakt, der minütlich meldet, ist auch nach einer Stunde offenstehendem Fenster frisch.

Und ein laufendes Lüften wird nie ohne beobachtetes Öffnen behauptet: `opened_seen` ist Voraussetzung für `ventilating`. Ohne Nachweis fragt die Maschine erneut, statt eine Durchführung anzunehmen, die nie stattgefunden hat.

### 5d. Meldungen gehören der Episode (Rev. 5)

Die Quote je Aufforderungsphase wird durch Wiedereintritt ausgehebelt: ein Grund, der über seiner Schwelle flackert, läuft `ventilating → stop_requested → ventilating` und beginnt jedes Mal von vorn — gemessen **zehn Meldungen in einundzwanzig Ticks**. Darüber liegt jetzt eine Decke je **Episode** (`episode_id`, `max_prompts_per_episode` 4 bzw. 10), durch die **jede** Meldung geht, auch die Eröffnungsbitte einer Phase. Die Budgetklasse ist einrastend: hat Gebäudeschutz einmal gesprochen, gilt die größere Quote für den Rest der Episode.

**Eine Eskalation ist ein Ereignis, keine Erinnerung** — und liegt damit ausdrücklich **außerhalb beider Quoten**. Wechselt ein stehender Schließrat zu einem Schutzgrund, meldet er sich sofort; auf die Erinnerungsuhr zu warten hieße, eine Bauteilwarnung um Minuten zu verzögern. Begrenzt wird sie nicht durch einen Zähler, sondern durch den Latch selbst: sobald `emergency` gesetzt ist, ist jeder weitere Schutz-Schließrat eine Fortsetzung und keine Steigerung — eine Episode eskaliert also höchstens einmal. In einem Satz: **Quoten regeln Erinnerungen, eine Eskalation meldet sich immer genau einmal.**

**Ein eingerasteter Schutz-Stopp behält Grund und Dringlichkeit.** Ein gewöhnlicher Schließrat (`target_reached`, `cooled_off`, `too_dry`) darf sie nicht überschreiben — sonst bliebe der Latch gesetzt, während die Meldung harmlos klingt. Nur ein anderer Schutz-Schließgrund aktualisiert ihn.

**Ein entfallener Anlass endet in jeder Phase auf `airing_done`.** Ein ausdrücklicher Schließrat behält seinen eigenen Grund; alles andere — auch ein Datenverlust — endet auf dem neutralen Token. „Schließen / keine Daten" ist kein Grund, auf den ein Nutzer handeln kann, und genau für diesen Fall wurde das Token eingeführt.

**Aktion, Grund und Dringlichkeit werden gemeinsam geführt.** Ein eingerasteter `close/thermal_floor` übernahm bisher das `level` des Rates, den der Resolver gerade lieferte, und erschien dadurch als `ok`. Der gespeicherte Wert gilt.

### 5e. Was von einer Episode übrig bleibt (Rev. 8)

Das Ablaufdiagramm kennt in Schritt 4C einen Ausgang, den der Entwurf bis Rev. 7 nicht abbildete: **„Fenster geschlossen → verbleibende Gründe merken für spätere Empfehlung"**. Eine Episode endet aus *ihren* Gründen — das Fenster wurde von Hand zugemacht, eine Anforderung lief ab —, ob die **Luft** noch etwas braucht, ist eine davon getrennte Frage. Der Resolver beantwortet sie auf genau diesem Tick.

Beispiel aus dem Feld: bei 1400 ppm wird das Fenster zugemacht. Die Episode ist zu Ende, der Cooldown ist *gewollt* still (10 min) — aber von der Karte aus sieht diese Stille aus wie „Poise hat das Thema fallengelassen". Genau diese Lücke schließt `EpisodeState.pending_reason` / `EpisodeResult.pending_reason`.

Drei Eigenschaften machen das Feld gutartig, und alle drei sind als Invariante geprüft:

* **Es ist eine Notiz über die Ruhezeit, kein Episodengedächtnis.** `pending_reason` ist ausschließlich in `cooldown` gesetzt; in jeder lebenden Phase ist es leer. Eine Notiz in einer laufenden Phase wäre eine zweite, konkurrierende Quelle dafür, was gerade gewollt ist.
* **Es folgt dem Resolver, nicht der Uhr.** Jeder Cooldown-Tick schreibt es neu: `reason`, solange der Resolver weiter `open` sagt, sonst leer. Eine Notiz, die ihre Ursache überlebt, würde nach der Ruhezeit Lüften für Luft empfehlen, die längst in Ordnung ist — der einzige Fehlermodus, den dieses Feld erzeugen kann.
* **Es ändert kein Verhalten.** Die „spätere Empfehlung" entsteht bereits heute von selbst: nach Ablauf des Cooldowns liegt der Grund weiter an, `idle` beginnt eine neue Episode. Neu ist allein, dass die Wartezeit *erklärbar* wird — dieselbe Klasse wie `idle_cause` in §6, und damit innerhalb der Leitplanke aus §0.

**Bewusst nicht mitgemacht:** den Cooldown-Scope eines manuellen Schließens auf den gemerkten Grund zu verengen (`cooldown_scope=pending_reason` statt blanko). Das wäre inhaltlich verteidigbar, ist aber eine Verhaltensänderung, die das Diagramm nicht fordert — also §0. Die Anzeige gehört zu Schritt 8 (Karte).

## Was ausdrücklich NICHT geändert wird

Die Präzedenz der Regeltabelle, beide Feuchtelinien (N5), das regelindividuelle Datentor (N4), der 48-h-EWMA als Schimmelursache gegenüber dem Momentanwert als akutem Wächter, die Bezugsrahmen-Disziplin (N7.1/N8.1), die asymmetrischen Δ-Hysteresen, der Schutzboden-Ausschluss (N7/N9). Die FSM rechnet **keine** Physik; sie interpretiert nur die Antwort der Tabelle im Licht der Phase.

Die im Ablaufdiagramm gezeichnete Prioritätsreihenfolge (Bauteilschutz > CO₂ > Feuchte > Abkühlen) weicht von der heutigen ab (CO₂ steht unter Freikühlen und Feuchte). Das ist eine **offene Entscheidung**, kein Bestandteil dieses ADR — sie beträfe die Regeltabelle, nicht die Maschine, und wirkt praktisch nur auf den angezeigten Grund, weil alle vier dieselbe Aktion tragen.

## Nachweise

`tests/test_vent_episode.py`, 55 Fälle: die Nicht-Inversion, der Schutz-Abbruch, der volle Lebenszyklus, das bereits offene Fenster, das fremd geöffnete, die zurückgezogene Anfrage, der Grundwechsel innerhalb einer Episode, das manuelle Schließen, die vier Schutz-Ausnahmen, das Erinnerungsbudget, der inferierte und der unbekannte Kontakt, die vier Stillen, die übrig gebliebene Nachfrage aus §5e, die Ableitung der Orakel-Flags, die Tick-Kappung — und ein End-to-End-Fall, der den Schlafzimmer-Befund vom 14.09. durch **beide** Schichten fährt und über sechs Ticks nachweist, dass die Episode nicht kippt.

Dazu `tests/test_vent_episode_soak.py` — der Zustandsraum-Soak als **eingechecktes, deterministisches Testmodul** (fester Seed 20260917, rund 9 s): 30 000 Läufe über alle 5 Fensterzustände × 13 Resolver-Antworten × variable Tick-Längen gegen zwölf Invarianten — Struktur; Prompt-Budget gehört der Episode; `discourage` wird nie verschluckt; ein **aktueller** Schutz-Schließgrund wird nie als `open` publiziert; bei bekannt offenem Fenster verfällt kein Schließrat; ein Not-Abbruch wird nie von einem neuen Öffnungsgrund überstimmt; das Stummschalten ändert den `action`-Status nicht; die Notiz aus §5e ist nie veraltet und tritt nie aus der Ruhezeit heraus. Dazu 1 500 zufällig erzeugte Startzustände, aus denen eine stille Welt die Maschine ausnahmslos nach `idle` zurückführt, und ein Abdeckungstest, der belegt, dass der Lauf tatsächlich alle fünf Phasen und den Episoden-Token erreicht — ein grüner Soak über einen unerreichten Zustandsraum bewiese nichts. **Und auch das bleibt eine Stichprobe:** erreichte Phasen sind kein Beleg für vollständige Übergangs- oder Historienabdeckung. Invariante 10 kam erst durch einen externen Prüfbericht dazu, weil die vorherige Fassung nur die Dringlichkeit prüfte und deshalb nicht auslösen konnte, sobald der Grund selbst verloren war.

Drei echte Fehler stammen ausschließlich von dort: ein Prompt-Budget, das dem Grund des Ticks statt der Episode folgte; ein erschöpftes Budget, das einen stehenden Schließrat in `idle` verwandelte; und eine Phasenänderung, die `discourage` genau im Moment seiner Handlungsrelevanz verschluckte.

Die bestehende Suite bleibt vollständig grün (132 Module), weil `ventilation.py` unberührt ist.

## Umsetzungsreihenfolge (normativ)

1. **v2a — pures Modul + Tests** — `comfort/vent_episode.py`, ohne jede Verdrahtung, **null Änderung an `ventilation.py` und null Änderung an der publizierten physikalischen Antwort**. Jede Korrektur dieses Pakets lässt sich vollständig mit dem heutigen `VentilationAdvice` ausdrücken. *(dieser Stand)*
2. **v2b — Evaluationsgrenze** — `VentilationEvaluation` als informationsreicher Zwischentyp (alle gültigen Öffnungsgründe, primärer Anzeigegrund, harter Schließgrund, weicher Veto-Grund, Idle-Ursache) mit `resolve_legacy()` darüber. Abnahmebedingung vor jeder Verhaltensänderung: `resolve_legacy(evaluate(x)) == ventilation_advise_alt(x)` über die beiden Sweeps (400 000 Zufalls- + 400 000 schwellenzentrierte Fälle) sowie die 58 Regressionsfälle. Erst wenn dieser Beweis grün ist, darf die FSM mehr als den einzelnen `VentilationAdvice` lesen.
3. **Fachliche Änderungen, jede einzeln aktiviert und messbar** — Hard-Stop gegen `mold_risk`; `dry_critical` auf `dry_alert_gm3`; CO₂-Rang; `mold_risk` als Eintritts- statt Haltebedingung; Entkopplung der Schließprädikate vom Fensterkontakt (ADR-0066-Nachtrag). Jede davon ist eine bewusste Verhaltensänderung im Gebäudeschutzpfad mit eigenem Feldtest, kein Nebenprodukt des Refactorings.
4. **Shadow** — die Naht führt die FSM mit, veröffentlicht `vent_phase`/`vent_idle_cause`/`vent_prompt` als Diagnose-Keys, aber die publizierte Empfehlung stammt weiter aus der Tabelle. Feldvergleich Phase gegen heutiges Verhalten.
5. **Persistenz** — `EpisodeState` in eine eigene Zustandsgruppe (Muster `ComfortActivationRuntime`, ADR-0069 §5: langlebiger Episodenzustand, kein Anti-Chatter-Latch, also **nicht** `PipelineLatches`). Codec additiv, Payload-Vertrag fortschreiben.
6. **Fensterinferenz** — ADR-0041-Slope als Quelle für `likely_open`/`likely_closed`, zunächst nur in Zonen ohne Kontakt, mit Konfidenzschwelle und Rückfall auf `unknown`.
7. **Flip** — die FSM wird die Quelle der publizierten Empfehlung; `oracle_flags()` ersetzt die `prev_*`-Ableitung an der Naht. Der Rückzug aus N6/N6b/N9 und die Flag-Krücken entfallen ersatzlos.
8. **Karte** — Phase und `idle_cause` sichtbar machen; die Erinnerungsschiene ersetzt die stehende Notification.

Schritt 7 ist der einzige mit Verhaltensänderung im Feld und braucht einen eigenen Feldtest je Zone.

## Konsequenzen

**Positiv:** eine ganze Fehlerklasse strukturell ausgeschlossen statt dreimal geflickt; Zonen ohne Fensterkontakt bekommen erstmals Schließräte; Anti-Spam existiert; „es passiert nichts" wird erklärbar; das Ablaufdiagramm wird zur prüfbaren Außensicht der Implementierung. Die drei N-Flicken in `ventilation.py` können nach Schritt 7 zurückgebaut werden.

**Negativ/Kosten:** ein persistierter Zustand mehr pro Zone; neun neue Zeitkonstanten, die kalibriert werden wollen; die Fensterinferenz ist ein Konfidenzproblem und kann falsch liegen — deshalb Schritt 6 getrennt und zunächst nur dort, wo heute gar nichts ist.

**Offen (alle hinter der Äquivalenzgrenze von Schritt 2b, siehe §0):** darf ein harter Schließgrund `mold_risk` überstimmen; `dry_critical` als echter Hard-Stop auf `dry_alert_gm3`; der CO₂-Rang; `mold_risk` nur als Eintritts- statt Haltebedingung; Entkopplung der sensorlosen Schließprädikate vom Fensterkontakt. Dazu die Konfidenzbildung der Slope-Erkennung und die Kalibrierung der zehn Zeitkonstanten.
