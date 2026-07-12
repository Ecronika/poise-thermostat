# ADR-0017: Operativ→Luft-Transformation

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-18 · **Bezug:** E18, K4 · **Verifizierung:** Code-Review (kein echtes Feld-Vorbild — Befund)

## Kontext
Komfortband/Sollwert sind in Operativtemperatur formuliert; Wärmemodell und Aktor kennen nur Lufttemperatur (K4). Offen: Glättung des (MRT−Luft)-Offsets und Verhalten bei fehlendem MRT.

## Entscheidungstreiber
Stabiler Regelkreis in einer Größe (Luft); kein „wanderndes Ziel" bei wechselnder Einstrahlung; saubere Degradation bei fehlendem MRT; keine Solar-Doppelzählung.

## Befund am Code
- **Kein Wettbewerber rechnet MRT selbst.** Adaptive Climate/schoolboyqueue nutzen nur ein naives `(T_air+T_mrt)/2` mit **extern** geliefertem MRT, per Default **aus**. Das eigene Virtual MRT ist im Feld konkurrenzlos — also kein Vorbild, sondern Alleinstellung; die Transformationsschicht ist Eigenentwicklung.

## Entscheidung
1. **Komfortziel in Operativtemperatur bilden, an genau einer Stelle (`comfort/operative_temp`) in einen Luft-Sollwert transformieren** (ADR-0005-Schicht): `T_set,luft = T_set,operativ − offset`, `offset = geglättet(MRT − T_luft)`. Der Regelkreis (EKF/MPC/Aktor) arbeitet durchgängig in **Luft**.
2. **Glättung:** EWMA des Offsets mit Zeitkonstante **langsamer als Sensorrauschen, schneller als Solarschwankung** (Startwert ~15–30 min; im Harness ADR-0011 zu tunen) — verhindert das „wandernde Ziel".
3. **Degradationsleiter (G14) für MRT:** gemessener MRT → geschätzt aus Luft + Globalstrahlung (Virtual MRT) → **offset = 0** (Operativtemperatur = Lufttemperatur). Jede Stufe mit Quelle/Konfidenz (ADR-0012/0016).
4. **Offset geklemmt** auf einen plausiblen Bereich (gegen MRT-Ausreißer).
5. **Invariante (Verknüpfung K3/ADR-0010):** der MRT-/Operativpfad verbucht **Strahlungs**asymmetrie, der β_s-Pfad den **konvektiven** Eintrag — derselbe Wärmestrom darf nicht zweimal eingehen (Property-Test in ADR-0011).

## Begründung
Eine einzige, geglättete Transformationsstelle ist die K4-Auflösung aus dem Strukturplan; sie hält den Regelkreis in einer konsistenten Größe. Da das Feld MRT nicht rechnet, ist die Lösung Eigenentwicklung — entsprechend mit konservativer Klemmung, sauberer Degradation und Harness-Tuning der Zeitkonstante abgesichert.

## Konsequenzen
**Positiv:** stabiler Regelkreis ohne Pendeln bei wechselnder Einstrahlung; nutzt den MRT-Vorsprung, ohne den Aktor in Operativtemperatur regeln zu müssen; robuste Degradation bis „= Lufttemperatur".
**Negativ/Kosten:** die Zeitkonstante ist ein zu tunender Parameter (zu schnell → Pendeln, zu langsam → träge Komfortkorrektur); die Doppelzählungs-Invariante muss aktiv getestet werden.

## Compliance
Eigenentwicklung; MRT/Operativtemperatur sind generische Eingänge (kein gerätespezifischer Sonderweg).

## Verknüpfungen
Auflösung von K4; sitzt in der Comfort-Schicht (ADR-0005). Zeitkonstante/Invariante werden im Harness (ADR-0011) getunt/getestet; Doppelzählungs-Invariante teilt sich mit ADR-0010.

## Nachtrag (v0.11.0): Virtuelles MRT als Schatten-Schätzer
Bislang degradierte der Operativ→Luft-Pfad ohne MRT/Globe-Sensor auf Identität (operative = Luft). Jetzt liefert ein interner Schätzer ein MRT, sobald keiner konfiguriert ist (Schatten-Prinzip ADR-0026):
- **Pure `comfort/virtual_mrt.py`:** `t_mrt = (1−k)·t_air + k·t_out + g·q_solar`. Term 1+2 = Strahlungskopplung an die Außenhülle (kalte Wände im Winter ziehen MRT unter die Luft → höherer Luftsollwert, schützende Richtung); Term 3 = solarer Strahlungsbonus. `ENV_COUPLING=0.08` ist am Smart-Setpoint-Blueprint geerdet (README-Beispiel −5 °C → ~+2 K Luft), `SOLAR_MRT_GAIN_K=1.5 K` bei voller normierter Sonne (konservativ). Harness-tunebar.
- **Coordinator:** `mrt_internal` läuft immer; ein gemessener MRT-/Globe-Sensor überschreibt nur den verwendeten Wert. Geht in `operative_to_air` (Sollwert) **und** `operative_temperature` (Anzeige). Attribute `mrt`, `mrt_source` (sensor/internal), `mrt_internal`.
- **Keine Doppelzählung (ADR-0010 Punkt 5, jetzt realisiert):** β_s = konvektiver Solareintrag in die Luftbilanz (Lufttemperatur steigt real); MRT-Solarterm = Strahlungsempfinden (getrennte Größe). Beide senken an Sonnentagen die Heizlast, aber über verschiedene physikalische Wege — kein doppelt verbuchter Joule. Invariante getestet (`test_virtual_mrt`).
- **Risiko/Hinweis:** Ohne Fassadenorientierung kann der Solar-MRT-Term in nicht besonnten Räumen den Luftsollwert leicht zu stark senken (Unterheizen). Daher `SOLAR_MRT_GAIN_K` konservativ; in der kalten Saison live beobachten, ggf. reduzieren. Der Kaltwand-Term ist die schützende (mehr heizen) Richtung. Gate v0.11.0: 175 Tests grün.
