# Bewertung der 143 Climate-Attribute: funktionaler und diagnostischer Wert (2026-08-12)

**Frage:** Gibt es wirklich nutzlose Informationen in den `extra_state_attributes` der Poise-Climate-Entity?
**Methode:** Fünf parallele Code-Analysen über alle 143 Keys aus `climate.py:35-191` — (1) Datenquelle + Live/Shadow/Diagnostic-Status (presenter/tick_orchestrator/shadows + README/ADRs), (2) Card-Konsum (card/src, nicht das Bundle), (3) Entity-Duplikate (sensor/binary_sensor/switch + Diagnostics-Export), (4) Volatilität (Recorder-Kosten), (5) Doku-/Automationswert (README, ADRs, strings.json). Jede Zeile ist mit file:line-Belegen unterfüttert (Rohdaten: Workflow wf_4863c366).

## Kernantwort

**„Nutzlos" im absoluten Sinn ist fast nichts — falsch platziert ist sehr viel.** Jedes Attribut hat eine nachvollziehbare Entstehungsgeschichte (meist ADR-dokumentiert als bewusste Shadow-/Diagnose-Transparenz). Aber als **State-Attribute** — die bei jedem Tick mit in den Recorder geschrieben werden — bestehen nur 56 von 143 den Test „braucht das ein Konsument an genau dieser Stelle?" (23 KERN + 33 CARD). Der Rest:

- **10 Attribute sind als State-Attribute faktisch nutzlos** (STREICHEN): reine Interna ohne einen einzigen Konsumenten — kein Card-Read, kein Automationswert (`none`), keine oder nur ADR-interne Doku. Die Information selbst bleibt im Diagnostics-Export erhalten.
- **13 sind Duplikate** (DUP): der Wert existiert bereits als eigene Entity (Sensor/Switch), als identischer Zwilling (`heat_sp`==`comfort_low`, `cool_sp`==`comfort_high`) oder als natives HA-Attribut (`preset`==`preset_mode`).
- **64 sind echte Diagnose ohne Attribut-Zwang** (DIAG): wertvoll zum Verstehen/Debuggen, aber ohne Konsument auf der State-Fläche — gehören in den Diagnostics-Export bzw. (wo History nützt) in default-deaktivierte Sensoren.

**Recorder-Hebel:** 56 Attribute sind pro-Tick-volatil (jede Änderung invalidiert den geteilten Attribut-Blob des Recorders). Davon sind 36 DIAG/DUP/STREICHEN — d. h. **rund zwei Drittel der Volatilitätskosten stammen von Attributen ohne Konsumenten auf der State-Fläche** (v. a. die Shadow-Floats: `fr_*`, `mpc_*`-Werte, `pi_offset`, `tpi_duty`, `ref_offset*`, `savings_*`, `cover_predicted_peak`, `seasonless_rate`, Einheiten-Duplikate der Feuchteachse).

## Urteils-Legende

| Urteil | Bedeutung | Anzahl |
|---|---|---|
| **KERN** | Behalten: Live-/Automations-API ohne bessere Fläche oder Card-tragend + dokumentiert | 23 |
| **CARD** | Behalten wegen Card-Vertrag; bei einer Card-Migration (D.9 Variante b) → Sensor oder streichen | 33 |
| **DUP** | Redundant zu existierender Entity / identischem Zwilling — Attribut streichbar, die Entity ist die Fläche | 13 |
| **DIAG** | Information wertvoll, aber kein State-Attribut nötig → Diagnostics-Export / disabled-Sensor | 64 |
| **STREICHEN** | Als State-Attribut faktisch nutzlos (Interna ohne Konsument); Diagnostics-Export genügt | 10 |

Spalten: Status = live/shadow/diagnostic (speisender Pfad). Vol. = Änderungsrate (pro Tick / Event / statisch). Card = von der Poise-Card gelesen. Entity-Dup = existierende Duplikat-Entity. Auto = Automationswert (high/medium/low/none).

## Einzelbewertung aller 143 Attribute

