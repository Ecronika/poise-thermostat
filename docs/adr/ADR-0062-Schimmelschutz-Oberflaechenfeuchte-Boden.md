# ADR-0062: Schimmelschutz — Oberflächenfeuchte-Modell und Mindest-Lufttemperatur-Boden

**Status:** Implementiert (rückwirkend dokumentiert) · **Wirkung:** Live-A · **Datum:** 2026-07-26 · **Bezug:** ADR-0023 (Dual-Setpoint), ADR-0035 (Präzedenz-Solver), ADR-0041 (Fenster), ADR-0048 (Abgrenzung VDI 6022), ADR-0050 (Dry-Pfad), ADR-0057 (Card-Tick), ADR-0012 (Repair-Issues) · **Verifizierung:** Quellcode-Abgleich (`comfort/mold.py`, `estimation/psychrometrics.py`, `comfort/corridor.py`, `control/tick_pipeline.py`, `safety/sensor_watchdog.py`, `const.py`) + Normabgleich DIN 4108-2 / EN ISO 13788

## Kontext

Der Schimmelschutz ist seit den ersten Versionen **live im Schreibpfad** — er hebt den Heiz-Sollwert an und ist damit neben dem Frostschutz die härteste Sicherheitsschranke des Systems. Dokumentiert war er als Entscheidung jedoch **nie**.

**Befund beim Verweis-Abgleich (2026-07-26):** `comfort/mold.py` nennt „charter G4, ADR-0010", `estimation/psychrometrics.py` „ADR-0010 mould/psychrometrics", ADR-0048 und ADR-0050 zitieren „ADR-0010 (Schimmel/Taupunkt)" bzw. „ADR-0010 (Taupunkt+2 K harte Grenze)" — **ADR-0010 ist aber „Solar-Buchhaltung"**. Kein ADR im Register behandelte `f_Rsi`, DIN 4108-2 oder EN ISO 13788 als Entscheidung; die einzigen Treffer (ADR-0011, ADR-0014, ADR-0048) sind Test- bzw. Abgrenzungskontexte. Das referenzierte „charter G4" liegt nicht im Repo.

Dieser ADR schließt die Lücke **rückwirkend**: er beschreibt das Modell, wie es heute läuft, legt die Parameter normativ fest und räumt die Fehlverweise auf. Er ändert **kein Verhalten**.

## Entscheidungstreiber

Nachvollziehbarkeit der härtesten Live-Schranke; Normtreue (DIN 4108-2 / EN ISO 13788) statt Zahlenfolklore; klarer Ankerpunkt für Folge-ADRs (die Feuchte-Achsen-Erweiterung baut darauf auf); Vermeidung stiller Parameterdrift, solange niemand die Werte begründet hat.

## Betrachtete Optionen (mit Quelle)

1. **Status quo (undokumentiert lassen).** Die Verweise zeigen weiter ins Leere; jeder spätere Eingriff in `mold.py` müsste die Begründung neu rekonstruieren. Verworfen.
2. **Als Kontext-Abschnitt in den Erweiterungs-ADR (ADR-0063) aufnehmen.** Verworfen: die Bestandsentscheidung stünde in einem Dokument, das eine *Erweiterung* beschreibt — der nächste Leser sucht sie wieder an der falschen Stelle.
3. **Eigener, rückwirkend dokumentierender ADR + Korrektur der Fehlverweise.** — **gewählt.** Präzedenz: ADR-0048 hat die Nicht-Ziele ebenfalls nachträglich festgeschrieben.

## Entscheidung

### 1. Physikalisches Kriterium

Schimmelwachstum wird über die relative Feuchte an der **kältesten Bauteiloberfläche** bewertet, nicht über die Raumluft. Das Wachstumskriterium ist `SURFACE_RH_LIMIT = 0.80` (80 % Oberflächen-RH, EN ISO 13788). Die Oberflächentemperatur folgt dem Temperaturfaktor

```
θ_si = θ_e + f_Rsi · (θ_i − θ_e)      f_Rsi = (θ_si − θ_e)/(θ_i − θ_e)
```

mit `DEFAULT_F_RSI = 0.7` — dem Mindestwert für **Bestandskonstruktionen** nach DIN 4108-2 (entspricht ~12,6 °C Mindest-Oberflächentemperatur im Norm-Referenzklima).

### 2. Umkehrung zur Regelgröße

Poise regelt keine Oberflächenfeuchte, sondern eine Temperatur. Das Kriterium wird deshalb zur **Mindest-Lufttemperatur** invertiert (`mold_min_air_temperature_detail`):

