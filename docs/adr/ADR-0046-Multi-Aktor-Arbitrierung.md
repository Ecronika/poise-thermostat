# ADR-0046 — Mehrere Klimaaktoren je Raum: Arbitrierung (thermisch / Feuchte / Lüften)

**Status:** In Arbeit (20 %) · **Datum:** 2026-06-27 · **Bezug:** Poise v0.89.0; ADR-0005 (Pure-Core/Glue), ADR-0012 (Safety/Window/Heating-Failure), ADR-0013/0038 (Hub), ADR-0023 (Dual-Setpoint), ADR-0035 (Constraint-Solver, Präzedenz), ADR-0042 (Override).
**Konsolidiert aus:** zwei Arbeits-Designdokumenten (Projekt-Arbeitsstand: Best-of-Multi-Aktor + Begleitdokument Lüften/Trocknen/Feuchte), Wettbewerber-Quelltext (dual_smart_thermostat, Versatile Thermostat, climate_group_helper), HA-Community/GitHub-Nutzerfeedback, HA-Dev-Doku — und zwei externen Design-Reviews. Frühere `ZoneActuator`-/monolithische `select_actuators`-Modelle aus den Arbeitsdokumenten sind **veraltet, nicht implementieren** — maßgeblich ist allein dieses Dokument.

---

## 1. Kontext & Entscheidung

HA hat Lösungen für *ein* Gerät regeln, *mehrere synchronisieren* oder *Heizbedarf aggregieren* — aber **keine** arbitriert pro Raum mehrere klimarelevante Aktoren nach Richtung, Kosten, Komfort, Feuchte, Lüftung und Geräteschutz. Poise heute = **ein Aktor pro Zone** (`CONF_ACTUATOR`, ein `climate`-Entity). Entscheidung: eine **reine, capability-getriebene Arbitrierungsschicht** zwischen Komfortkern/Solver und Aktuierung; Komfortkern (ADR-0023) und Solver (ADR-0035) bleiben unverändert.