### Kernzustand, Sensorik & Ingest

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `operative_temperature` | live | pro Tick | x | sensor | medium | **CARD** | Card-Hero (Dial-Mitte, Chart); Sensor default AN existiert - nach Card-Migration DUP |
| `t_rm` | live | statisch | - | sensor | medium | **DUP** | Sensor t_rm vorhanden; Saison-Condition ueber den Sensor |
| `t_rm_source` | diagnostic | statisch | - | - | low | **DIAG** | Herkunftslabel |
| `t_rm_internal` | diagnostic | statisch | - | - | none | **STREICHEN** | interner Schattenwert, kein Konsument |
| `source` | diagnostic | Event | - | - | low | **DIAG** | Degradationsleiter; Alarm laeuft ueber Repair-Issues |
| `q_solar` | live | pro Tick | - | sensor | medium | **DUP** | Sensor vorhanden |
| `q_solar_source` | diagnostic | statisch | - | - | low | **DIAG** | Herkunftslabel |
| `q_solar_internal` | diagnostic | pro Tick | - | - | none | **STREICHEN** | interner Parallel-Schaetzer, kein Konsument |
| `mrt` | live | pro Tick | - | sensor | low | **DUP** | Sensor vorhanden; operative_temperature ist die nutzbarere Groesse |
| `mrt_source` | diagnostic | statisch | - | - | low | **DIAG** | Herkunftslabel |
| `mrt_internal` | diagnostic | pro Tick | - | - | none | **STREICHEN** | virtueller Schattenwert, kein Konsument |
| `sensor_frozen` | live | Event | - | - | medium | **KERN** | Pause-Condition fuer abhaengige Automationen; speist auch Hub-Logik |
| `sensor_placement_suspect` | diagnostic | Event | - | - | low | **DIAG** | Repair-Issue sensor_at_heat_source deckt die Meldung |
| `dewpoint` | live | pro Tick | - | - | medium | **KERN** | Kondensations-/Lueftungs-API jenseits von Poise |

### Komfortband & Solver

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `comfort_low` | live | pro Tick | x | - | medium | **KERN** | Card-Hero + Discovery-Marker (getStubConfig); Band-API |
| `comfort_high` | live | pro Tick | x | - | medium | **KERN** | Card-Hero; Band-API |
| `heat_sp` | live | pro Tick | x | - | medium | **DUP** | identisch mit comfort_low (Publikation 3191/3194); Card-Buttons-Modus konsolidierbar |
| `cool_sp` | live | pro Tick | - | - | medium | **DUP** | identisch mit comfort_high |
| `category` | live | statisch | x | - | low | **CARD** | Kategorie-Label der Card; quasi-statisch, billig |
| `binding_lower_cause` | diagnostic | Event | x | - | low | **CARD** | Guard-Chip (mold/frost) |
| `mode` | live | Event | - | - | low | **DIAG** | hvac_mode/hvac_action der Entity decken Automationen; Card liest es nicht |
| `norm_binding` | diagnostic | Event | - | - | low | **DIAG** | Solver-Transparenz |
| `binding_precedence` | diagnostic | Event | - | - | low | **DIAG** | Solver-Transparenz |

### EKF / Modell

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `tau_hours` | live | pro Tick | - | sensor | low | **DUP** | Sensor vorhanden |
| `confidence` | diagnostic | pro Tick | x | sensor | low | **CARD** | Lern-Balken der Card; Sensor default AN |
| `learning_phase` | diagnostic | Event | - | sensor | low | **DUP** | ENUM-Sensor default AN |
| `identified` | live | Event | - | - | low | **DIAG** | learning_phase-Sensor (identified) deckt es |
| `identification_progress` | diagnostic | pro Tick | - | sensor | low | **DUP** | Sensor vorhanden |
| `beta_s` | live | pro Tick | - | sensor | low | **DUP** | Sensor vorhanden |
| `tau_confidence` | diagnostic | pro Tick | - | - | low | **DIAG** | Modell-Neugier |
| `tau_settled` | diagnostic | Event | - | - | low | **DIAG** | Modell-Neugier |
| `seasonless_phase` | diagnostic | Event | - | - | low | **DIAG** | Schaetzer-Phase, Neugier |
| `seasonless_rate` | diagnostic | pro Tick | - | - | low | **DIAG** | rekonstruierte Rate, chartbar ohne Automationsnutzen |

### Fenster

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `window_open` | live | Event | x | - | high | **KERN** | Automations-Trigger (high); EINZIGE Flaeche - kein binary_sensor! D-Kandidat: Entity spendieren |
| `window_auto_detected` | live | Event | x | - | medium | **CARD** | Chip-Label-Variante; Trigger fuer sensorlose Zonen |
| `window_auto_slope` | diagnostic | pro Tick | - | - | none | **STREICHEN** | Detektor-Interna (roher EWMA-Slope) |
| `window_auto_threshold` | live | pro Tick | - | - | none | **STREICHEN** | Detektor-Interna (Schwelle), nirgends dokumentiert |
| `window_bypass` | live | Event | x | switch | low | **DUP** | Switch-Entity ist Flaeche UND Schreibpfad |

