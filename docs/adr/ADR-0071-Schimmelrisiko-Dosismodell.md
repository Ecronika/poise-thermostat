# ADR-0071: Schimmelrisiko — Dosismodell (VTT-Schimmelindex) statt Momentanwert-Boden

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-09-11 · **Bezug:** ADR-0062 (abgelöst: Oberflächenfeuchte-Boden), ADR-0066 (Feuchte-Achse, teilt sich die Psychrometrie), ADR-0023 (Dual-Setpoint), ADR-0035 (Präzedenz-Solver), ADR-0012 (Repair-Issue `mould_protection_inactive`), ADR-0005 (Schichtgrenzen), ADR-0007/ADR-0064 (Persistenz), ADR-0041 (Fenster-Unterdrückung), ADR-0048 (Nicht-Ziele) · **Verifizierung:** `comfort/mould_risk.py` + `tests/test_mould_risk.py` (26 Fälle), `runtime/state.py::HumidityRuntime`, nachgerechneter Szenarienvergleich (6 × 90 d stündlich)

## Kontext

ADR-0062 bewertete das Schimmelrisiko an **einer einzigen Momentanaufnahme**: Oberflächen-RH über `SURFACE_RH_LIMIT = 0.80`, sofort und ungefiltert in einen Lufttemperatur-Boden invertiert (`mold_min_air_temperature_detail`). Der Boden ist neben dem Frostschutz die härteste Live-Schranke des Systems — er hebt den Heiz-Sollwert an, gegen Nutzerwunsch, gegen Zeitplan, gegen Absenkung.

Der Anlass zur Neubewertung war nicht ein Feldfehler, sondern eine Plausibilitätsfrage: **80 % Oberflächenfeuchte ist die untere Grenze möglichen Wachstums, kein Wachstumsereignis.** Keimzeiten von 1–2 Tagen setzen über 90 % rF bei 15–25 °C voraus; bei 81 % rF und 20 °C liegt die Zeit bis zum ersten sichtbaren Befund nach Hukka & Viitanen bei rund 127 Tagen. Ein Kriterium, das auf das Überschreiten von 80 % **sofort** mit Heizen antwortet, verwechselt „Wachstum ist nicht ausgeschlossen" mit „Wachstum findet statt".

Nachgerechnet wurde das an sechs Szenarien à 90 Tage, stündlich, auf Oberflächenwerten (Substratklasse SENSITIVE, Rückgangsfaktor 0,5). Verglichen wurde die abgelöste Methodik (Oberflächen-RH > 80 % → sofort Boden) gegen das hier beschlossene Dosis-Modell (Index + akuter Backstop 48 h über `critical_rh`):

| Szenario | Stunden mit Boden ALT | Stunden mit Boden NEU | Index nach 90 d | erster Eingriff NEU |
|---|---|---|---|---|
| A Schlafzimmer, intakte Wand (rF⌀ 57,5 %) | 0 | 0 | 0,000 | nie |
| B Schlafzimmer, Wärmebrücke (rF⌀ 75,6 %, Spitzen 85 %) | **720** | **0** | 0,000 | nie |
| C Bad, Duschspitzen (rF⌀ 62,9 %, 2×/Tag 100 %) | **360** | **0** | 0,092 | nie |
| D kaum beheizt, dauerfeucht (konstant 82 %) | 2160 | **2113** | 0,347 | **Tag 1** |
| E intermittierend (120 h 55 % / 6 h 95 %) | 102 | 0 | 0,006 | nie |
| F Wärmebrücke + Boden aktiv (rF⌀ 63,6 %) | 0 | 0 | 0,000 | nie |

**Was daraus folgt — und nur das:** Die neue Methodik entfernt **1182 Stunden** Heizen, das die alte allein wegen kurzer Feuchtespitzen ausgelöst hätte (B, C, E), und hält im einzigen echt chronischen Fall (D) den Schutz **ab dem ersten Tag** aufrecht. Der Gewinn ist die ausbleibende Reaktion auf Transienten bei unverändert vollem Schutz bei anhaltender Nässe.

**Was ausdrücklich NICHT behauptet wird:** dass das Dosis-Modell Fälle *fängt*, die das statische Kriterium übersieht. In dieser Rechnung tut es das nicht — die Spalte „NEU" liegt nirgends über der Spalte „ALT". Eine frühere Vergleichsrechnung dieser Runde behauptete das Gegenteil; sie lief in der falschen Zeitbasis (Tage als Stunden gelesen, Faktor 24 zu schnell) und ist samt ihrer Schlussfolgerung hinfällig. Die Tabelle oben ist die korrigierte Rechnung und die einzige, die hier gilt.