**Leitplanke (gegen „fragile Super-Automation"):** Der **MVP ist rein thermisch**. Feuchte/Lüften/Hub-Ressourcen sind strikt phasiert (§14). Disziplin wie immer: **pure → Shadow → opt-in live**, Diagnose zuerst.

### 1.1 Ziel / Nicht-Ziele
**Ziel:** Pro Zone ≥1 Aktor; bei mehreren *fähigen* Quellen entscheiden, **welches Gerät** (und bei Mehrzweckgeräten **welche Fähigkeit**) die Anforderung bedient — inkl. des Kernfalls **heizfähige AC vs. Heiz-TRV**. Failover, Staging/Boost, sichere Standby-Zustände, Geräteschutz.
**Nicht-Ziele:** keine zertifizierte Anlagen-/Lüftungsbemessung; kein verbindliches COP/JAZ-Modell; kein anteiliges Mischen zweier laufender Quellen (nur Single-Active + bewusster Boost). Normbezug = **„norm-informed comfort & health guardrails"**, nicht „norm-compliant control".

---

## 2. Datenmodell

```python
# Achsen & Richtungen
Axis      = Literal["thermal", "air_movement", "ventilation", "humidity"]
Direction = Literal["heat","cool","fan","exhaust","supply","balanced","recirculate","dry","humidify"]

@dataclass(frozen=True)
class DeviceCapability:
    axis: Axis
    direction: Direction
    mode_command: str | None          # was der Adapter setzen muss (hvac_mode / preset / service)
    setpoint_command: str | None      # falls sollwertfähig
    supports_modulation: bool = False
    priority: int = 100               # kleiner = bevorzugt, je Richtung
    cost_model: CostModel | None = None
    comfort_model: ComfortModel | None = None

@dataclass(frozen=True)
class ZoneDevice:
    entity_id: str
    adapter: str                      # ClimateAdapter | FanAdapter | … (s. §3)
    capabilities: tuple[DeviceCapability, ...]
    ownership_policy: OwnershipPolicy
    standby_policy: StandbyPolicy     # s. §7
    min_on_s: float; min_off_s: float; min_mode_hold_s: float
    max_starts_per_h: int | None
    mode_change_deadtime_s: float
    noise_class: int | None           # 0..3
    location: str | None              # z. B. „Aufenthaltszone"
    shared_resource_id: str | None    # geteilte Ressource (s. §10)
```

Eine reversible AC = **ein** `ZoneDevice` mit Capabilities {thermal:heat, thermal:cool, air_movement:recirculate(fan), humidity:dry}. Das löst „**ein `hvac_mode` pro Gerät und Tick**": die Pipeline wählt höchstens **eine** Capability je Gerät pro Tick.

---

## 3. Adapter-Vertrag (Phase-0-Liefergegenstand)

Domänen-Adapter kapseln HA-Eigenheiten; alles darüber ist pur. **Minimalinterface** (verbindlich):

```python
class DeviceAdapter(Protocol):
    def discover_capabilities(self, state) -> list[DeviceCapability]: ...
    def current_mode(self, state) -> DeviceMode: ...
    def current_setpoint(self, state) -> float | None: ...
    def current_action(self, state) -> DeviceAction | None: ...     # heating/cooling/drying/fan/idle/off
    def build_command(self, capability, target, context) -> Command: ...
    def build_standby_command(self, policy, context) -> Command | None: ...
    def is_external_override(self, state, last_command) -> bool: ...
    def health(self, state) -> DeviceHealth: ...                    # ok/unavailable/fault/stale/lockout
```

**`Command` als Vertrag (Idempotenz & Echo-Erkennung).** Jeder vom Adapter gebaute Befehl trägt mindestens:

```python
@dataclass(frozen=True)
class Command:
    entity_id: str
    domain: str
    service: str
    data: Mapping[str, Any]
    capability_id: str          # welche DeviceCapability ihn auslöste
    reason: ReasonCode          # warum (§11)
    issued_at_wall: float       # Wall-Clock (nicht monotonic), s. §8
    dedupe_key: str             # idempotenter Schlüssel → Deadband/No-Repeat
    expected_echo: Mapping[str, Any]  # erwarteter Folgezustand (mode/setpoint)
```

`is_external_override(state, last_command)` prüft auf dieser Basis: weicht der beobachtete Zustand vom `expected_echo` des letzten Poise-Befehls ab — **nach** Ablauf einer Echo-Toleranzzeit (Geräte spiegeln verzögert) — gilt es als Fremdeingriff (→ §9). `dedupe_key` unterdrückt redundante Writes (Single-Writer/Deadband pro Gerät).

Implementierungen: `ClimateAdapter, FanAdapter, HumidifierAdapter, SwitchAdapter, NumberValveAdapter, SelectPresetAdapter, ScriptServiceAdapter, Remote/IRAdapter`. Discovery liest `hvac_modes`/`fan_modes`/`preset_modes`/`min/max/step`, unterscheidet **`dry`/`fan_only` als `hvac_mode` vs. `preset_mode`**, **niemals Mode-Strings hardcoden** (Gree/Midea-Zahlen, Honeywell `heat_cool`, fehlendes `auto`). Quirks via bestehende `model_fixes`-Schicht (ADR-0029). Discovery-Fehler → **degradiert auf sichere bekannte Capability oder `unavailable`, nie auf Raten** (§15).

---

## 4. Resolver-Pipeline (statt Monolith)

Fünf reine, tabellengetestete Funktionen:
1. `thermal_resolver` → gewünschte thermische Aktion + Kandidaten (Quellenwahl §6).
2. `humidity_resolver` → entfeuchten/befeuchten + Kandidaten.
3. `air_movement_resolver` → Luftbewegung/Free-Cooling + Kandidaten.
4. `device_conflict_resolver` → **ein-Modus-pro-Gerät** auflösen (Achsen-Priorität §5), geteilte Ressourcen (§10), Min-Cycle/Lease-Sperren.
5. `assignment_planner` → finales `{entity: Command}` + **Reason-Objekt** (§11).

**P0/P1-Scope (hart thermisch):** `humidity_resolver` und `air_movement_resolver` existieren in P0/P1 **nur als No-op-Stubs** mit stabilem Interface + Reasons — sie treffen **keine** aktiven Entscheidungen und erzeugen **keine** Commands. Erst P4–P7 aktivieren sie. So bleibt der MVP rein thermisch und P0 wächst nicht unbemerkt.

Tick-Einbettung (minimal-invasiv): `comfort.decide → constraints.resolve(target) → pipeline → for device: should_write → adapter.build_command → write`. `capability`/`device_max`/`_last_written_mode`/Deadband **pro Gerät**.

---

## 5. Präzedenz (erweitert ADR-0035)

1. **SAFETY:** Frost, Geräte-Min/Max, Sensor-Fehler/Stale-Failsafe, **Kompressor-Min-Off**, Fenster offen.
2. **HEALTH:** Schimmel-/**Kondensations**-Vermeidung, Über-Feuchte, **Taupunkt-Kühlkappe**, (optional IAQ/CO₂).
3. **COMFORT-thermisch** (operative Temp im Band) → 4. **COMFORT-Feuchte** (muffig/trocken, ohne Health-Risiko) → 5. **COMFORT-Luftbewegung** (Fan-Komfort, Coast) → 6. **Efficiency** (Kosten/COP/Preis/CO₂) → 7. **Noise**.
Leitplanken: Befeuchter erzeugt **nie** Kondensation; Entfeuchter kühlt **nicht** aus, wenn Heizbedarf besteht; Health kann thermischen Komfort schlagen, aber begrenzt.

---

## 6. Thermische Arbitrierung & Effizienz-Ehrlichkeit

**Kandidatenfilter:** Richtung gekonnt **und** gesund/verfügbar/nicht im Lockout. Fällt einer weg → nächster → **Failover gratis**.
**Rangordnung:** (1) explizite `priority` je Richtung → (2) Energiequelle/COP **nur mit Daten** → (3) Komfort/Geschwindigkeit/Zeit/Lärm → (4) stabiler Tie-Break (`priority`, dann `entity_id`).
**Single-Active default;** mehrere Quellen nur als **bedarfsgetriebener Boost** (Primär hält Sollwert über ein Fenster nicht → Sekundär additiv, mit Hysterese/Mindesthaltezeit).
**Effizienz ehrlich:** `cop_balance_c` **Default `None` → KEIN automatischer COP-Wechsel.** Erst wenn der Nutzer „Wärmepumpe vs. Brennstoff" aktiviert, wird ein **vorgeschlagener** Startwert 0 °C angeboten. Für stärkere Aussagen optional `energy_price_sensor`, `marginal_cost_sensor`, `cop_curve`, `carbon_intensity_sensor`, `min_runtime_cost`. **Ohne Daten** sagt Poise „**nutzer-priorisierte/heuristische Quelle**", nie „günstigste".
**UI-Ehrlichkeit:** Solange kein echter COP hinterlegt ist, heißt das Feld **nicht** „COP-Balancepunkt", sondern **„Umschalttemperatur Wärmepumpe ↔ Heizkreis"** mit Untertitel **„Heuristik. Kein garantierter Kostenvergleich."**

---

## 7. Standby-Policy je Gerätetyp (mit Sicherheitsminimum)

Pauschales `off` ist falsch. Policy-Optionen: `off | hold_safe_setpoint | fan_only_low | leave_as_is | restore_previous | eco`. **Defaults + harte Sicherheitsregel:**

| Gerät | Default Standby | Sicherheitsregel (immer) |
|---|---|---|
| TRV | `hold_safe_setpoint` | Frost-/Schimmel-Floor nie unterschreiten |
| AC reversibel | **`off`** (konservativ) | bei Heat/Cool-Konflikt **nie im Gegenmodus** lassen |
| Entfeuchter | `leave_as_is` *oder* `off` | bei Tank-voll/Fault sofort `off` |
| Befeuchter | `off` | Kondensationsdeckel **hart** |
| Ventilator | `off` *oder* `leave_as_is` | kein Health-Override |

**AC-Standby konservativ:** Default **`off`**, weil manche ACs in `fan` dauerhaft mehr verbrauchen, hörbar sind oder nach Kühlung Feuchte re-evaporieren. **`fan_only_low`** ist ein **Opt-in-Komfortfeature** („Coast-in-fan"), das der Nutzer bewusst aktiviert; Ausnahme: Gerät verliert in `off` seinen Zustand/Silent-Status und der Nutzer bestätigt — dann `fan_only_low`.

---

## 8. Per-Device-Lifecycle / Anti-Short-Cycle (Phase 0, nicht Detail)

Pro Gerät **und** Achse: `min_on`, `min_off`, `min_mode_hold`, `max_starts_per_hour`, `mode_change_deadtime`, Sperrzustände `defrost/lockout`, `drain/full_bucket/fault`. **Kompressor-Min-Off 10–20 min** (Community). Eine Anforderung bei laufendem `min_off` **startet nicht**, sondern **diagnostiziert den Grund** (`compressor_min_off_active`).

**Neustart-Persistenz:** Persistiert werden **Wall-Clock-Zeitstempel, nicht monotonic time** (monotonic ist über einen HA-Neustart nicht übertragbar; vgl. ADR-0006/0007). Beim Restore wird die **verbleibende Sperrzeit** aus `now_wall − issued_at_wall` berechnet. Bei **offensichtlich falscher Systemzeit oder sehr altem Zustand** wird **konservativ** entschieden: lieber `min_off` einhalten als den Verdichter versehentlich sofort starten. Persistiert: last command (`expected_echo`), min-on/off-Timer, mode-hold, Lease, Health.

**Verortung aus dem Meinungsbild Fenster/Kühlen (B/C):** Der wiederkehrende **AC-Kurzzyklus**-Schmerzpunkt ist genau dieses §8-Thema (`min_off`, P2) — wirksam, sobald die AC über die Multi-Pipeline läuft; im **Standalone-Single-AC-Betrieb** (Sollwert + Modus an `climate`) übernimmt den Verdichterschutz die **Geräte-Firmware**. Eine **`fan_only`-Fenster-/Lüften-Aktion** (statt `off`) nutzt die Luftbewegungs-Capability (§4/§7); ihr **Fenster-Auslöser** liegt jedoch in **ADR-0041** — die *konfigurierbare* Fensteraktion (`off | fan_only | setback`) ist daher eine ADR-0041-Erweiterung (eigenes künftiges ADR), nicht Teil dieses ADR.

---

## 9. Ownership / Lease / Manual-Override (harte Invariante)

Poise schreibt ein Gerät **nur mit Lease**. Fremdänderung (Nutzer/andere Integration) → **`external_override`** (`adapter.is_external_override` auf Basis `expected_echo`, §3). Rückkehr per Policy: `immediate | timer | comfort_window | explicit_reenable` (nutzt ADR-0042). Verhindert das von Nutzern gehasste sofortige Wegschalten eines manuell eingeschalteten Geräts.

---

## 10. Geteilte Ressourcen (Hub-Policy)

`shared_resource_id` markiert Multi-Split-Außeneinheit, ducted AC, zentralen Entfeuchter, KWL, einen Heizkreis für mehrere TRVs. **Zone-Policy** wählt die lokale Quelle; **Hub-Policy** entscheidet die geteilte Ressource. **Konfliktklassen:**

| Klasse | Beschreibung | Hub-Reaktion |
|---|---|---|
| `same_resource_same_direction` | zwei Räume wollen dieselbe ducted AC kühlen | erlauben / aggregieren / priorisieren |
| `same_resource_opposite_direction` | Raum A heizen, Raum B kühlen über dasselbe Gerät | **blockieren** oder priorisieren (kein Gegenmodus) |
| `capacity_limit` | Ressource reicht nicht für alle | Load-Shedding (ADR-0013-Reuse) |
| `mode_lock` | Multi-Split-Außengerät nur Heat **oder** Cool für alle Innengeräte | Modus-Mehrheits-/Prioritätsentscheid, Rest in Standby |
| `min_cycle_lock` | Ressource darf gerade nicht umschalten | warten, Reason |
| `manual_resource_override` | Nutzer hat zentrale Einheit manuell gesetzt | respektieren (Lease) |

**Abgrenzung:** ADR-0046 definiert hier **nur den Vertrag** für `shared_resource_id` und die Konfliktklassen. Die **konkrete Hub-Arbitration** (Auflösungsalgorithmus, Prioritätsmodell, Load-Shedding-Mechanik) wird in einer **separaten ADR** spezifiziert, **bevor P8** umgesetzt wird — baut auf ADR-0013/0038 auf. So bleibt ADR-0046 fokussiert und P8 explodiert nicht.

---

## 11. Reason- / Diagnostics-Vertrag (Enum/API, ab Phase 0 stabil)

Pro Tick liefert die Pipeline ein **strukturiertes** Reason-Objekt mit **vier getrennten Feldern**:
- `selected_source: entity_id | None`
- `reason: ReasonCode` (warum diese Quelle/Aktion)
- `blocked: list[BlockingCause]` (was Alternativen verhinderte)
- `fallback: FallbackCause | None`

Beispiel: `selected_source=climate.schlafzimmer_ac`, `reason=thermal_heat_cost_preferred`, `blocked=[trv_min_cycle_active]`, `fallback=none`.

**Was Vertrag ist und was nicht:**
- `ReasonCode`/`BlockingCause`/`FallbackCause` sind **stabil, englisch/technisch** — der eigentliche API-Vertrag (Tests, Diagnostics, Support hängen daran).
- **Nutzertext** kommt aus `strings.json`/Translation-Keys (lokalisierbar) — **nicht** Teil des Core-Vertrags (ADR-0021).
- **Debug-Details** dürfen sich **erweitern**, vorhandene Keys bleiben kompatibel.
- **Card-Chips/Emoji** sind **UI-Hinweise**, kein Core-Vertrag.

**Reason-Tabelle (Auszug; Code = Vertrag, Nutzertext = Translation):**

| Code | Achse | Severity | Nutzertext (de, aus strings.json) | Debug-Detail | Card-Chip (UI) |
|---|---|---|---|---|---|
| `thermal_heat_cost_preferred` | thermal | info | „Heizt mit AC-Wärmepumpe (günstiger)" | `outdoor`, `cop_balance_c` | 🔥WP |
| `thermal_heat_priority` | thermal | info | „Heizt mit TRV (Priorität)" | `priority` | 🔥TRV |
| `boost_secondary_added` | thermal | info | „Boost: zweite Quelle zugeschaltet" | `gap`, `window_s` | ⚡Boost |
| `failover_primary_unhealthy` | thermal | warn | „Wechsel auf Reserve (Primär gestört)" | `health` | ↺Failover |
| `compressor_min_off_active` | thermal | info | „Start verzögert (Verdichterschutz)" | `min_off_s`, `remaining` | ⏳ |
| `device_external_override` | any | warn | „Manuell übersteuert" | `since`, `return_policy` | ✋ |
| `air_movement_credit_applied` | air | info | „Ventilator hebt Kühlkante (+X K)" | `credit_k`, `occupied` | 🌀 |
| `free_cooling_blocked_outdoor_more_humid` | air/hum | info | „Free-Cooling gesperrt: Außenluft feuchter" | `abs_hum_in/out` | — |
| `ac_dry_blocked_would_overcool` | humidity | info | „Entfeuchten via AC würde auskühlen" | `room`, `floor` | — |
| `humidify_capped_condensation_risk` | humidity | warn | „Befeuchten gedeckelt (Kondensationsrisiko)" | `glass_t`, `dewpoint` | 💧Cap |
| `shared_resource_busy` | thermal | info | „Geteiltes Gerät anders belegt" | `resource_id`, `owner` | 🔒 |

Speist Lovelace-Card (ADR-0040), Diagnostics (ADR-0012), Tests, Support.

---

## 12. UX / Progressive Disclosure

**Leitprinzip:** Komplexität ist *optional*, nicht *sichtbar*. Erst-Setup = unverzichtbares Minimum; alles mit „so ist es meistens passend"-Default wird **gesetzt, nicht gefragt**; Anpassung ist ein bewusster späterer Schritt. Drei HA-native Hebel:

**(1) Capability-getriebene Auslassung (primär).** Dynamisches Schema zeigt nur, was die echten Geräte/Sensoren können.
**(2) Config-Subentries.** Erst-Setup = Zone mit **einem** Aktor; weiterer Aktor = Subentry-Flow „Gerät hinzufügen", der **erst dann** die Arbitrierungs-Schicht freischaltet → Single-TRV-Nutzer sieht Arbitrierung nie.
**(3) Options-Flow gestaffelt.** `async_show_menu` (Komfort/Geräte/Feuchte*/Erweitert), collapsible `section({"collapsed":True})` für Tiefe (Auslassung bleibt primär — Frontend-`collapsed`-Bug in 2026.6.x), `show_advanced_options` für die tiefsten Knöpfe (COP-Kurve, `marginal_cost_sensor`, `mode_change_deadtime`, Adapter-Override).