### Zeitplan / Optimal-Start/-Stop

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `schedule_state` | live | Event | - | - | medium | **KERN** | comfort/setback-Condition zum Koppeln anderer Automationen |
| `minutes_to_comfort` | live | pro Tick | x | - | medium | **CARD** | Chip-Minuten; Power-User-Trigger |
| `preheating` | live | Event | x | - | medium | **CARD** | Vorheiz-Chip; Trigger (Pumpe/Fussboden vorbereiten) |
| `preheat_outdoor` | live | pro Tick | - | - | low | **DIAG** | Nachvollzieh-Diagnose des Preheat-Plans |
| `coasting` | live | Event | x | - | medium | **CARD** | Coasting-Chip; Trigger analog preheating |
| `minutes_to_setback` | live | pro Tick | x | - | medium | **CARD** | Chip-Minuten; Trigger Komfort-endet-gleich |

### Safety & Geraete-Beobachtung

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `heating_failure` | diagnostic | Event | x | - | high | **KERN** | Alarm-Trigger (high) + Card-Chip |
| `device_alarm` | diagnostic | Event | - | - | medium | **KERN** | Geraetefehler-Alarm zusaetzlich zum Repair-Issue |
| `device_schedule_active` | diagnostic | Event | - | - | low | **DIAG** | Repair-Issue traegt die Nutzer-Kommunikation |
| `trv_input_mode` | live | statisch | - | - | low | **DIAG** | Feed-Pfad-Diagnose |
| `valve_health` | diagnostic | Event | - | - | medium | **KERN** | stuck/ok-Bewertung fuer Geraetefehler-Automation; Doku-Luecke schliessen |
| `valve_closing_steps` | diagnostic | statisch | - | - | none | **STREICHEN** | roher Geraetezaehler; valve_stuck-Repair interpretiert ihn bereits |
| `valve_idle_steps` | diagnostic | statisch | - | - | none | **STREICHEN** | roher Geraetezaehler |
| `tick_over_budget` | diagnostic | Event | - | - | low | **DIAG** | Sensor tick_duration_ms ist die Monitoring-Flaeche |

### Regel-Shadows (TPI/PI/MPC)

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `tpi_active` | shadow | statisch | x | - | low | **CARD** | Shadow-Pill-Gate (Vorrang) |
| `tpi_duty` | shadow | pro Tick | - | - | low | **DIAG** | speist heat_demand intern; per-Tick-Float |
| `tpi_valve_percent` | shadow | pro Tick | x | - | low | **CARD** | Shadow-Pill-Prozentzahl |
| `pi_active` | shadow | statisch | x | - | low | **CARD** | Shadow-Pill-Gate |
| `pi_setpoint` | shadow | pro Tick | x | - | low | **CARD** | Shadow-Pill-Gradzahl |
| `pi_offset` | shadow | pro Tick | - | - | low | **DIAG** | Shadow-Interna |
| `mpc_active` | shadow | Event | x | - | low | **CARD** | Shadow-Pill-Gate |
| `mpc_power` | shadow | pro Tick | - | sensor | low | **DUP** | Sensor vorhanden |
| `mpc_weight` | shadow | pro Tick | - | sensor | low | **DUP** | Sensor vorhanden |
| `mpc_setpoint` | shadow | pro Tick | x | - | low | **CARD** | Shadow-Pill-Gradzahl |
| `mpc_regime` | shadow | Event | - | - | low | **DIAG** | Regime-Label |