```
p_v      = vapour_pressure(t_air_ref, rh)          # Raumluft-Dampfdruck
θ_si,min = temperature_at_saturation(p_v / limit)  # Oberfläche bei 80 % RH
raw      = θ_e + (θ_si,min − θ_e) / f_Rsi
```

`t_air_ref` ist die **aktuelle Raumlufttemperatur** und dient nur der Schätzung der absoluten Raumfeuchte aus `rh`.

### 3. Deckelung bei 24 °C und `was_capped`

`_MOLD_MAX_C = 24.0` deckelt das Ergebnis. Die Deckelung ist **notwendig** — die Umkehrung hat bei kleinem `f_Rsi` und hoher Feuchte eine Singularität und liefert sonst unphysikalische Sollwerte. Zugleich ist sie eine **Schutzlücke**: liegt die physikalisch erforderliche Mindesttemperatur über 24 °C, schützt der zurückgegebene Boden **nicht mehr**. Dieser Fall wird als zweiter Rückgabewert `was_capped` ausgewiesen, damit er nicht still unter den Tisch fällt — der Raum braucht dort Entfeuchtung oder Lüftung, nicht mehr Wärme.

`_F_RSI_FLOOR = 0.1` klemmt unphysikalische Eingaben; `limit` wird auf (0, 1] geklemmt.

### 4. Einbindung in den Regelpfad

- **Untere Schranke:** `corridor.py` fügt `Bound(mold_min, "mold")` in die Liste der unteren Schranken ein; die Auflösung übernimmt der Präzedenz-Solver (ADR-0035).
- **Dual-Setpoint:** `heat_sp = max(heat_sp, mold_min)`.
- **Live-Berechnung:** `control/tick_pipeline.py` ruft `mold_min_air_temperature_detail(t_out_eff, rh, room)` — bewusst mit dem **effektiven Außen-Proxy** statt mit einem echten Außensensor, damit der Boden auch ohne Außensensor (konservativ) erhalten bleibt.
- **`f_Rsi` ist nicht konfigurierbar.** `corridor.py` führt es als Kontextfeld, der Live-Pfad nutzt den Default 0,7. Bewusst: ein falsch geratener Gebäudeparameter würde eine Sicherheitsschranke aufweichen, und den echten Wert kennt der Nutzer in aller Regel nicht.

### 5. Präzedenz gegenüber anderen Lagen

- **Frostschutz schlägt Schimmelschutz nie und umgekehrt** — beide sind untere Schranken, es gewinnt die höhere.
- **Eingefrorene Sensorik:** `safety/sensor_watchdog.frozen_safe_target(frost_floor, mold_min) = max(frost_floor, mold_min)`.
- **Offenes Fenster (ADR-0041):** DIN 4108-2 ist ein **stationäres** Kriterium. Bei offenem Fenster kollabiert das Schreibziel auf den Boden; ein feuchter Raum würde dann gegen die Lüftung Richtung 24 °C heizen. Deshalb wird **nur die Schimmel-Komponente** für die ersten `WINDOW_MOULD_SUPPRESS_S = 1800` s der Fensterepisode aus dem **Schreibpfad** unterdrückt — der Frostboden **nie**. Die **Diagnose behält den echten Wert** (`mould_floor`). Wer den Schimmelboden konsumiert, muss deshalb wissen, ob er den geschriebenen oder den diagnostischen Wert braucht.
- **Ein manueller Sollwert oder eine geräteseitige Übernahme setzt sich nie durch** — der Boden klemmt beide (ADR-0059).

### 6. Sichtbarkeit

- `mould_floor` (= `mold_min`) ist ein veröffentlichtes Climate-Attribut und erscheint als oranger Tick auf der Card (ADR-0057, display-only).
- `dewpoint` wird ebenfalls veröffentlicht; die harte Kühlgrenze `cool_sp ≥ Taupunkt + 2 K` gehört zum selben Schutzkomplex (ADR-0050 §1).
- **Repair-Issue `mould_protection_inactive`:** ein konfigurierter, aber ausgefallener Feuchtesensor deaktiviert den Schimmelschutz still — das wird als Issue sichtbar gemacht und verschwindet automatisch wieder.
- **Bekannte Lücke:** `mold_capped` wird berechnet und liegt im Return-Dict, steht aber **nicht** in der `_ATTRS`-Allowlist von `climate.py` und kommt in der Card nicht vor. Genau die Lage „der Boden schützt nicht mehr" ist damit heute unsichtbar. Behebung ist ADR-0063 zugeordnet.

### 7. Zeitbasis — bewusste Abweichung von der Norm