**Erst-Setup = genau drei Felder:** **Raumsensor, Aktor, Anzeigename (optional/auto).** Komfort-Basistemp und Kategorie haben Defaults und liegen im **Options-Flow** (nicht im Create-Schritt).

**Sichtbarkeits-Matrix:**

| Konstellation | Zusätzlich sichtbar | Unsichtbar |
|---|---|---|
| 1 Heiz-TRV | (nur die 3 Felder) | cool/fan/dry/Feuchte/Arbitrierung/COP/Standby/Mehr-Geräte |
| 1 reversible AC | Kühlen; Fan-Coast/Kredit *nur wenn `fan_only`*; Dry *nur wenn `dry`* | Arbitrierung, COP |
| ≥2 thermische Quellen | Quellenwahl (Priorität, opt. Umschalttemperatur), Standby je Gerät, Boost | Feuchte/Lüften (bis Sensor/Aktor da) |
| + Feuchtesensor + Feuchte-Aktor | Feuchte-Achse | — |

**Defaults „gesetzt, nicht gefragt" (Auszug):** Single-Active; `cop_balance_c=None`; Standby TRV `hold_safe_setpoint` / **AC `off`** (`fan_only_low` nur opt-in); Kompressor `min_off` 10 min; Luftbewegungs-Kredit **aus** (braucht Präsenz/Freigabe); Feuchte-Achse **aus** bis Sensor+Aktor da; Override-Rückkehr `comfort_window`.