### Free-Running / Fan / Ref-Offset / Cover

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `fr_active` | shadow | Event | - | - | low | **DIAG** | Shadow-Transparenz |
| `fr_heat_sp` | shadow | pro Tick | - | - | low | **DIAG** | Shadow-Bandkante (per-Tick-Float) |
| `fr_cool_sp` | shadow | pro Tick | - | - | low | **DIAG** | Shadow-Bandkante (per-Tick-Float) |
| `fr_adaptive_lower` | shadow | statisch | - | - | low | **DIAG** | Shadow-EN-Band |
| `fr_adaptive_upper` | shadow | statisch | - | - | low | **DIAG** | Shadow-EN-Band |
| `fan_circ_shadow` | shadow | Event | - | - | low | **DIAG** | Preview-Empfehlung |
| `fan_circ_reason` | shadow | Event | - | - | low | **DIAG** | Begruendung |
| `fan_ce_k` | shadow | Event | - | - | low | **DIAG** | Shadow-Kredit bis Tier-2 |
| `fan_cool_sp_shadow` | shadow | pro Tick | - | - | low | **DIAG** | Shadow-Kante |
| `fan_velocity_ms` | shadow | Event | - | - | low | **DIAG** | PMV-Input-Transparenz |
| `ref_offset` | shadow | pro Tick | - | - | low | **DIAG** | Kalibrier-Transparenz (Shadow) |
| `ref_offset_dev` | shadow | pro Tick | - | - | none | **STREICHEN** | EWMA-Interna des Schaetzers |
| `ref_offset_trusted` | shadow | Event | - | - | low | **DIAG** | Vertrauens-Flag |
| `ref_offset_conditioning` | shadow | Event | - | - | none | **STREICHEN** | Feed-Gate-Interna |
| `cool_sp_compensated` | shadow | pro Tick | - | - | low | **DIAG** | Shadow-Kante |
| `cover_predicted_peak` | shadow | pro Tick | - | - | low | **DIAG** | per-Tick-Shadow-Float |
| `cover_would_shade` | shadow | Event | - | - | medium | **KERN** | Automations-API bis Cover-Aktuierung live (ADR-0043-Stufenmuster) |
| `cover_shade_position` | shadow | Event | - | - | medium | **KERN** | direkte Vorlage fuer eigene cover-Automation |
| `cover_shade_reason` | shadow | Event | - | - | low | **DIAG** | Begruendungs-String |

### Adaptive Kuehlkante (ADR-0051/0061)

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `adaptive_cool` | live | statisch | - | - | low | **DIAG** | Config-Echo |
| `adaptive_cool_mode` | live | statisch | - | - | low | **DIAG** | Config-Echo; mit adaptive_cool konsolidierbar |
| `cool_sp_eff` | live | pro Tick | - | - | low | **DIAG** | laut ADR-0051 bereits in cool_sp enthalten - redundant |
| `cool_sp_active` | live | pro Tick | - | - | low | **DIAG** | Anzeige der wirksamen Kante |
| `cool_raised` | live | Event | - | - | low | **DIAG** | Flag der Hitzetag-Anhebung |
| `cool_raise_reason` | live | Event | - | - | low | **DIAG** | Begruendungs-String |
| `en_cool_upper` | live | statisch | - | - | low | **DIAG** | Norm-Transparenz |

### Feuchte, Schimmel & Lueftung

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `humidity_action` | live | Event | - | - | low | **DIAG** | dry_active ist der nutzbarere Latch |
| `dry_active` | live | Event | - | - | medium | **KERN** | Entfeuchtungs-Condition/Trigger (eigene Luefter-/Fensterlogik) |
| `humidity_reason` | live | Event | - | - | low | **DIAG** | Begruendungs-String |
| `abs_humidity_gkg` | live | pro Tick | - | - | low | **DIAG** | Einheiten-Duplikat zu abs_humidity_gm3 - konsolidierbar |
| `rh_high_used` | live | statisch | - | - | low | **DIAG** | verwendete RH-Decke, Transparenz |
| `abs_humidity_gm3` | diagnostic | pro Tick | x | - | medium | **KERN** | prominenteste dokumentierte Feuchte-API (README, Card-Ampel) |
| `abs_humidity_out_gm3` | diagnostic | pro Tick | - | - | low | **DIAG** | Innen/Aussen-Entscheid steckt fertig in vent_action |
| `surface_rh` | diagnostic | pro Tick | - | - | medium | **KERN** | Schimmel-Fruehwarn-Condition (z.B. ueber 75% melden) |
| `surface_rh_mean` | diagnostic | pro Tick | - | - | low | **DIAG** | geglaetteter Advice-Input |
| `mold_capped` | diagnostic | Event | - | - | low | **DIAG** | vent_level=alert eskaliert bereits |
| `rh_max_safe` | diagnostic | pro Tick | - | - | medium | **KERN** | dokumentierte Befeuchter-Deckel-API (README) |
| `abs_max_safe` | diagnostic | pro Tick | - | - | medium | **DIAG** | Einheiten-Duplikat zu rh_max_safe |
| `fabric_conflict` | diagnostic | Event | - | - | low | **DIAG** | Hinweis-Flag |
| `mould_floor` | live | pro Tick | x | - | low | **CARD** | oranger Dial-Tick (ADR-0062: display-only) |
| `vent_action` | diagnostic | Event | x | sensor | high | **KERN** | Lueftungs-Trigger (high); Sensor + Bus-Event flankieren |
| `vent_reason` | diagnostic | Event | x | - | low | **CARD** | Chip-Begruendung (i18n) |
| `vent_level` | diagnostic | Event | x | - | medium | **CARD** | Alert-Stil des Chips; Eskalations-Filter |
| `vent_delta_gm3` | diagnostic | pro Tick | - | - | low | **DIAG** | Delta-Anzeige |

