# ADR-0005: Datenverträge & Schichtgrenzen

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-18 · **Bezug:** E1, E2 · **Verifizierung:** Code-Review RoomMind/Versatile/ThermoSmart/Vesta (Thema A)

## Kontext
Der Strukturplan reicht typisierte Objekte durch die Pipeline (`Reading → ThermalState → ComfortCorridor → ControlRequest → ActuatorCommand`). Offen ist, wie diese Verträge und die Modul-Abhängigkeiten technisch umzusetzen sind.

## Entscheidungstreiber
Typsicherheit/Testbarkeit, klare nach-unten gerichtete Abhängigkeit, Isolierbarkeit der Schichten, Vermeidung versteckter Kopplung.

## Befund am Code (Belege)
- **Niemand typisiert seine Domänendaten vollständig.** Einziger echter Werttyp im Feld: RoomMind `TargetTemps` (`NamedTuple`, `const.py`); der zentrale Raumzustand ist dort dennoch ein ~40-Schlüssel-**plain dict** (`_build_room_state_dict`). ThermoSmart/Vesta durchgängig plain dicts; Versatile kapselt Zustand in Manager-`@property`.
- **RoomMind = vorbildlicher Composition-Root mit echter DI:** der Coordinator instanziiert alle Manager und injiziert geteilte Objekte (`EkfTrainingManager(self._model_manager)`, `MPCController(..., model_manager=…, target_resolver=…)`); klare `async_evaluate()` (Entscheidung) ↔ `async_apply()` (Ausführung)-Trennung.
- **Versatile = sauberer ABC-Vertrag** (`BaseFeatureManager`: einheitlicher Lifecycle `post_init/start_listening/is_configured`) — **aber** mit globalem Singleton-Service-Locator (`VersatileThermostatAPI.get_vtherm_api()`), der Feature-Manager hart an die globale API koppelt.
- **Negativbelege:** ThermoSmart webt Zustand über Mixins in ein Mono-`self` (nicht isoliert testbar); Vesta zieht Abhängigkeiten ad-hoc aus `hass.data[DOMAIN]` (keine DI).

## Entscheidung
1. **Frozen, schmale Werttypen an jeder Schichtgrenze:** `@dataclass(frozen=True, slots=True)` für die fünf Verträge, mit Einheiten, Defaults und Validierung. **Keine plain dicts über Modulgrenzen** (die gemeinsame Feld-Schwäche). RoomMinds `TargetTemps` belegt die Lesbarkeit; wir gehen einen Schritt weiter zu frozen dataclasses.
2. **`Protocol`/ABC je Schicht** nach Versatiles `BaseFeatureManager`-Muster (einheitlicher Lifecycle `update_config()/is_configured/evaluate()`) — **ohne** globalen Singleton.
3. **Eine Composition-Root** (Coordinator) verdrahtet `Estimator → Controller → Actuator` per Konstruktor-DI (RoomMind-Muster). Abhängigkeit strikt **nach unten**: Actuator kennt weder Controller noch Estimator; Controller bekommt `ThermalState`+`ComfortCorridor`, gibt `ControlRequest`; ein dünner Actuator übersetzt zu `ActuatorCommand`→Service-Call (Vestas `_set_heaters`-Choke-Point + RoomMinds evaluate/apply-Split).

## Begründung
Die Kombination nimmt von jedem Vorbild die Stärke (RoomMind DI + evaluate/apply, Versatile ABC-Lifecycle, Vesta Choke-Point) und schließt die im ganzen Feld offene Lücke (keine typisierten Grenzen). Singleton-Service-Locator und Mixin-Mono-`self` werden bewusst gemieden, weil sie Schichten unteilbar koppeln und Tests verhindern (G27).

## Konsequenzen
**Positiv:** statisch prüfbare Grenzen (mypy), isoliert testbare Schichten, klare Abhängigkeitsrichtung, kein verstecktes Global-State.
**Negativ/Kosten:** mehr Boilerplate (Vertragstypen + Protokolle); Disziplin nötig, Verträge stabil zu halten (Versionierung der Verträge bei Änderung).

## Compliance
Muster (DI, ABC, frozen dataclass) sind Allgemeingut; eigenständige Umsetzung, kein Code-Copy. Generisch.

## Verknüpfungen
Konkretisiert ADR-0002 (`RCModel` ist Teil von `ThermalState`). Fundament für ADR-0006 (Tick ruft die Schichten in Vertragsreihenfolge). Folge: Vertrags-Schemaversionierung (gehört zu ADR-0007).
