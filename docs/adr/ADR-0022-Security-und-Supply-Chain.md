# ADR-0022: Security & Supply-Chain

**Status:** Implementiert · **Wirkung:** Live-D · **Datum:** 2026-06-18 (umgesetzt 2026-08-19) · **Bezug:** E30, G28 · **Verifizierung:** Code-Review Versatile/RoomMind/ThermoSmart/BT/Vesta (Thema O)

## Kontext
Die Charta verlangt vollständige Lokalität und anonymisierte, nie automatische Exporte (G28). Offen: Abhängigkeitspolitik, Netzwerkverhalten, Export-/Diagnostics-Datenschutz.

## Entscheidungstreiber
Minimale Angriffs-/Lieferkettenfläche; keine Cloud-Abhängigkeit; keine PII in Exporten/Diagnostics; reproduzierbare Builds.

## Befund am Code (Belege)
- **Abhängigkeiten:** **Versatile = einziges Anti-Pattern** — `requirements: ["numpy","scipy","vtherm_api>=0.3.0"]`, numpy/scipy **ungepinnt** und im Komponenten-Code **nie importiert** (Numerik via stdlib `math`), nur transitiv über `vtherm_api`. **Alle anderen: `requirements: []`** (RoomMind/ThermoSmart/BT) bzw. keiner (Vesta). Kein Cloud-`iot_class`.
- **Netzwerk:** **keiner der fünf** macht eigene REST/Cloud-Calls im Kern; Daten aus lokalen Entities + Recorder (BT `weather.py`), Aktorik über `hass.services.async_call`.
- **Anonymisierung:** **ThermoSmart = Goldstandard** (`export.py`: gesalzener `hashlib.sha256(f"{salt}:{zone_id}")[:12]`, nur Counts/Booleans, dokumentierter „Privacy contract"; **Restschwäche selbst benannt:** Timestamps bleiben → Nutzungsmuster ableitbar). **RoomMind = schwächster** (`diagnostics.py` **ohne** `async_redact_data`: dumpt Config, Entity-IDs, **Personen-IDs samt States**, Skript-Pfade). BT-Diagnostics ebenfalls ohne `async_redact_data`.

## Entscheidung
1. **Null schwere Abhängigkeiten:** `requirements: []`, Numerik in der stdlib (`math`/`statistics`); wird je eine Dep nötig, dann **gepinnt** mit Version-Bound (Versatiles ungepinnte, ungenutzte numpy/scipy sind das ausdrückliche Anti-Pattern).
2. **Vollständig lokal:** `iot_class: local_polling`/`local_push`, **keine** eigenen REST/Cloud-Calls im Kern; alle Eingänge aus lokalen Entities/Recorder. (Der bestehende Open-Meteo-Globalstrahlungssensor ist ein **separater** REST-Sensor außerhalb des Regelkerns; der Kern konsumiert nur dessen Entity.)
3. **Exporte anonymisieren wie ThermoSmart** (gesalzener SHA-256 statt IDs, nur Counts/Booleans, dokumentierter Privacy-Contract) — **plus** Timestamps quantisieren/aggregieren, um ThermoSmarts selbstbenannte Restschwäche zu schließen; nie automatisch senden (G28).
4. **`diagnostics.py` MIT `async_redact_data` + `TO_REDACT`** (Entity-IDs, Personen-IDs, Sensor-IDs, Skript-/Datei-Pfade, Koordinaten) — genau die Lücke von RoomMind **und** BT; teure Reads im Executor (RoomMind-Muster).
5. **Build-/Versionshygiene:** keine Secrets im Repo; manifest-Version als einzige Wahrheitsquelle (ADR-0018); `min_ha_version` gesetzt.

## Begründung
`requirements: []` ist im Feld der Normalfall und reduziert Lieferkettenrisiko maximal; Versatiles ungenutzte, ungepinnte native Deps sind der konkrete Negativbeleg. ThermoSmarts Anonymisierung ist am Code als Bestpraxis belegt; die fehlende Diagnostics-Redaktion (RoomMind/BT) ist die zu schließende Lücke. Lokalität ist ohnehin Charta-Pflicht.

## Konsequenzen
**Positiv:** minimale Angriffs-/Lieferkettenfläche; keine Cloud; datenschutzkonforme Exporte/Diagnostics; reproduzierbare Builds.
**Negativ/Kosten:** Verzicht auf numpy/scipy bedeutet Eigenimplementierung numerischer Routinen in der stdlib (EKF/MPC ohne BLAS) — bewusst akzeptiert für die schmale Lieferkette; Anonymisierungs-/Redaktions-Listen müssen bei neuen Feldern gepflegt werden.

## Compliance
Erfüllt G28 (lokal, anonymisiert, nie automatisch). Eigenständige Umsetzung.

## Umsetzungsstand (2026-08-19)
Alle fünf Entscheidungen sind im Code:
1. `manifest.json` `requirements: []`, Numerik stdlib (EKF/MPC ohne BLAS).
2. `iot_class: local_polling`, keine REST/Cloud-Calls im Kern (Import-Audit: nur stdlib + HA).
3. **Export-Anonymisierung geschlossen:** Trace-Zeitstempel werden quantisiert
   (`trace/schema.py::TRACE_TS_QUANTUM_S` = 900 s, `mono` als Replay-dt-Quelle bleibt
   exakt — ADR-0014-Determinismus unberührt) und der Trace-Dateiname trägt den
   gesalzenen SHA-256-Slug statt der Entry-ID (`trace/recorder.py::salted_trace_slug`,
   Salt = HA-Installations-ID; ThermoSmart-Muster). Die Record-Zeilen selbst tragen
   keine Zonen-Identität. Löschpfad räumt salted- und Alt-Namen samt Rotation.
4. `diagnostics/` redigiert 28 ID-tragende Schlüssel (`async_redact_data`-Muster).
5. Keine Secrets; Version einquellig (Gate `test_version_consistency`).

## Verknüpfungen
Diagnostics-Redaktion ergänzt ADR-0012; Versionsquelle/`min_ha_version` aus ADR-0018; stdlib-Numerik berührt ADR-0001/0009 (kein BLAS). Globalstrahlungssensor bleibt externer Eingang (Strukturplan-Ebene 0).