### Kompressor-Guard

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `mode_nudge_blocked` | live | Event | x | sensor | low | **CARD** | Compressor-Guard-Chip; gemappter Sensor existiert |
| `compressor_gate_would_block` | live | Event | - | - | low | **DIAG** | Guard-Transparenz |
| `compressor_mode_hold_remaining` | live | Event | - | - | low | **DIAG** | Restzeit-Anzeige |

### PMV & Komfort-Aktivierung

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `pmv` | shadow | pro Tick | x | - | medium | **KERN** | README deklariert das Attribut explizit als API (kein Sensor - Attribut lesen) |
| `ppd` | shadow | pro Tick | x | - | medium | **KERN** | dokumentierte Komfort-API; Card-Ampel |
| `pmv_category` | shadow | Event | - | - | low | **DIAG** | Kategorien-Label |
| `clo_used` | shadow | statisch | - | - | low | **DIAG** | Feld-Plausibilisierung |
| `clo_source` | shadow | statisch | - | - | low | **DIAG** | Herkunftslabel |
| `met_used` | shadow | statisch | - | - | low | **DIAG** | Profil-Echo |
| `pmv_valid` | shadow | Event | x | - | medium | **KERN** | Pflicht-Gate jeder pmv/ppd-Automation; Card gated darauf |
| `clo_offset` | shadow | statisch | - | - | low | **DIAG** | Lern-/Config-Echo (ADR-0067) |
| `active_comfort` | live | statisch | x | - | low | **CARD** | Gate der Massnahmen-Pill; Config-Echo |
| `fan_first_phase` | live | Event | x | - | low | **CARD** | Massnahmen-Pill (Ventilator-Phase) |
| `tier2_fan_ce` | diagnostic | Event | x | - | low | **CARD** | Reift-Hinweis der Pill; Latch-Interna |
| `tier2_pmv_offset` | diagnostic | Event | x | - | low | **CARD** | Reift-Hinweis der Pill; Latch-Interna |
| `fan_ce_credit_k` | live | Event | x | - | low | **CARD** | angewandter Kredit in der Pill |
| `pmv_offset_k` | live | Event | x | - | low | **CARD** | angewandte Verschiebung in der Pill |
| `ca_deviation_k` | diagnostic | pro Tick | x | sensor | low | **CARD** | Regelguete-Ampel; Sensor existiert (LTS) |
| `ca_time_in_band` | diagnostic | pro Tick | x | sensor | low | **CARD** | Regelguete-Ampel (Prozent-Anzeige); Sensor existiert |
| `ca_cycles_per_h` | diagnostic | pro Tick | x | sensor | low | **CARD** | Regelguete-Ampel; Sensor existiert |
| `ca_minutes` | diagnostic | pro Tick | - | - | none | **STREICHEN** | Stichprobengroesse, reine Interna |

### Override / Preset

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `override_active` | live | Event | x | - | high | **KERN** | Hold-Condition (high); Gate der ganzen Hold-Pill |
| `override_reason` | live | Event | x | - | medium | **KERN** | Herkunft (ui/device/frost) fuer differenzierte Automationen; Pill |
| `override_expires_at` | live | Event | x | sensor (BUG) | medium | **KERN** | Zeit-Trigger + Card-Countdown; ACHTUNG: der duplizierte Sensor ist verbuggt (immer unknown) |
| `override_clamped` | diagnostic | Event | x | - | medium | **CARD** | Clamp-Chip; Benachrichtigungs-Automation moeglich |
| `override_requested` | diagnostic | Event | x | - | low | **CARD** | Pre-Clamp-Wunsch im Clamp-Chip |
| `override_policy` | live | statisch | x | - | low | **CARD** | Config-Echo fuer die Pill |
| `mode_override` | live | Event | x | - | low | **CARD** | Mode-Hold-Wort der Pill |
| `boost_expires_at` | live | Event | x | - | low | **CARD** | Boost-Countdown |
| `preset` | live | Event | x | - | low | **DUP** | dupliziert das native preset_mode der Entity |
| `mode_adopt_reason` | diagnostic | Event | - | - | low | **DIAG** | observe-only Debug (README) |
| `sp_adopt_reason` | diagnostic | Event | - | - | low | **DIAG** | observe-only Debug |

