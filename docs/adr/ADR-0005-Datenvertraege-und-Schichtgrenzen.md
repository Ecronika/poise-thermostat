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

## Nachtrag (2026-07-21, Phase-9-Refactoring-Migration): `AdoptReason`-Serialisierungs-Stabilität — plain-`str` an der Schichtgrenze, Enum nur als Registry

**Invariante (test-gepinnt).** Über die Schichtgrenze `coordinator.data["mode_adopt_reason"]`/`["sp_adopt_reason"]` und in den Store fließen **plain `str`**, keine Enum-Member. `control.external_override.AdoptReason` (ein expliziter `str`+`Enum`, StrEnum-äquivalent) ist bewusst ein **Vokabular-Registry** dieser Reason-Codes, **nicht** der Laufzeit-Werttyp: die verlagerten Stage-Bodies produzieren weiter verbatim plain `str`, und der Frozen-Datenvertrag (`TickOutcome`/`coordinator.data`) trägt `str`, nicht das Enum.

**Warum kein Enum durch den Datenvertrag.** Enum-Member durch `coordinator.data`/Store zu fädeln würde auf `Enum.__format__`-Semantik reiten, die sich über Python 3.10→3.12/3.13 verschoben hat. Die **pure Suite läuft 3.10, die HA-Suite 3.13** — plain Strings sind die **eine** auf beiden beweisbar identische Repräsentation. Die Enum-Member serialisieren zeichen-exakt wie die historischen plain Strings (`__str__`/`__format__` auf `str` gepinnt; JSON dumpt den `str`-Inhalt), gesichert durch `tests/test_phase7_tracker.py`; die Whitelist im Registry hält die Vokabular-Menge ehrlich, ohne den Wertfluss zu ändern.

Dies ist ein konkretes Beispiel der Grundregel dieses ADR (frozen, schmale, versions-stabile Werttypen an Schichtgrenzen — keine Repräsentation, deren Bytes von der Laufzeitumgebung abhängen). **Code-Ort:** `control/external_override.py::AdoptReason`.
