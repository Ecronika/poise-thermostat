# ADR-0041: Fenster-Auto-Erkennung per Temperatur-Slope + Bypass

**Status:** akzeptiert (Umsetzung shadow-first) · **Datum:** 2026-06-23 · **Bezug:** ADR-0002/0024 (EKF, Lernpause), ADR-0012 (Fenster-Sicherheit & Degradationsleiter), ADR-0026 (Schatten-Schätzer-Prinzip), ADR-0027/0035 (Norm-Floors & Constraint-Solver), ADR-0011 (Pure-Core/Test-first) · **Grundlage:** `Meinungsbild_Override-und-Fenster-Slope.md` (quellcode- + issue-belegt)

## Kontext
Poise pausiert heute nur, wenn ein **Fenstersensor** konfiguriert ist (`_window_open()` im Coordinator). Die meisten Räume haben keinen Kontaktsensor — Stoßlüften bleibt unerkannt, Poise heizt dagegen. Der Coordinator berechnet ohnehin bereits die Raumtemperatur-Rate `rate = (room − prev_room)/dt_h` in °C/h (für `seasonless_rate`). Diese Größe ist die natürliche Eingabe einer slope-basierten Fenstererkennung — keine neue Messung nötig (ADR-0026).

**Feld (quellcode-verifiziert):** Versatile Thermostat `window_auto` erkennt per Temperaturabfall ohne Sensor (°C/h, EMA-Glättung 0,2/0,8, getrennte Auf/Zu-Schwellen, `MIN_NB_POINT=4`, `MAX_SLOPE=120`, `window_auto_max_duration`-Auto-Reset, Slope nur aktiv *ohne* Sensor, wählbare Reaktion frost/eco/off/fan). Better Thermostat liefert den sauberen Sensorpfad (beidseitiger Debounce + Lernpause beim Öffnen). **Community-Meinungsbild:** das *Prinzip* wird vertraut; Schmerzpunkte sind (a) fehlerhafte Zustands-/Preset-Rückkehr v. a. bei Kühlung [VT#1987/1958], (b) fehlender manueller Bypass [BT#1638/1487], (c) fehlender Failsafe bei totem Sensor [BT#1978].

## Entscheidung
1. **Pure Helfer `control/window_auto.py` (test-first).** Slope-basierte Erkennung aus dem vorhandenen geglätteten dT/dt: EMA-Glättung, **getrennte Auf/Zu-Schwellen** (Hysterese), Mindestpunkte vor erster Entscheidung, |Slope|-Sanity-Filter, **Max-Dauer-Auto-Reset** (erzwungenes „geschlossen", schützt vor Dauerblockade). Keine HA-Abhängigkeit, kein eigener Timer — Sample-Zähler + verstrichene Minuten werden injiziert.
2. **Sensor schlägt Heuristik (Exklusivität, wie VTherm).** Auto-Slope ist nur aktiv, wenn *kein* Fenstersensor konfiguriert ist. Sauberes „measured > estimated" (Degradationsleiter ADR-0012).
3. **Reaktion norm-sicher über den Constraint-Solver (ADR-0035), nie hart aus.** Erkanntes Fenster senkt auf Frost-/Eco-Stufe; Frost-/Schimmel-Floor und ASR-Deckel bleiben aktiv (ADR-0027). Das vermeidet konstruktiv die „Kühlen-vs-Heizen-Preset"-Bugklasse [VT#1958/1987], weil nicht ein Roh-Preset, sondern ein normgeclampter Sollwert gesetzt wird.
4. **Lernpause während offen** (EKF-Pause, BT-Muster — heute schon für den Sensorpfad, auf Auto ausweiten) gegen Modellvergiftung.
5. **Failsafe bei Sensor-Ausfall:** unavailable/unknown → heizen *wie ohne Sensor* + Repair-Issue/Notify. Deckt [BT#1978]; der Frozen-Sensor-Watchdog + Degradationsleiter (ADR-0012, v0.14.0) sind die vorhandene Basis.
6. **Bypass-Schalter** „Fenster ignorieren" (neustartfest), deckt [BT#1638/1487] für Sonderfälle (Lüftungsautomatik, Haustier).
7. **Shadow-first (ADR-0026/0033-Muster).** Zuerst Diagnose `window_auto_detected` + `window_auto_slope` exponieren, ohne zu regeln; Aktuierung (Slope löst die Pause aus) ist der zweite, separat verifizierte Schritt.

## Konsequenzen
**Positiv:** funktioniert sensorlos (häufigster Realfall); nutzt eine bereits vorhandene Modellgröße statt eines zweiten Filters; Default-Schwellen aus `tau`/Heizrate ableitbar statt fix; Reaktion normkonform; Community-Schmerzpunkte (a)–(c) sind durch Solver/Watchdog/Bypass adressiert. **Negativ/Risiko:** jede Heuristik kann fehlauslösen — abgefedert durch Hysterese + Mindestpunkte + Max-Dauer-Reset + Sensor-Vorrang + Bypass + shadow-first-Einführung. **Failsafe:** im Zweifel heizen (nicht einfrieren).

## Nachtrag — Stufe 2 umgesetzt (v0.67.0)

Die Aktuierung ist live: pure `effective_window_open(sensor_open, auto_open, bypass)` (getestet) kombiniert Sensor- und Slope-Signal; der Coordinator speist das **effektive** Fenstersignal in genau den bestehenden norm-sicheren Pfad (`resolve_write_target` → Absenkung auf Frost-/Schimmel-Floor, Mode „off") sowie in das Lernpause-Gate (`should_learn`) und das `heating`-Flag. **Bypass** als persistenter Schalter (`switch.py`, EntityCategory.CONFIG, `set_window_bypass`/`window_bypass`-Property, in Save-Payload persistiert/wiederhergestellt) — erzwingt Fenster=zu (Eskap gegen Fehlauslösung / „Heizen trotz offenem Fenster", BT#1638/1487). Diagnose-Attribute: `window_open` (jetzt effektiv), `window_auto_detected` (roh), `window_bypass`, `window_auto_slope`. Übersetzungen EN/DE mit Parität. Platform.SWITCH in __init__ verdrahtet, switch.py in coverage-omit/mypy-ignore (HA-Glue). Gate grün: pytest 348, mypy 59, card 13.