### Savings & Multi-Zone

| Attribut | Status | Vol. | Card | Entity-Dup | Auto | Urteil | Begruendung |
|---|---|---|---|---|---|---|---|
| `savings_kwh_month` | diagnostic | pro Tick | - | - | low | **DIAG** | Reporting -> Sensor-Kandidat (LTS statt Attribut-History) |
| `savings_eur_month` | diagnostic | pro Tick | - | - | low | **DIAG** | wie savings_kwh_month |
| `savings_pct` | diagnostic | pro Tick | - | - | low | **DIAG** | wie savings_kwh_month |
| `heat_demand` | diagnostic | pro Tick | - | - | medium | **KERN** | dokumentierte hub-lose Kessel-API (README:42) |

## Befunde jenseits der Einzelbewertung

1. **Bug: der `override_expires_at`-Sensor ist im realen Betrieb immer `unknown`.** Das Attribut publiziert einen ISO-8601-String (`tick_orchestrator.py:3232` via `iso_utc`), die Sensor-`value_fn` akzeptiert aber nur Epoch-Zahlen (`sensor.py:56-67`, `:256-262`). Der Test maskiert das, indem er den Epoch direkt in `coord.data` injiziert (`test_entity_defaults.py:148-158`) — dieselbe Mock-maskiert-Bug-Klasse wie beim `target_temp_step`-Falsch-Key. Pikant: Der Sensor ist default-aktiviert und im README (Z. 222) als user-facing beworben. → Separater Fix (Task-Chip erstellt).
2. **Lücke: `window_open` hat keine Entity.** Der wertvollste Automations-Trigger der Integration (effektives Fenstersignal inkl. sensorloser Erkennung) existiert *nur* als Attribut und ist nirgends dokumentiert. D-Kandidat: `binary_sensor` spendieren + dokumentieren.
3. **Identische Zwillinge:** `heat_sp`/`comfort_low` und `cool_sp`/`comfort_high` publizieren denselben Wert unter zwei Namen (`tick_orchestrator.py:3191-3195`); die Card liest beide Namen an verschiedenen Stellen. Konsolidierbar ohne Funktionsverlust (Card-Anpassung nötig).
4. **Einheiten-Duplikate der Feuchteachse:** `abs_humidity_gkg` vs. `abs_humidity_gm3` und `rh_max_safe` vs. `abs_max_safe` tragen dieselbe Information in zwei Einheiten; je eine dokumentierte Fläche genügt.
5. **`preset` dupliziert das native `preset_mode`** der Climate-Entity (HA-Standardattribut) — die Card nutzt es nur als Fallback-Chip.
6. **Keine Recorder-Ausnahme:** Es gibt weiterhin kein `_unrecorded_attributes` — jede der 143 Spalten landet in der Recorder-History. Unabhängig von der D.9-Entscheidung wäre das der billigste Sofort-Hebel: die DIAG/STREICHEN-Menge als unrecorded zu deklarieren, ohne die Live-State-Fläche zu ändern (HA unterstützt das seit langem; die Card liest den Live-State, nicht die History — einzige Ausnahme: die drei History-Keys `operative_temperature`/`current_temperature`/`temperature`, die alle KERN/CARD sind).

## Konsequenz für D.9

Die Zahlen stützen einen **Mittelweg zwischen Variante (a) und (b)**:

- **Sofort (ohne Card-Umbau):** STREICHEN-Menge (10) entfernen, DUP-Menge (13) entfernen (Card-Reads auf die 4 betroffenen Zwillinge umstellen: `heat_sp`→`comfort_low` etc.), DIAG-Menge (64) per `_unrecorded_attributes` von der Recorder-History ausnehmen oder direkt in den Diagnostics-Export verlagern. Ergebnis: State-Fläche 143 → ~89 sichtbare Attribute, Recorder-Volatilität −36 von 56 per-Tick-Quellen — ohne dass Card oder dokumentierte APIs brechen.
- **Mit Card-Migration (Variante b):** zusätzlich die 33 CARD-Attribute auf Sensoren/eigene Datenquelle umziehen → Endzustand ~23 KERN-Attribute, wie es das externe Review empfahl.