EN ISO 13788 wertet das 80-%-Kriterium auf **Monatsmittelwerten** aus (`f_Rsi,min` je Monat, der kritische Monat entscheidet); einen Momentanwert kennt die Norm nicht. Poise wertet **je Tick** aus. Das ist für eine **Regelschranke** die richtige Wahl: Sicherheit darf nicht mitteln, und konservativ zu klemmen kostet nur Wärme. Für **Hinweise** an den Nutzer gilt das nicht — dort ist die tickweise Auswertung normfremd und erzeugt Alarmmüdigkeit; die gemittelte Auswertung ist deshalb ADR-0063 zugeordnet. **Die beiden Zeitbasen sind bewusst verschieden und dürfen nicht „harmonisiert" werden.**

### 8. Verweis-Korrektur

`comfort/mold.py`, `estimation/psychrometrics.py`, ADR-0048 und ADR-0050 verweisen für den Schimmel-/Taupunkt-Komplex auf **ADR-0010** (= Solar-Buchhaltung). Alle vier Stellen zeigen künftig auf **diesen** ADR.

## Begründung

**Normwahl.** DIN 4108-2 liefert den Temperaturfaktor als *Bauteil*-Anforderung, EN ISO 13788 das Oberflächen-Feuchtekriterium und das Rechenverfahren — zusammen genau die zwei Größen, die Poise braucht, und beide ohne Materialkenntnis auswertbar. Der Verzicht auf ein **Dosis-Modell** (VTT/Viitanen-Index, Sedlbauer-Isoplethen) ist für die Regelschranke bewusst: diese Modelle sind substratabhängig (Ojanen 2010 unterscheidet Fichte, Beton, Porenbeton, Mineralwolle, EPS …), und Poise kennt die Wandoberfläche nicht. Ein Index mit falscher Materialklasse wäre schlechter als das konservative stationäre Kriterium.

**`f_Rsi` = 0,7 statt 0,9.** Der Bestandswert ist die sichere Annahme: er unterstellt die schlechtere Konstruktion und liefert damit den höheren (schützenderen) Boden. Im Neubau ist er zu streng — das kostet Wärme, aber nie Schutz. Die umgekehrte Fehlannahme wäre ein Bauschaden.

**Warum die Umkehrung zur Temperatur und nicht zur Feuchte.** Poise besitzt Aktoren für Temperatur; Feuchte kann es nur abwärts und nur mit einem `dry`-fähigen Gerät bewegen (ADR-0050), heben gar nicht (ADR-0048). Die Temperatur ist damit der einzige Freiheitsgrad, der immer zur Verfügung steht.

## Konsequenzen

**Positiv:** Die härteste Live-Schranke ist begründet und auffindbar; die vier Fehlverweise sind aufgeräumt; Folge-ADRs haben einen Ankerpunkt; die bewusst verschiedenen Zeitbasen (§7) sind festgeschrieben, bevor jemand sie versehentlich vereinheitlicht. **Negativ/Kosten:** keine — rein dokumentarisch, kein Code-Verhalten berührt. **Rest-Risiko:** `f_Rsi` bleibt eine Annahme; der Boden ist so gut wie diese Annahme und **kein Gutachten**. Das gehört in jede nutzerseitige Erklärung des Werts.

## Verifizierung

Rückwirkend: das beschriebene Verhalten ist der Bestand und durch die vorhandenen Tests abgesichert (`mold`/`psychrometrics`-Referenztests, Korridor- und Solver-Tests, `frozen_safe_target`). Für diesen ADR ist **kein neuer Test und kein Version-Bump** erforderlich — Präzedenz: ADR-0048 wurde ebenfalls behavior-identisch nachdokumentiert. Zu prüfen ist allein, dass die vier korrigierten Verweise auf ADR-0062 zeigen.

## Compliance

Generische Bauphysik ohne geräte-/herstellerspezifische Sonderlogik (G29/G30). **Abgrenzung (ADR-0048):** dies ist Bauteil-Kondensationsphysik nach DIN 4108-2 / EN ISO 13788 — **kein** Anspruch auf RLT-Anlagenhygiene nach VDI 6022 und keine Lüftungsbemessung.

## Verknüpfungen

**Dokumentiert rückwirkend** den seit Bestehen live laufenden Schimmelboden. **Korrigiert** die ADR-0010-Fehlverweise in `mold.py`, `psychrometrics.py`, ADR-0048 und ADR-0050. **Genutzt von** ADR-0023/0035 (Schranke im Korridor), ADR-0041 (Fenster-Unterdrückung), ADR-0050 (Health-Floors vor Feuchte), ADR-0057 (Card-Tick). **Grundlage für ADR-0063** (Feuchte-Achsen-Erweiterung: gemittelte Auswertung für Hinweise, Veröffentlichung von `mold_capped`, schimmelsichere Feuchte-Obergrenze).