ADR-0062 §Begründung hat das Dosis-Modell seinerzeit **bewusst verworfen**, mit dem Argument: die VTT-/Sedlbauer-Modelle seien substratabhängig, Poise kenne die Wandoberfläche nicht, ein Index mit falscher Materialklasse sei schlechter als das konservative stationäre Kriterium. Dieses Argument wird hier nicht ignoriert, sondern beantwortet (siehe Begründung, „Zur Substrat-Einrede von ADR-0062").

## Entscheidungstreiber

- **Die Schranke muss auf das reagieren, was Schaden macht** — auf anhaltende Nässe, nicht auf eine Duschspitze. Fehlheizen kostet Energie und Vertrauen in die Schranke; wer sie als übergriffig erlebt, sucht nach Wegen, sie abzuschalten.
- **Tag-1-Wirksamkeit ist nicht verhandelbar.** Eine Schutzschranke, die erst nach Wochen Dosis greift, ist bei einer frisch installierten Integration in einem bereits feuchten Raum wertlos.
- **Normanschluss.** ASHRAE 160 Addendum e (2016) hat den VTT-Index normativ übernommen; er ist damit kein Forschungsmodell mehr, sondern die referenzierbare Methode für genau diese Frage.
- **Schnittstellenkompatibilität.** Der Boden wird von Korridor, Präzedenz-Solver, `frozen_safe_target`, Card und Hub konsumiert. Ein Methodenwechsel darf diesen Pfad nicht umbauen.
- **Determinismus und Reinheit** (G3/G27, ADR-0005): das Modell muss pur, zustandsfrei und im Replay-Harness wiederholbar sein; der Zustand gehört in die Persistenzschicht, nicht ins Modell.
- **Ehrlichkeit über die Modellgüte.** Das Modell stammt aus Holzversuchen; was es für Innenoberflächen nicht leisten kann, muss im Record stehen, nicht in einer Fußnote.

## Betrachtete Optionen (mit Quelle)

1. **Status quo: Momentanwert 80 % beibehalten** (ADR-0062, `comfort/mold.py::mold_min_air_temperature_detail`, EN ISO 13788 / DIN 4108-2). Verworfen: das Kriterium reagiert auf jede Transiente mit einer Sollwertanhebung — 1182 der 1182 Bodenstunden in B/C/E sind Reaktionen auf Feuchtespitzen von Stunden Dauer, bei einem Schimmelindex, der über 90 Tage nicht messbar steigt. Die Schwelle ist dabei nicht falsch; falsch ist, sie als Ereignis statt als Zustandsgrenze zu lesen.

2. **30-Tage-Mittel nach DIN EN ISO 13788:2012 bzw. ASHRAE 160-2009 in der Altfassung.** Die Norm selbst wertet das 80-%-Kriterium auf Monatsmittelwerten aus; der naheliegende Schritt wäre also, Poise auf diese Zeitbasis zu heben. Verworfen: **die Mittelung zerstört genau die Information, um die es geht.** Sie glättet die Transienten, die den Fehlalarm auslösen, verbessert aber die Erkennung des chronischen Falls nicht — Szenario B mittelt sich auf 75,6 % und Szenario C auf 62,9 % herunter, obwohl beide reale Feuchtestunden enthalten, und Szenario D ist mit 82 % Konstantwert im Mittel wie im Moment identisch. Für einen Regler, der im Minutentakt Daten hat, wäre der Wechsel von der Momentanaufnahme auf ein Monatsmittel kein Fortschritt, sondern ein Informationsverlust mit anderer Fehlerrichtung. Die Norm mittelt, weil sie auf Klimadatensätzen für eine Bauteilbemessung rechnet, nicht weil Mittelung die bessere Risikoaussage wäre.

3. **VTT-Schimmelindex nach ASHRAE 160 Addendum e (2016)** — Wachstumsmodell Hukka & Viitanen 1999, Sensitivitätsklassen und Rückgangsklassifizierung nach Ojanen et al., *Buildings XI* (2010), Tab. 4/6. — **gewählt.** Das Modell integriert Feuchte, Temperatur und Dauer zu einer Dosis, kennt eine temperaturabhängige Grenzfeuchte statt einer festen 80-%-Linie, deckelt das Erreichbare über M_max (eine dauerhaft klamme, aber nicht nasse Wand läuft nicht auf 6 hoch) und **klingt in Trockenphasen wieder ab**. Es ist mit vier Koeffizientensätzen vollständig parametrisierbar und braucht keine Materialkenntnis über die Grobklasse hinaus.

4. **Biohygrothermisches Modell nach WTA-Merkblatt 6-3 (Ausg. 2024-10), Sedlbauer-Isoplethen/LIM-Kurven.** Verworfen aus zwei Gründen. Erstens **Nichteinsehbarkeit**: die LIM-Kurven liegen nur als Diagramme in Sedlbauers Dissertation bzw. im kostenpflichtigen Merkblatt 6-3 vor und waren uns nicht zugänglich — eine Implementierung müsste Kurven aus Abbildungen abgreifen, was weder auditierbar noch reproduzierbar ist und dem Nachimplementierungs-Grundsatz (G29) widerspricht. Zweitens **fehlender Rückgangsterm**: das Modell beschreibt Keimung und Wachstum, kennt aber keine Regression bei Austrocknung. Bei intermittierender Befeuchtung — der Normalfall im Bad — würde der Index deshalb dauerhaft und monoton steigen, obwohl die Oberfläche zwischen den Duschen 23 Stunden trocken ist. Genau der Fehlalarm-Mechanismus, den wir hier abstellen wollen, wäre in ein Dosis-Modell hineingebaut worden.

## Entscheidung

### §1 Das Kriterium: Dosis statt Momentanwert

Das Schimmelrisiko wird als **VTT-Schimmelindex** 0…6 auf der kältesten Bauteiloberfläche geführt (`comfort/mould_risk.py`). Die Skala: 0 = kein Wachstum, 1 = mikroskopisches Wachstum / Keimung, 2 = sichtbares Wachstum (erste Hyphen, ~10 % Bedeckung), … 6 = starke Bedeckung.

Drei reine Funktionen tragen das Modell:

- `critical_rh(t_surface, spec)` — die temperaturabhängige Grenzfeuchte nach Ojanen Gl. 1 (`−0,00267·T³ + 0,160·T² − 3,13·T + 100` bis 20 °C, darüber die Klassenuntergrenze `spec.rh_min`). Das ersetzt die feste 80-%-Linie: bei 5 °C Oberflächentemperatur liegt die Grenze bei ~88 %, bei 20 °C bei 80 %.
- `max_index(t_surface, rh_surface, spec)` — das unter den aktuellen Bedingungen überhaupt erreichbare Maximum `M_max = a + b·x − c·x²`. Dies ist der Mechanismus, der Szenario D begrenzt: konstante 82 % Oberflächenfeuchte deckeln den Index einer sensiblen Oberfläche weit unterhalb der Eingriffsschwelle.
- `index_step(index, *, t_surface, rh_surface, dt_h, dry_hours, spec)` — ein Tick. Wachstum nach Hukka & Viitanen mit `k1·k2 / (7·exp(−0,68·lnT − 13,9·lnRH + 66,02))`, W = SQ = 0. **Zeitbasis:** diese Rate ist **pro Tag** (die 7 rechnet die Keimzeit in Wochen auf Tage um); im Stundenschritt wird durch 24 geteilt (`_HOURS_PER_DAY`). Gegenprobe an der Literatur: 20 °C/100 % → 6,8 d, 20 °C/95 % → 13,9 d, 20 °C/85 % → 65 d, 20 °C/81 % → 127 d — deckungsgleich mit Viitanens Kiefern-Messungen (eine Woche bei 100 %, rund zwei Wochen bei 95 %). Der Rückgang ist dreistufig: schnell in den ersten 6 Trockenstunden (`DECLINE_LT_6H`), **Plateau** von 6 bis 24 h, danach langsam (`DECLINE_GT_24H`), jeweils skaliert mit `spec.decline` (Ojanens C_mat). Das Plateau ist der Grund, warum tägliches Stoßlüften die Dosis nicht zurücksetzt — eine Kolonie übersteht einen trockenen Tag im Wesentlichen unbeschadet, und das Modell muss das sagen.

### §2 Der Modulschnitt und die eine Glue-Funktion

`comfort/mould_risk.py` ist **pur**: keine HA-Importe, keine Importe aus `ha/`, `runtime/`, `control/`. Einzige Abhängigkeit ist die geteilte Psychrometrie in `comfort/mold.py` bzw. `estimation/psychrometrics.py` (ADR-0005).

Der Rest der Integration sieht **genau eine** Funktion:

```python
evaluate(*, t_room, rh_room, t_out, index, wet_hours, dry_hours,
         dt_h, was_engaged, spec=SUBSTRATES[DEFAULT_SUBSTRATE],
         f_rsi=DEFAULT_F_RSI) -> MouldRisk
```

Der Aufrufer reicht den persistierten Zustand hinein und bekommt den fortgeschriebenen Zustand plus das Urteil zurück. Der Zustand liegt damit **außerhalb** des Modells — das hält es pur und im Closed-Loop-Harness trivial wiederholbar.

`MouldRisk` trägt `index`, `wet_hours`, `dry_hours`, `engaged`, `floor`, `capped`, `surface_rh`, `critical_rh`, `reason` (`"index" | "acute" | "clear" | "no_humidity"`).

**Ausfallender Feuchtesensor:** bei `rh_room is None` wird der Dosis-Zustand **eingefroren**, nicht abgeklungen — „trocken" zu raten würde einen real erarbeiteten Index still abbauen, während wir blind sind. Der Repair-Issue `mould_protection_inactive` (ADR-0012) bleibt unverändert Aufgabe der Glue-Schicht und ist wortgleich erhalten.

### §3 Substratklasse: fester Default SENSITIVE, Landkarte vorbereitet

`SUBSTRATES` enthält die vier Sensitivitätsklassen nach Ojanen Tab. 4/6 vollständig (VERY_SENSITIVE, SENSITIVE, MEDIUM_RESISTANT, RESISTANT) mit `k1_lo`, `k1_hi`, `a`, `b`, `c`, `rh_min`, `decline`.

Verdrahtet ist **ausschließlich** `DEFAULT_SUBSTRATE = SubstrateClass.SENSITIVE` — papierkaschierte Innenoberflächen, also Tapete und Gipskarton, womit eine gewöhnliche Wohnungsinnenwand beschichtet ist.

`ROOM_PROFILE_SUBSTRATE` (Raumprofil → Klasse) ist **vorbereitet und bewusst von niemandem aufgerufen**. Die Zuordnung wird einmal dort entschieden, wo die Koeffizienten stehen, statt beim späteren Config-Schritt ad hoc erfunden zu werden. Die Konstante ist im Modul ausdrücklich als „LATENT BY DESIGN" markiert, damit kein Struktur-/Dead-Code-Gate daran scheitert — dieselbe Markierung trägt `CONF_OVERRIDE_SUGGESTIONS` in `const.py`. **Die Konfigurierbarkeit der Substratklasse ist eine bewusst zurückgestellte Folge-Entscheidung**, kein Versehen (siehe Verknüpfungen).

### §4 Warmstart 1.0 und Persistenz

`WARM_START_INDEX = 1.0`. Eine Zone ohne Historie startet nicht bei 0.

**Begründung ist Realismus, nicht Reaktionsgeschwindigkeit.** Index 1 bedeutet auf der VTT-Skala „Keimung hat stattgefunden, kein sichtbares Wachstum". Eine seit Jahren bewohnte Wohnungsoberfläche ist genau dort; bei 0 steht eine sterile Laborfläche. Der Warmstart bildet also den ehrlichen Ausgangszustand ab.

Ausdrücklich **nicht** damit begründet, dass das Modell dadurch schneller reagiert: für die Default-Klasse SENSITIVE ist `k1_hi` (0,386) **kleiner** als `k1_lo` (0,578) — oberhalb Index 1 wächst der Index also *langsamer*. Die Tag-1-Wirksamkeit liefert der akute Backstop (§5), nicht der Warmstart.

Persistiert werden in `runtime/state.py::HumidityRuntime` genau drei Felder: `mould_index` (Default 1.0), `mould_wet_hours`, `mould_dry_hours`, aufgenommen in `PERSISTED_FIELDS` und durchgereicht bis `persistence/codec.py` und `coordinator.py` (ADR-0007/ADR-0064). Der Warmstartwert steht dort als **Literal**, nicht als Import — `runtime/` importiert nicht aus `comfort/` (ADR-0005). Fehlende Werte in alten Payloads fallen auf die Defaults zurück und sind kein Fehler: eine bestehende Installation startet nach dem Update mit dem Warmstart, eine gereifte mit ihrem gespeicherten Index.

`mould_engaged` ist die eine bewusste Ausnahme: der Engage-Verdikt des Vortticks ist **transient**, weil er sich nach einem Neustart binnen eines Ticks aus dem persistierten Index/Zähler-Zustand neu ergibt und anders als der Index keine Mehrtages-Historie trägt.

### §5 Zwei Schichten, mit klar getrennten Rollen

Das ist die zentrale Konstruktion dieses ADR, und sie darf nicht verwischt werden:

- **Akuter Backstop — die operative Schutzschicht.** `wet_hours >= ACUTE_WET_HOURS` (48 h ununterbrochen über `critical_rh`) engagiert den Boden, **unabhängig vom gelernten Index, ab Tag 1**. Das ist die Schicht, die den chronischen Nässefall abdeckt (Szenario D: erster Eingriff Tag 1), und die Schicht, die in einer frisch installierten Integration überhaupt schützt. `reason = "acute"`.
- **Dosis-Index — die Langzeitschicht.** `index >= INDEX_ENGAGE` (2,0). Der Index wächst in einer normalen Wohnung über eine Heizperiode nur um Bruchteile und akkumuliert über **Jahre** (deshalb persistiert). Er ist kein Auslöser des Tagesgeschäfts, sondern das Gedächtnis für eine Oberfläche, die über viele Heizperioden immer wieder knapp in den Wachstumsbereich gerät. `reason = "index"`.

Die Eingriffsschwelle liegt bei **MI 2** und nicht bei dem in ASHRAE 160 genannten MI 3: Künzel (ORNL 2016) setzt die tolerierbare Grenze für **Innenoberflächen** bei 2 an — sichtbares Wachstum im Wohnraum ist bereits ein Hygieneversagen, während die 3 für verdeckte Bauteilschichten geschrieben ist.

Hysterese: einmal engagiert, hält der Boden bis `index < INDEX_RELEASE` (1,5). Ohne sie würde der langsam wandernde Index tagelang über der 2,0-Linie flattern.

### §6 Die Umkehrung zur Regelgröße — Bisektion statt Einzeiler

Poise regelt Temperatur, nicht Feuchte. `required_air_temperature(...)` liefert die Lufttemperatur, bei der die Oberflächenfeuchte auf `critical_rh` zurückfällt.

Der ADR-0062-Einzeiler (`θ_si,min` aus dem Dampfdruck, dann durch `f_Rsi` zurückrechnen) trägt hier **nicht mehr**: das Ziel ist implizit geworden. Wärmere Luft erwärmt die Oberfläche, senkt damit die Oberflächenfeuchte — senkt aber **zugleich** `critical_rh` (die Ojanen-Kubik fällt bis 20 °C). Beide Seiten des Vergleichs bewegen sich. Gelöst wird per Bisektion über `[t_out, FLOOR_CEILING_C]`, `_BISECTION_STEPS = 60` Halbierungen eines ≤ 24 K breiten Intervalls; das liegt weit unter der Float-Auflösung und erspart jede Konvergenzdiskussion. Die absolute Feuchte bleibt dabei konstant: Heizen trocknet die Oberfläche, indem es sie erwärmt, es entfernt kein Wasser.

`FLOOR_CEILING_C = 24.0` und die `capped`-Meldung werden **unverändert aus ADR-0062 übernommen**, samt ihrer Begründung: reicht selbst die Decke nicht, schützt der Boden nicht mehr, und der Raum braucht Entfeuchtung oder Lüftung statt mehr Wärme. Dieser Fall wird gemeldet, nicht verschluckt.

**Schnittstellenkompatibilität.** `SafetyFloorsResult` behält die Feldnamen `mold_min` und `mold_capped`; sie tragen jetzt `MouldRisk.floor` bzw. `MouldRisk.capped`. Dadurch bleibt der gesamte nachgelagerte Pfad — `comfort/dual_setpoint.py::decide`, `tick_resolve`, `phase_actuate`, `safety/sensor_watchdog.py::frozen_safe_target`, `FinalizeContext`, `ha/phase_report.py`, `control/hub_aggregate.py` — **unverändert**. `control/pipeline_prepare.py::stage_safety_floors` wächst um `mould_state`, `was_engaged`, `dt_h` als Eingänge und um `mould_index`, `mould_wet_hours`, `mould_dry_hours`, `mould_engaged`, `mould_reason` als Ausgänge. Neu in der Diagnose: `mould_index` (2 Nachkommastellen), `mould_engaged`, `mould_reason`, `mould_substrate`; die Bestandsschlüssel `surface_rh`, `surface_rh_mean`, `mold_capped`, `rh_max_safe`, `abs_max_safe` bleiben erhalten.

Aus `comfort/mold.py` entfallen rückstandslos `mold_min_air_temperature_detail`, `mold_min_air_temperature`, `_MOLD_MAX_C` und `SURFACE_RH_LIMIT` — die 80-%-Konstante **ist** die abgelöste Methodik und darf nicht als unbenutzter Begleiter liegenbleiben. `DEFAULT_F_RSI`, `_F_RSI_FLOOR`, `surface_temperature`, `surface_relative_humidity` und `max_safe_rh` **bleiben**: das ist geteilte Psychrometrie, und ADR-0066 baut darauf. `max_safe_rh` bekommt seine Grenze künftig vom Aufrufer als `limit = MouldRisk.critical_rh / 100.0` — die Feuchte-Achse rechnet damit gegen dieselbe temperaturabhängige Grenze wie der Boden, statt gegen eine eigene 0,80.

### §7 Zweite Entscheidung dieser Runde: die Bindungs-Ursache wird an der Quelle bestimmt

Kleiner im Umfang, aber derselbe Fehlertyp. `diagnostics/shadows.py::evaluate_cover_shadow` rekonstruierte die Ursache der unteren Bindung aus dem **Ergebnis**:

```python
binding = "mold" if mold_min and mold_min >= heat_sp else "en16798"
```

Das vergleicht **ungerundetes** `mold_min` gegen **gerundetes** `heat_sp` und meldet deshalb systematisch die falsche Ursache — je nach Rundungsrichtung „mold", wo EN 16798 band, oder umgekehrt.

Entschieden: `ComfortDecision` bekommt ein Feld `lower_cause: str` mit den Werten `"mould" | "frost" | "en16798" | "comfort_base"`, gesetzt in `comfort/dual_setpoint.py::decide()` genau an der Stelle, an der `heat_sp` sein Maximum bekommt, **vor dem Runden**; Prüfreihenfolge mould > frost > en16798-Klemme > comfort_base. `evaluate_cover_shadow` bekommt den Wahrheitswert als Keyword-Parameter `mould_binds` hereingereicht (`ha/phase_shadow.py`: `mould_binds = ctx.decision.lower_cause == "mould"`) und gibt `"mold" if mould_binds else "en16798"` zurück. Das Feld hat den Default `"comfort_base"`, damit bestehende Aufrufstellen, die `ComfortDecision` konstruieren, nicht brechen. `ha/phase_report.py` bleibt unverändert (es liest weiter `binding`); `control/hub_aggregate.py` matcht bereits auf `"mould"`/`"mold"`.

Das Prinzip, das hier zum zweiten Mal in diesem Record auftaucht: **eine Ursache wird dort festgehalten, wo sie entsteht, nicht aus einem gerundeten Resultat zurückgeschlossen.**

### §8 Dritte Entscheidung: die Beratungsachse wird von der Dosis entkoppelt

Aufgefallen erst im CI, nachdem §1–§7 standen, und es ist der Preis dafür, dass §1 eine bis dahin *implizite* Gleichsetzung auflöst.

ADR-0066 N2 formuliert den Schließ-Rat `mold_guard` als „Fenster offen ∧ Boden gebunden ∧ Oberflächen-RH über der sicheren Grenze". Unter ADR-0062 war „ein Boden greift durch" eine reine Funktion des aktuellen Messwerts und damit **synonym** zu „die Oberflächen brauchen es wärmer als die Kühlkante". Das Dosismodell macht die erste Aussage langsam — absichtlich, denn sie rechtfertigt Heizen — und zieht die zweite unbeabsichtigt mit. Ergebnis: eine frische Installation hätte die Empfehlung über die gesamte Reifezeit des Index nie bekommen, obwohl die Wände nachweislich über der Grenze liegen (im Glue-Test 82,2 % gegen eine Decke von 58,4 %).

Entschieden: `ventilation_advise` bekommt den Parameter `surface_needs_warmer` (Default `False`), berechnet an der Naht aus dem **ungegateten** `required_air_temperature` gegen die effektive Kühlkante — dieselbe Vergleichsform und Toleranz wie `cool_edge_protected`, nur ohne den Dosis-Gate. `mold_guard` liest ihn; Wächter 5, der eine echte Komfort-Entscheidung (`heat_out`) vetoed, liest weiter den **durchgreifenden** Boden. In `diagnostics/shadows.py` stehen deshalb ab jetzt zwei Werte nebeneinander: `required` (immer, wenn Feuchte und Außentemperatur vorliegen) und `mold_min = required if mould_engaged else None`.

Das Prinzip dahinter, und es ist nicht dasselbe wie in §7: **Die Dosis ist die Berechtigung zu handeln, nicht die Berechtigung zu sprechen.** Heizen übergeht den Nutzerwunsch und kostet Geld — dafür muss die Evidenz reif sein. Ein Rat kostet nichts und ist reversibel; ihn hinter dasselbe Gate zu stellen verwechselt die Schwelle für eine Handlung mit der Schwelle für eine Information. Dieselbe Linie trägt bereits die Festlegung, dass Lüften nur empfohlen und nie in der Präzedenz bevorzugt werden darf (ADR-0048).

Was das **nicht** heißt: dass die Beratungsachse jetzt ungefiltert auf jeden Feuchtepeak anspringt. Der offensichtliche Fehlauslöser — Bad nach dem Duschen — wird weiterhin von der Präzedenz gefangen, nicht von dieser Bedingung: Regel 1 (`mold_risk`, „öffnen") sitzt über `mold_guard` und gewinnt bei trockenerer Außenluft und akutem 48-h-Mittel. Der Küchenfall erreicht `mold_guard` gerade deshalb, weil sein Mittel noch unter der Rule-1-Linie liegt. Die Einzelheiten stehen in ADR-0066 N3, der die Regel besitzt; hier steht die Begründung, weil dieser Record die Ursache gesetzt hat.

## Begründung

**Warum überhaupt gewechselt, wenn die neue Methodik nichts zusätzlich fängt.** Weil die Frage nicht „fängt sie mehr?" ist, sondern „bindet sie richtig?". Die alte Schranke hat in drei von sechs Szenarien den Heiz-Sollwert angehoben, ohne dass ein Schimmelindex über 90 Tage messbar reagiert hätte. 1182 Stunden Heizen sind keine Sicherheitsreserve, sondern ein Kriterium, das auf die falsche Größe misst. Eine Sicherheitsschranke, deren Eingriffe der Nutzer als grundlos erlebt, verliert ihre Autorität — und genau das ist bei einer Schranke, die sich gegen den Nutzerwunsch durchsetzt, das eigentliche Risiko. Der Schutz im chronischen Fall bleibt dabei vollständig erhalten und setzt am selben Tag ein wie vorher.

**Warum ein Dosis-Modell und nicht eine höhere Schwelle.** Die Schwelle allein anzuheben (etwa auf 90 %) hätte Szenario C und E ebenfalls entschärft — aber auf Kosten von D, wo 82 % dauerhaft anliegen. Feuchte und Dauer sind nicht gegeneinander austauschbar; nur ein Modell, das beide integriert, kann 6 Stunden bei 95 % von 90 Tagen bei 82 % unterscheiden. Genau das leistet die Dosis.

**Warum VTT und nicht die Norm-Mittelung.** Siehe Option 2: eine Mittelung ist für einen Regler mit Minutendaten ein Informationsverlust. ADR-0062 §7 hatte die tickweise Auswertung mit demselben Argument gegen die Norm verteidigt („Sicherheit darf nicht mitteln") — dieser Teil der ADR-0062-Argumentation bleibt gültig und trägt hier gegen Option 2 weiter. Was ADR-0062 nicht sah: die Alternative zur Mittelung ist nicht zwingend der Momentanwert. Die Dosis ist die dritte Möglichkeit — sie integriert, ohne zu glätten.

**Zur Substrat-Einrede von ADR-0062.** ADR-0062 verwarf das Dosis-Modell, weil Poise die Wandoberfläche nicht kennt und ein Index mit falscher Materialklasse schlechter sei als das konservative stationäre Kriterium. Das Argument trifft eine Annahme, die wir nicht machen: Poise **rät** die Klasse nicht. Es setzt fest und unkonfigurierbar SENSITIVE — papierkaschierte Innenoberflächen, die zweitempfindlichste der vier Klassen, und für eine Wohnungsinnenwand die zutreffende. Die Restunsicherheit ist damit auf die Grobklassen-Entscheidung eingedampft und liegt auf der konservativen Seite: Fliese und Putz (MEDIUM_RESISTANT) würden langsamer wachsen, als SENSITIVE unterstellt. Die Klasse überhaupt konfigurierbar zu machen, würde die Einrede zurückholen — deshalb ist sie es nicht (§3). Dieselbe Logik hatte ADR-0062 bereits für `f_Rsi` angewandt: ein falsch geratener Gebäudeparameter weicht eine Sicherheitsschranke auf, und den echten Wert kennt der Nutzer in aller Regel nicht.

**Warum die Zweischichtigkeit und nicht nur der Index.** Der Index allein hätte in Szenario D erst nach Wochen gegriffen — und in einer frisch installierten Integration im bereits feuchten Bad nie rechtzeitig. Der akute Backstop löst dieses Problem ohne den Index zu verbiegen: 48 Stunden ununterbrochen über der Grenzfeuchte sind unabhängig von jeder Dosisrechnung ein Zustand, den man beantworten muss. Die Alternative — den Warmstart höher zu setzen, damit der Index schneller einsetzt — wäre eine Manipulation der Modellgröße zu Regelungszwecken gewesen und hätte die Aussage des Index als Zustandsmaß zerstört.

**Warum der Warmstart trotzdem bei 1,0 liegt.** Weil er den realen Ausgangszustand beschreibt, nicht weil er nützt. Siehe §4: für SENSITIVE wächst der Index oberhalb 1 sogar langsamer. Ein Warmstart, der aus Regelungsgründen gewählt würde, wäre derselbe Fehler wie ein Index mit geratener Materialklasse.

## Konsequenzen

**Positiv.**
- 1182 Stunden Fehlheizen weniger in den transienten Szenarien B/C/E, bei unverändertem Schutz ab Tag 1 im chronischen Fall D.
- Der Boden reagiert auf eine temperaturabhängige Grenzfeuchte statt auf eine feste 80-%-Linie; bei kalten Oberflächen ist er dadurch strenger, bei warmen milder — beides physikalisch richtig herum.
- Normanschluss an ASHRAE 160 Addendum e statt an eine Zahl, die aus DIN EN ISO 13788 sinnentstellt in den Momentanwert übernommen war.
- Eine Langzeitschicht, die es vorher nicht gab: eine Oberfläche, die über Jahre immer wieder knapp in den Wachstumsbereich gerät, wird erkannt — der Momentanwert konnte das grundsätzlich nicht.
- Der nachgelagerte Regelpfad ist unverändert; der Methodenwechsel ist eine Ersetzung hinter stabilen Feldnamen.
- Die Bindungs-Ursache ist nicht mehr aus einem gerundeten Ergebnis rekonstruiert (§7).

**Negativ / Kosten / Rest-Risiko.**
- **Herkunft aus Holzversuchen.** Hukka & Viitanen fitteten das Modell an Kiefern- und Fichtensplintholz. Die Übertragung auf mineralische Oberflächen geschieht ausschließlich über Ojanens Grobklassen; eine oberflächenspezifische Kalibrierung gibt es nicht und kann es hier nicht geben.
- **Eigenunsicherheit des Modells.** VTT gibt ±0,5 Indexpunkte an. Bei einer Eingriffsschwelle von 2,0 ist das ein Viertel des Weges von 0 auf die Schwelle.
- **Schwache Datenlage beim Rückgang.** Die dreistufige Rückgangsklassifizierung beruht laut Ojanen auf wenigen, stark streuenden Messungen. Das Plateau zwischen 6 und 24 Trockenstunden ist die am dünnsten belegte Stelle des Modells — und zugleich die, die darüber entscheidet, ob tägliches Lüften die Dosis zurücksetzt.
- **Keine belastbare Feldvalidierung für Innenoberflächen in Wohnungen.** Das Modell ist an Bauteilaufbauten und in Laborversuchen validiert, nicht an bewohnten Innenräumen. Die vorliegenden Feldstudien sind schwach: die UCL-Studie 2005 traf in 2 von 6 Fällen zu; Menneer et al. (2022) berichten eine balanced accuracy von 0,63 — das ist besser als Raten, aber weit von einem Gutachten entfernt. Vereecken & Roels (2012) haben im Modellvergleich generell erhebliche Streuung zwischen den Schimmelmodellen gefunden. **Der Boden ist eine Regelschranke, kein bauphysikalisches Gutachten**; das gehört in jede nutzerseitige Erklärung.
- **Mehr Zustand.** Drei zusätzliche persistierte Felder, ein transientes; eine gereifte Installation trägt nun eine Dosis-Historie, die bei einem Store-Verlust auf den Warmstart zurückfällt.
- **Die Substratklasse ist nicht konfigurierbar** und `ROOM_PROFILE_SUBSTRATE` bleibt vorerst toter, absichtlich latenter Code. Wer ein Bad korrekt als MEDIUM_RESISTANT führen will, kann das heute nicht.
- **Verhaltensänderung im Bestand ohne Versionssprung des Datenmodells.** Installationen, in denen der alte Boden regelmäßig band, werden nach dem Update spürbar seltener angehoben. Das ist beabsichtigt, aber es ist eine Verhaltensänderung an einer Sicherheitsschranke und muss so kommuniziert werden.
- **Schutzlücke unverändert.** `capped` bleibt der Fall, in dem der Boden nicht mehr schützt — das Dosis-Modell ändert daran nichts, es benennt den Fall nur weiterhin.

## Verifizierung

**Kernmodul.** `custom_components/poise/comfort/mould_risk.py` — pur, keine HA-/`ha/`-/`runtime/`-/`control/`-Importe. Belegte Symbole: die Konstanten `WARM_START_INDEX = 1.0`, `INDEX_ENGAGE = 2.0`, `INDEX_RELEASE = 1.5`, `INDEX_MAX = 6.0`, `ACUTE_WET_HOURS = 48.0`, `FLOOR_CEILING_C = 24.0`, `DECLINE_LT_6H = -0.00133`, `DECLINE_GT_24H = -0.000667`; die internen Wächter `_F_RSI_FLOOR`, `_T_GROWTH_MIN`/`_T_GROWTH_MAX` (Gültigkeitsfenster 0 < T < 50 °C), `_RH_SPAN_FLOOR`, `_HOURS_PER_DAY = 24.0` (die Zeitbasis-Umrechnung), `_CRIT_RH_T_MAX = 20.0`, `_BISECTION_STEPS = 60`; `SubstrateClass`, `SubstrateSpec`, `SUBSTRATES`, `DEFAULT_SUBSTRATE`, `ROOM_PROFILE_SUBSTRATE`; die Funktionen `critical_rh`, `max_index`, `_growth_per_hour`, `index_step`, `_surface_rh_excess`, `required_air_temperature`; `MouldRisk` und `evaluate`.

**Tests.** `tests/test_mould_risk.py`, 26 Fälle. Namentlich die tragenden:
- `test_substrate_table_is_complete`, `test_default_substrate_is_sensitive`, `test_room_profile_map_is_latent_but_well_formed` — die Klassen-Tabelle und der feste Default aus §3.
- `test_critical_rh_reference_points`, `test_critical_rh_above_20c_is_the_class_floor`, `test_critical_rh_never_below_the_class_floor`, `test_critical_rh_falls_from_0_to_20c` — die Ojanen-Kubik und ihre Klemmung.
- `test_max_index_stays_low_at_a_steady_82_percent` — der M_max-Deckel, also genau der Mechanismus, der Szenario D vom Hochlaufen abhält.
- `test_index_step_grows_only_above_the_critical_line`, `test_index_step_does_not_grow_below_freezing`, `test_index_step_decline_uses_the_class_factor`, `test_index_step_plateau_between_6_and_24_dry_hours`, `test_index_step_slow_decline_beyond_24_dry_hours`, `test_index_step_clamps_at_zero_and_six` — Wachstum, dreistufiger Rückgang samt Plateau, Klemmung.
- `test_required_air_temperature_rises_with_room_humidity`, `test_required_air_temperature_caps_at_the_ceiling`, `test_required_air_temperature_round_trip_hits_the_critical_line`, `test_required_air_temperature_no_floor_when_already_safe` — die Bisektion aus §6, einschließlich Rundlauf gegen `critical_rh` und `capped`.
- `test_evaluate_without_humidity_passes_the_state_through`, `test_evaluate_dry_room_stays_clear`, `test_evaluate_acute_backstop_engages_after_48_wet_hours`, `test_evaluate_hysteresis_holds_between_release_and_engage` — die vier Verhaltenszweige von `evaluate`, darunter der akute Backstop aus §5.
- `test_evaluate_warm_start_grows_faster_than_a_pristine_zone` pinnt den k1-Verzweigungspunkt — **auf der VTT-Referenzklasse VERY_SENSITIVE**, wo `k1_hi` (2,0) größer als `k1_lo` (1,0) ist. Für die produktiv verdrahtete Klasse SENSITIVE ist das Verhältnis umgekehrt (0,386 gegen 0,578); der Test belegt also den Zweigwechsel, **nicht** eine schnellere Reaktion im Default. Genau deshalb steht die Warmstart-Begründung in §4 auf Realismus und nicht auf Reaktionsgeschwindigkeit.

**Persistenz.** `custom_components/poise/runtime/state.py::HumidityRuntime` führt `mould_index: float = 1.0`, `mould_wet_hours`, `mould_dry_hours` in `PERSISTED_FIELDS` und `mould_engaged: bool = False` ausdrücklich außerhalb davon; der Klassen-Docstring nennt die Begründung (Mehrtages-Dosis vs. Ein-Tick-Verdikt). Gepinnte Tests ziehen mit: `tests/test_phase1_state.py` (`EXPECTED_PERSISTED`), `tests/test_phase3_codec.py` (`EXPECTED_PAYLOAD_KEYS` und die Key-Zahl), `tests/test_phase6b_state_move.py` (`PROXY_MAP`/`POST_RELOCATION_FIELDS`).

**Integrationsnaht.** `control/pipeline_prepare.py::stage_safety_floors` (Eingänge `mould_state`/`was_engaged`/`dt_h`, Ausgänge `mould_index`/`mould_wet_hours`/`mould_dry_hours`/`mould_engaged`/`mould_reason` bei unveränderten Feldnamen `mold_min`/`mold_capped`), `runtime/zone_runtime.py` und `ha/phase_prepare.py` (Zähler-Rückschreibung nach `self._runtime.humidity`, `dt_h = TICK_INTERVAL_S / 3600.0`), `comfort/dual_setpoint.py::decide` (`lower_cause`), `diagnostics/shadows.py::evaluate_cover_shadow` (`mould_binds`) und der Humidity-Shadow (`limit = risk.critical_rh / 100.0` an `comfort/mold.py::max_safe_rh`).

**Nicht ausgeführt und daher nicht behauptet:** die HA-Integrationstests laufen in der Umgebung dieser Runde nicht. Belegt sind die oben namentlich genannten Symbole durch Quellcode-Abgleich, nicht durch einen grünen Gate-Lauf dieses Records.

## Compliance

**G29 (Nachimplementierung, kein Code-Copy).** Das Modell ist aus der publizierten Literatur nachimplementiert: Wachstumsgleichung und Rückgangsraten aus Hukka & Viitanen (1999), Sensitivitäts- und Rückgangsklassen aus Ojanen et al., *Buildings XI* (2010), Tab. 4/6, normative Übernahme in ANSI/ASHRAE Addendum e zu Standard 160-2009 (2016), Innenraum-Schwelle MI 2 nach Künzel (ORNL 2016). Kein Quellcode und keine Datentabelle aus einer fremden Implementierung wurde übernommen; alle Koeffizienten stehen als Literale im Modul und sind gegen die genannten Tabellen prüfbar. Das WTA-Merkblatt 6-3 (2024-10) wurde **nicht eingesehen** und ist deshalb auch nicht implementiert — die Verwerfung von Option 4 ist ausdrücklich eine Verwerfung wegen Nichteinsehbarkeit, keine Bewertung des Modells. Weitere herangezogene Quellen: DIN EN ISO 13788:2012 (abgelöste Zeitbasis), Glass et al., ASTM STP1599 (2017), Vereecken & Roels (2012) zur Modellstreuung.

**G30 (keine gerätespezifischen Sonderwege im Kern).** Generische Bauphysik. `comfort/mould_risk.py` kennt weder Gerät noch Hersteller noch Integration; es kennt Temperatur, Feuchte, Zeit und vier Materialklassen. Es gibt keinen Zweig, der von einem Aktortyp, einem Raumnamen oder einer Konfigurationsvariante abhängt.

**Abgrenzung (ADR-0048).** Dies ist Bauteil-Oberflächenphysik. **Kein** Anspruch auf RLT-Anlagenhygiene nach VDI 6022, keine Lüftungsbemessung, kein bauphysikalisches Gutachten und keine Aussage über verdeckte Bauteilschichten.

## Verknüpfungen

- **Löst ADR-0062 ab** (Schimmelschutz — Oberflächenfeuchte-Modell und Mindest-Lufttemperatur-Boden). Aus ADR-0062 **übernommen**: `f_Rsi`-Politik samt Default 0,7 und `_F_RSI_FLOOR`, die 24-°C-Deckelung mit `capped`-Meldung, die Regel „Sicherheit darf nicht mitteln" (hier gegen Option 2 weitergetragen), die Präzedenzlage gegenüber Frostschutz und Fenster (ADR-0041, `WINDOW_MOULD_SUPPRESS_S`), die Veröffentlichung als `mould_floor`. **Verworfen**: der 80-%-Momentanwert (`SURFACE_RH_LIMIT`) und die Einzeiler-Inversion.
- **Berührt ADR-0066** (Feuchte-Achse): `comfort/mold.py::max_safe_rh` bleibt bestehen und bekommt seine Grenze künftig als `MouldRisk.critical_rh / 100.0` statt als feste 0,80 — beide Achsen rechnen damit gegen dieselbe temperaturabhängige Linie. `surface_rh_mean` und der Lüftungsrat bleiben unverändert.
- **Berührt ADR-0023** (Dual-Setpoint): `heat_sp = max(heat_sp, mold_min)` unverändert; neu ist `lower_cause` (§7).
- **Berührt ADR-0035** (Präzedenz-Solver): `Bound(mold_min, "mold")` unverändert, nur der Wert dahinter wechselt die Methodik.
- **Berührt ADR-0012**: der Repair-Issue `mould_protection_inactive` bleibt wortgleich und bleibt Aufgabe der Glue-Schicht.
- **Berührt ADR-0005**: `comfort/mould_risk.py` ist pur; der Zustand liegt in `runtime/`, das Modell importiert nicht zurück, `runtime/` importiert nicht aus `comfort/` (deshalb der Warmstart als Literal).
- **Berührt ADR-0007 / ADR-0064**: drei neue persistierte Felder, defaultende Decodierung alter Payloads, Checkpoint am Tick-Ende unverändert.
- **Offene Folge-Entscheidung (bewusst zurückgestellt):** **Substratklasse und `f_Rsi` als Konfigurationsoption.** `ROOM_PROFILE_SUBSTRATE` ist die dafür vorbereitete Landkarte und wird bis dahin von niemandem aufgerufen. Die Entscheidung ist nicht „später machen", sondern „nicht ohne eigene Begründung": beide Parameter weichen bei falscher Eingabe eine Sicherheitsschranke auf, und beide kennt der Nutzer in aller Regel nicht. Ein künftiger ADR muss zeigen, wie er das auffängt, bevor die Option erscheint.
- **Offen (nicht Gegenstand dieses ADR):** Sichtbarkeit des Index in der Card (ADR-0057/ADR-0049) über die Diagnose-Schlüssel hinaus.