Die 23 KERN-Attribute sind zugleich die Kandidatenliste für die im Plan (F) angedachten fachlichen Trigger/Conditions und für die offenen Quality-Scale-Doku-Punkte (`docs-examples`): `window_open`, `override_active`, `heating_failure`, `vent_action` (alle auto=high) plus die medium-Klasse (`dry_active`, `schedule_state`, `surface_rh`, `dewpoint`, `heat_demand`, …).

---

## Nachtrag (gleicher Tag): Shadow-Validierung — brauchen die Flips die Attribut-Aufzeichnung?

**Frage:** Werden zur Aktivierung der Shadow-Funktionen Diagnoseaufzeichnungen benötigt, die danach in den Attributen unnötig werden?
**Methode:** Sweep über alle 72 ADRs (ausstehende Validierungen, benannte Beobachtungsgrößen, Aufzeichnungsort, Verbleib nach Flip) + unabhängige Analyse des Aufzeichnungs-Subsystems (trace/, diagnostics/, tests/harness/). Rohdaten: Workflow wf_c76ad405.

### Ausstehende Validierungen mit klaren Kriterien

| Feature (ADR) | Flip-Kriterium | Benötigte Beobachtung | Kanal heute |
|---|---|---|---|
| MPC Stufe 2 (0001/0009/0033) | Kalte Saison: (a) `mpc_weight` stabil hoch bei `identified`, (b) `mpc_setpoint` weicht plausibel/vorteilhaft vom statischen Sollwert ab, (c) keine Pendel-Tendenz über Tage | mpc_weight-Verlauf, mpc_setpoint-vs-Ist-Zeitreihe, Modellreife | mpc_power/mpc_weight: **LTS-Sensoren** ✓; `mpc_setpoint`: **nur 10-Tage-Attribut-History** ✗; Modellreife: Trace ✓ |
| TPI-Direktventil (0004/0036) | Kalte Saison analog MPC + Force-Open/`smart_temperature_control` am echten Gerät verifizieren | tpi_duty-Plausibilität (Anker: ~0,65 bei 8 °C/21 °C) | `tpi_duty`/`tpi_valve_percent`: **nur Attribut-History** ✗ |
| PI Stufe 2 (0037) | „Evidenz-gegated"; echtes setpoint-only-Gerät fehlt; Droop-Reduktion nachweisen | pi_setpoint/pi_offset-Verlauf | **nur Attribut-History** ✗ (Caveat 0037: Shadow-Integrator misst heute den Kreis des External-Feed-Pfads) |
| CA-Flip-Gate selbst (0055) | Schwellen-Feldkalibrierung über Sommer→Winter, erst dann bekommt die Metrik Flip-Autorität | ca_*-Verteilungen über Monate | **LTS-Sensoren — explizit dafür gebaut** (sensor.py:185-188: Attribut-History „~10 Tage" reicht nicht) ✓ |
| Ref-Offset live (0056) | Feld-Verifikation Trust-Gate am Büro-AC (Warm-up ≥30 min Konditionierung, Stabilität), dann gated auf 0055 + Opt-in | ref_offset/ref_offset_dev-Stabilität | **nur Attribut-History** ✗ (Momentwert persistiert) |
| tau-settle als Preheat-Klemme (0024) | `rel_gate` offline gegen echte α-Trajektorien nachkalibrieren | α-/τ-Trajektorien | **Feld-Traces — vorgesehener Kanal** ✓ |
| β_c-Kühl-Identifikation (0024) | Sommerfenster mit echter Kühl-Anregung (Gate kippt datengetrieben) | n_cooling/cooling_identified | **Trace + Persistenz** — gar nicht als Attribut exponiert ✓ |
| Free-Running-Widening (0023) | Diagnose soll Hitzetag-Fehlverhalten zeigen; Flip evtl. NIE (Schreibpfad behält Auslegungsbänder) | fr_*-Verhalten qualitativ | nur Attribut ✗ |
| Cover-Shading (0043) | Shadow-first, im Sommer live verifizierbar; keine Metrik benannt | cover_*-Plausibilität | nur Attribut ✗ |
| Hub S3/S4 + Flow (0013/0038/0039) | Flow-Allokator: Harness-Validierung ERFÜLLT; Enforcement braucht Shed-Cap-Präzedenz unterhalb Frost | Hub-Attribute | Attribut (Hub-Entity) |
| Tier-2 fan_ce/pmv_offset (0054/0068/0069) | **Automatisches Laufzeit-Gate:** identified ∧ CA-Reife ∧ PPD-Baseline (3 Tage) ∧ 24-h-Dwell ∧ Nicht-Verschlechterung ≤+1 pp, Schmitt-Exit +2 pp | Gate liest **persistierten Store** (regq/comfort_activation), nicht die Recorder-History | unabhängig von Attributen ✓ |
| Dynamik-Profile §6 / Zonen-Staffelung §5 (0052/0020) | Harness-(Re-)Validierung | Harness | n/a |

### Kernantwort in drei Teilen

1. **Die Architektur benutzt die Attribut-History gar nicht als Validierungskanal.** Vorgesehen sind LTS-Sensoren (Langzeit-Verteilungen für Flip-Evidenz — im Code wörtlich begründet, sensor.py:185-188) und der Trace (deterministisches Offline-Replay, trace_replay.py). Kein Codepfad liest die Recorder-History (kein recorder-Import, Grep: 0 Treffer); die Tier-2-Gates konsumieren ihre Evidenz zur Laufzeit aus dem persistierten Store. Die Attribute sind Live-Sichtfenster (Card), keine Aufzeichnung.
2. **Aber es gibt eine echte Lücke:** Vier Flip-Validierungen (MPC-Kriterium b, TPI-Duty, PI-Droop, Ref-Offset-Stabilität) brauchen **Shadow-Output-Zeitreihen, die es nirgends sonst gibt** — der Trace zeichnet keine Shadow-Outputs auf (kein mpc_*/tpi_*/pi_*-Feld im TraceRecord), und LTS-Sensoren existieren nur für mpc_power/mpc_weight. Diese Werte leben ausschließlich in der ~10-Tage-Attribut-History, die für Kaltsaison-Horizonte nicht reicht. **Nicht die Attribute sind die benötigte Aufzeichnung — die benötigte Aufzeichnung fehlt teilweise.**
3. **Ja, nach dem jeweiligen Flip werden die Would-be-Attribute obsolet:** `mpc_setpoint`/`mpc_regime` (werden Live-Größen), `tpi_duty`/`tpi_valve_percent` (werden Ist-Kommando), `pi_setpoint`/`pi_offset`, `cool_sp_compensated` (wird geschriebene Kante), `cover_would_shade`/`cover_shade_position` (Cover-Entity zeigt dann Ist), `fr_*` (falls je geflippt). **Dauerhaft bleiben laut ADRs:** `mpc_weight` (wird Live-Überblendgewicht der 0009-Mechanik), die ca_*-Metrik (permanentes KPI + Gate — als Sensoren), die Tier-2-Latches (Dauer-Wächter mit Schmitt-Exit), der ADR-0046-Reason-Vertrag und die PMV-Bewertung (wird nie Regelgröße, bleibt Überwachung).

### Konsequenz für Phase D (präzisiert)

Die Attribut-Diät kollidiert nicht mit den Flip-Validierungen, **wenn vorher die Lücke aus Punkt 2 geschlossen wird**: entweder ~4 default-deaktivierte LTS-Sensoren ergänzen (`mpc_setpoint`, `tpi_duty`, `pi_offset` bzw. `pi_setpoint`, `ref_offset` — ggf. + `ref_offset_dev`) **oder** das Trace-Schema um die Shadow-Outputs erweitern (dazu passt der offene ADR-0011-Punkt „Eval-/Scoring-Schicht als Folge-Increment"). Danach gilt: Die DIAG-/STREICHEN-Urteile der Haupttabelle bleiben gültig — die Would-be-Attribute sind Beobachtungsfenster auf Zeit, deren Aufzeichnungsbedarf auf die dafür gebauten Kanäle gehört, und nach dem jeweiligen Flip ersatzlos streichbar. Einzige Urteils-Präzisierung: `ref_offset_dev` (STREICHEN) trägt den Stabilitätsnachweis der 0056-Feldverifikation — vor dem Streichen in Sensor/Trace überführen.