Der **Schema-Builder ist rein** (Phase-0-tabellentestbar: „gegeben Geräte-Menü → welche Felder").

---

## 13. Migration `CONF_ACTUATOR` → `ZoneDevice`

- Bestehendes `CONF_ACTUATOR` wird beim Laden zum **ersten `ZoneDevice`** migriert (Adapter aus Entity-Domäne abgeleitet).
- **Entity-IDs der Zone bleiben stabil**; gelerntes EKF-Modell bleibt **pro Zone** erhalten (ADR-0007).
- Alte Optionen bleiben gültig (Defaults füllen neue Felder).
- **Reconfigure** unterscheidet Single- vs. Multi-Actor (Single bleibt 3-Feld-clean).
- **Downgrade** nicht garantiert, aber dokumentiert (Subentries fehlen in alten Versionen).

**Read-Path früh, Storage-Migration spät:** Schon ab **P0/P1** wird intern aus altem `CONF_ACTUATOR` ein **transienter `ZoneDevice`** gebaut (reine Adapter-Funktion, kein Schema-/Storage-Eingriff). Dadurch läuft der neue Core/Shadow bereits **gegen Bestandskonfiguration**, ohne das Config-Schema zu ändern. Die **persistente Storage-Migration** (Subentries, neue Felder dauerhaft) erfolgt erst in **P3**, wenn Multi-Actor live geht. Single-Actor-Nutzer bleiben bis dahin unberührt.

---

## 14. Phasenplan (einzig maßgeblich) + Akzeptanzkriterien

| Phase | Inhalt | **Done-Kriterien** |
|---|---|---|
| **P0** | Capability-Discovery, Schema-Builder, Reason-Enum, Resolver-Skelette (Feuchte/Luft als **No-op-Stubs**), transienter `ZoneDevice`-Read-Path — alles pur | Discovery pure getestet; **Reason-Enum stabil**; Schema-Builder tabellengetestet; Feuchte/Luft-Resolver no-op; **keine** HA-Servicecalls |
| **P1** | Thermal Shadow | Shadow zeigt aktive Quelle + Reason; **keine** zusätzlichen Aktorwrites; Feuchte/Luft weiter no-op |
| **P2** | Per-Device-Lifecycle | Lease, Min-Cycle, Health, Standby **persistieren Neustart** (Wall-Clock); pro Gerät |
| **P3** | Thermal Opt-in (+ Storage-Migration, + Add-Device-Subentry) | TRV+AC live; Failover; Single-Active; Boost; nicht-gewählte Geräte nach Standby-Policy; Migration verlustfrei |
| **P4** | Humidity Shadow | nur über **Taupunkt/absolute Feuchte/Oberflächenrisiko**; kein RH-only |
| **P5** | Humidity Opt-in | Entfeuchter/Befeuchter zuerst, AC-`dry` später; Kondensationsdeckel hart |
| **P6** | Air-Movement Shadow | Komfort-Kredit nur mit Präsenz/Freigabe; **kein** Free-Cooling über Umluft |
| **P7** | Air-Movement Opt-in | Coast-in-fan; Belegung/Override/Noise berücksichtigt |
| **P8** | Hub-Resource-Coordination (eigene Sub-ADR zuerst, §10) | Hub **blockiert gegensätzliche** Shared-Resource-Requests; Konfliktklassen §10 |

**Reihenfolge: zuerst thermische Mehrquellen-Arbitrierung vollständig**, dann Feuchte, dann Lüften, dann geteilte Ressourcen.

**Umsetzungsstand:** **P0** (pures `multi/`-Paket: model/reason/discovery/schema/resolvers + Tests) **und P1** (Thermal-Shadow **live** im Coordinator — `multi/shadow.py:evaluate_thermal_shadow` baut den transienten `ZoneDevice` aus dem Aktor und exponiert die Diagnose-Attribute `multi_active_source` / `multi_reason` / `multi_severity` / `multi_blocked`; **keine** Aktor-Writes, Feuchte/Luft weiter no-op) sind umgesetzt. Single-Active heute, der Seam ist live. Nächster Schritt **P2** (Per-Device-Lifecycle).

---

## 15. Testplan (Auszug, pure + Glue)

Quellenwahl über/unter `cop_balance_c`; ohne Metadaten deterministisch (kein Raten); Failover bei `unhealthy`; Boost mit Hysterese (kein Pumpen); **ein Gerät, zwei Achsen** (AC kühlen *und* entfeuchten → eine Capability, andere abgeben/zeit-multiplexen); Safety-Floor klemmt alle gewählten Geräte; **Manueller Eingriff** (`fan_only` → kein `off`-Nudge); **Kompressor-Min-Off** (Bedarf, aber `min_off` → kein Start, Reason); **Min-Off nach Neustart** (Wall-Clock-Restore hält Sperre, startet nicht sofort); Adapter-`dry`-nur-als-Preset (gültiger Servicepfad); **Free-Cooling nur bei echter Außenluftbewegung**; Außen kälter aber **absolut feuchter** → gesperrt; Befeuchter-Ziel über Kondensationsdeckel → gekappt; **geteilte Ressource gegensätzlich** → Hub blockt; Schema-Builder je Konstellation → korrekte Feldmenge; Migration Single→bleibt 3-Feld.

**Regressions-/Invarianz-Tests „No-op bleibt no-op":**
- **Single-TRV-Konfiguration** erzeugt **exakt dasselbe** Command-Verhalten wie vor ADR-0046.
- **P1-Shadow** erzeugt **keine** zusätzlichen Service-Calls.
- **Nicht verfügbare zweite Quelle** verändert den Single-Actor-Betrieb nicht.
- **Reason-Daten** ändern **nie** eine Steuerentscheidung (rein diagnostisch).
- **Adapter-Discovery-Fehler** degradiert auf sichere bekannte Capability oder `unavailable` — **nicht** auf Raten.
- Feuchte-/Luft-Resolver liefern in P0–P3 garantiert **leere Command-Mengen**.

---

## 16. Offene Fragen

- **Präsenzsignal** für den Luftbewegungs-Kredit: Poises EKF-Belegungsterm ist live nicht identifiziert → echtes Präsenz-Entity oder Nutzer-Toggle, Default konservativ (Kredit aus).
- **COP-Kurve vs. Einfachheit:** Balancepunkt bleibt Minimal; volle Kurve nur opt-in mit Daten.
- **Adapter-Abdeckung** realer IR-Klimas (Script/Remote) — Quirk-Katalog wächst über `model_fixes` (ADR-0029).
- **Hub-Arbitration-Algorithmus:** separate Sub-ADR vor P8 (§10).

---

## 17. Konsequenzen / Trade-offs

**Positiv:** Poise leistet echte Quellen-Arbitrierung (TRV ↔ heizfähige AC, Failover, Boost), **ohne** Komfortkern (ADR-0023) oder Solver (ADR-0035) umzubauen — die Arbitrierung ist eine additive, reine Schicht zwischen Entscheidung und Aktuierung. Single-Actor-Nutzer bleiben unberührt (3-Feld-Setup, identisches Verhalten). Diagnose („aktive Quelle"/Reason) ist ein Differenzierungsmerkmal, das beiden Wettbewerbern fehlt.

**Negativ:** deutlich mehr **Persistenzzustand pro Gerät** (Timer, Lease, Health, last command), mehr **Testaufwand** (Lifecycle, Adapter, Konflikte) und mehr **UI-Komplexität** (durch Progressive Disclosure kaschiert, aber vorhanden).

**Risiko:** **Adapter- und Quirk-Abdeckung** realer Geräte (IR-Klimas, Gree/Midea-Mode-Zahlen) wird langfristiger **Pflegeaufwand** — abgefedert über die `model_fixes`-Schicht und „degradiere sicher, rate nie".

**Bewusster Trade-off:** **Single-Active + bedarfsgetriebener Boost** statt echter proportionaler Mehrquellen-Mischung. Begründung gegenüber Alternativen: *Climate-Groups/paralleles Schreiben* (VTherm-Stil) kommandieren alle Geräte identisch und können Richtung/Kosten/Takt nicht arbitrieren; *proportionales Mischen* zweier laufender Verdichter/Quellen erhöht Takt-, Mess- und Modellkomplexität massiv ohne belegten Komfort-/Effizienzgewinn für den Wohnraum-Fall. Single-Active hält die Entscheidung erklärbar, testbar und geräteschonend.

---

## 18. Compliance & Verknüpfungen

**Compliance (G29/G30):** Methoden nachimplementiert, kein Code-Copy von Wettbewerbern; keine gerätespezifischen Sonderwege im Kern (Quirks isoliert in `model_fixes`, ADR-0029); norm-informiert, nicht norm-zertifizierend.
**Verknüpfungen:** erweitert ADR-0035 (Präzedenz) und ADR-0013/0038 (Hub); nutzt ADR-0042 (Override), ADR-0023 (Dual-Setpoint), ADR-0007 (Persistenz). Folge-Entscheidungen: separate Sub-ADR für die Hub-Arbitration (vor P8). Arbeits-Designdokumente (Projekt-Arbeitsstand, nicht im Repo): „Best-of Multi-Aktor" + Begleitdokument „Lüften/Trocknen/Feuchte".
