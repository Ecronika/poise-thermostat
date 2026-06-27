# ADR-0022: Security & Supply-Chain

**Status:** In Arbeit (75 %) · **Datum:** 2026-06-18 · **Bezug:** E30, G28 · **Verifizierung:** Code-Review Versatile/RoomMind/ThermoSmart/BT/Vesta (Thema O)

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

## Verknüpfungen
Diagnostics-Redaktion ergänzt ADR-0012; Versionsquelle/`min_ha_version` aus ADR-0018; stdlib-Numerik berührt ADR-0001/0009 (kein BLAS). Globalstrahlungssensor bleibt externer Eingang (Strukturplan-Ebene 0).
