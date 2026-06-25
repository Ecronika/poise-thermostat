# ADR-0029: Generische Geräte-Quirks (devices/model_fixes)

**Status:** akzeptiert · **Datum:** 2026-06-20 · **Bezug:** ADR-0015 (Capability-Matrix), ADR-0012 (Repair-Issues), Charta „Allgemeingültigkeit" (keine modellspezifischen Sonderwege), Phase 3 · **Verifizierung:** Z2M-Geräteseite SRTS-A01 (vollständige Exposes), Live-29-Entitäten

## Kontext
Die Aqara E1 (SRTS-A01) exponiert **keine** Ventilposition/`pi_heating_demand` (Firmware-Limit, code-verifiziert) — direkte Duty-Modulation bleibt unmöglich. Sie exponiert aber nützliche Funktionen, die der Regler beachten/nutzen sollte: einen **geräteinternen Wochenplan** (kämpft gegen Poise), eine **valve_alarm/Fault**-Meldung, **Batterie**, und einen **external_temperature_input**. Die Charta verbietet modellspezifische Sonderlösungen — alles muss **generisch** (capability-erkannt) sein.

## Entscheidung
Pure `devices/model_fixes.py` (Klassifizierer/Schwellen, getestet) + Coordinator-Glue (Registry-Lookup einmalig, Service-Calls, Repair-Issues). Vier capability-erkannte Quirks, **kein Modellname**:
1. **Interner Geräte-Zeitplan:** auf dem Aktor-Gerät wird ein `switch.*schedule*` erkannt; ist er `on`, Repair-Issue `device_schedule` (er übersteuert Poise — Nutzer schaltet ihn ab).
2. **Fault/valve_alarm:** ein `binary_sensor` mit alarm/fault/problem im Namen; ist er `on`, Repair-Issue `device_alarm` **und** Einspeisung in die Heizausfall-Erkennung (`failed = detector or fault_active`).
3. **Batterie:** Sensor `device_class=battery` ≤ `LOW_BATTERY_PCT` (15 %) → Repair-Issue `low_battery`.
4. **Externer Temperatur-Eingang:** optionales Config-Feld `trv_external_temp_input` (Number-Entity). Ist es gesetzt, schreibt Poise je Tick die **fusionierte Raum-Lufttemperatur** dorthin (`number.set_value`), sodass ein auf externen Sensor kalibrierbares Thermostat gegen die *echte* Raumtemperatur moduliert. Sollwert (operativ-korrigiert) geht weiter an die Climate-Entity; beide Schreibvorgänge gehören **einem** logischen Regler (kein Mehrfachschreiber-Konflikt, ADR-0013) — der Nutzer muss eine konkurrierende Fremd-Automation (z. B. pavax) auf dieselbe Number deaktivieren.

## Begründung
Capability-Erkennung statt Modellname hält es allgemeingültig (Charta) und ADR-0015-konform. #1–#3 nutzen die schon vorhandene Repair-Issue-Infrastruktur (ADR-0012). #4 holt den einzigen echten Regel-Hebel der E1 (interne Proportionalmodulation gegen genaue Temperatur) generisch in die Integration — ohne Ventilposition, die es nicht gibt.

## Konsequenzen
**Positiv:** der wichtigste Footgun (kämpfender Geräte-Zeitplan) wird sichtbar; Gerätefehler/Batterie werden gemeldet; präzise Temperatur-Einspeisung verbessert die TRV-interne Modulation generisch. **Negativ/Offen:** (a) Klassifizierer namensheuristisch (schedule/alarm im entity_id) — robust für Z2M/ZHA-Namensschema, ggf. später per device_class verschärfen; (b) #4 erfordert Nutzer-Disziplin gegen Doppelschreiber (dokumentiert); (c) Multi-Backend-„Adapter" (deconz/tado) bleiben unnötig, da Poise generisch auf HA-Entitäten arbeitet.

## Nachtrag (v0.18.0): Operativer TRV-Eingangsmodus, fehlertolerant
Konventionsklärung: Poise schreibt standardmäßig einen **Luft**-Sollwert (operativ→Luft, ADR-0017) und speist (bei #4) die **Luft**-Raumtemperatur ein → „Luft auf beiden Seiten". Die Alternative ist „Operativ auf beiden Seiten" (operativen Sollwert schreiben + operative Temperatur einspeisen; die MRT-Korrektur lebt im eingespeisten Signal). **Beide konsistent, aber nicht mischbar.**
- **Config:** `operative_input` (Bool, Default aus). An → operativer Modus.
- **Operativer Modus aktiv** nur wenn ein **gültiger** externer Temperatureingang vorhanden ist (`trv_external_temp_input` konfiguriert ∧ Entity verfügbar). Dann: `comfort_decide` mit `t_mrt=None` und `room=operative_temperature(room, t_mrt)` → Sollwert = operatives Ziel, Modus-Entscheidung operativ-konsistent; eingespeist wird `operative_temperature(room, t_mrt)`.
- **Fehlertoleranz:** ist `operative_input` an, aber **kein nutzbarer** externer Eingang verfügbar → **automatischer Fallback auf Luftseite** (operativ→Luft) **plus Repair-Issue** `operative_unsupported`. So bleibt ein Thermostat, das nicht auf einen externen Sensor kalibrierbar ist, korrekt luftgeregelt.
- **Diagnose:** Attribut `trv_input_mode` (operative/air/none). Der EKF lernt weiterhin auf **Luft** (physikalisch korrekt); nur die Komfort-/Sollwert-/Einspeise-Schicht wechselt die Konvention. Gate v0.18.0: 199 Tests grün.

## Nachtrag (v0.19.0): Auto-Erkennung des externen Eingangs + Sensor-Select (pavax-verifiziert)
Quelle: pavax-Gist `8d6ed250765d89cb281d4a1762b8d2e8` (Z2M Aqara TRV E1 external temperature). **Verifizierte Methodik:**
- **Auto-Erkennung am Gerät:** das `select`, dessen `options` „external" enthält (Sensor-Quelle), und das `number`, dessen entity_id „external" enthält (Eingang). Generisch, kein Modellname.
- **Sensor-Select MUSS „external" sein**, sonst ignoriert der TRV den eingespeisten Wert; pavax wartet nach dem Umschalten 10 s vor dem Schreiben.
- Der `external_temperature_input` ist **write-only** (Z2M kann nicht zurücklesen) → HA-State „unknown" ist normal; nur „unavailable" = Gerät offline.

**Umsetzung (kein User-Input fürs Plumbing):** `_resolve_device_guards` erkennt zusätzlich `_ext_temp_auto` (Number) + `_sensor_select` (Select mit external-Option). Effektiver Eingang = explizites Config-Feld `trv_external_temp_input` **oder** (bei `operative_input` an) der auto-erkannte. `ext_ok` jetzt `state != "unavailable"` (write-only-„unknown" erlaubt — Fix ggü. v0.18.0). Beim Einspeisen: ist der Select ≠ external, wird er auf external gesetzt und der Number-Write **diesen Tick übersprungen** (Settle; nächster 60-s-Tick schreibt) — ersetzt pavax' 10-s-Delay. Pure Klassifizierer `looks_like_external_temp_number` / `is_external_sensor_select` (getestet). Damit reicht der Schalter „Operativ ein" — Poise findet Eingang + Select selbst. **Unterschied zu pavax:** dessen Quell-Sensor-Ausfall→Select=internal-Fallback deckt Poise über eigene Degradation (frühes Return bei air=None + Repair-Issues) ab; im operativen Modus wäre ein Umschalten auf internal sogar konventionswidrig. Gate v0.19.0: 201 Tests grün.
