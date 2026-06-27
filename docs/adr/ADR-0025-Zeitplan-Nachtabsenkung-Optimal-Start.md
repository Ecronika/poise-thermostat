# ADR-0025: Komfort-Zeitplan, Nachtabsenkung & Optimal-Start

**Status:** Implementiert · **Datum:** 2026-06-19 · **Bezug:** ADR-0002/0009/0024 (EKF), ADR-0003 (Optimal-Stop), ADR-0023 (Dual-Setpoint) · **Verifizierung:** eigene EKF-Physik (`thermal_ekf.py`), Norm EN 16798-1; Wettbewerber-Optimal-Start **gegen realen Code verifiziert** (RoomMind/ThermoSmart/Versatile/Better Thermostat/Adaptive Climate/Vesta + eigenes ha-preheat, s. u.)

## Kontext
Nach dem Hardware-Limit der Aqara-E1-TRVs (keine Ventilposition → keine Duty-Modulation; ADR-Notiz Livetest v0.7.1) bleibt der wirksamste Komforthebel die **zeitliche** Steuerung: Nachtabsenkung (Energie sparen, wenn niemand Komfort braucht) und **Optimal-Start** (rechtzeitig vorheizen, damit der Raum *zur gewünschten Zeit* warm ist, statt zu einer festen Uhrzeit erst loszuheizen). Beides fehlte Poise; der EKF liefert seit ADR-0024 eine ehrliche Aufheizphysik, die genau das ermöglicht.

## Entscheidungstreiber
Der Zeitplan muss optional und rückwärtskompatibel sein (kein Plan = ganztags Komfort). Optimal-Start darf nur mit einem **identifizierten** Modell rechnen (sonst falsche Vorlaufzeiten) und muss **rein beratend** bleiben — kein zweiter Schreiber auf die Aktorik (Re-Entry-Bugklasse K5, vgl. ADR-0003).

## Entscheidung
1. **Pure Zeitplan-Schicht** `comfort/schedule.py`: tägliche Komfortfenster `[start, end)`; außerhalb = Setback. `state_at(minute)` liefert `is_comfort`, `minutes_to_comfort` (Vorlauf-Deadline) und `setback_offset` (−`setback_delta` K). Normalisierung (Clamp auf einen Tag, Verschmelzen, Sortieren) + `parse_hhmm` für die Config.
2. **Nachtabsenkung** über `setback_offset`: im Setback wird die effektive `comfort_base` um `setback_delta` (Default 3 K) gesenkt; die Dual-Setpoint-Logik (ADR-0023) regelt darauf — Frost-/Schimmel-Floor bleiben hart.
3. **Optimal-Start** `control/optimal_start.py`: invertiert die gelernte ZOH-Physik analytisch. Mit `t_eq = t_out + drive/α` und Zeitkonstante `1/α` ist die Aufheizzeit `t = −(1/α)·ln((T*−t_eq)/(T0−t_eq))`. Liegt `t_eq` nicht über dem Ziel → **unerreichbar** (Heizleistung reicht nicht) → Best-Effort (so früh wie der Horizont erlaubt). `advise(...)` meldet `start_now`, sobald die Komfort-Deadline innerhalb der Vorlaufzeit liegt.
4. **Verdrahtung (Coordinator):** im Setback wird, *nur* wenn `optimal_start` aktiv ∧ Gerät heizen kann ∧ `ekf.identified`, der Vorlauf berechnet; bei `start_now` wird die Absenkung aufgehoben (`base = comfort_base`) und damit regulär vorgeheizt. Optimal-Start kommandiert nichts selbst — es verschiebt nur den Sollwert-Fahrplan.
5. **Config:** optionale `comfort_start`/`comfort_end` (TimeSelector), `setback_delta` (0–8 K), `optimal_start` (Bool, Default an). Fehlen die Zeiten oder `delta=0` → `always_comfort` (kein Setback, kein Vorheizen).
6. **Diagnose:** Attribute `schedule_state` (comfort/setback), `minutes_to_comfort`, `preheating`.

## Begründung
Die Aufheiz-Schätzung nutzt **dasselbe** code-verifizierte EKF-Modell wie der MPC (keine Doppelmodellierung, keine Heuristik-Konstanten). Das Gate auf `identified` (ADR-0024) verhindert, dass unter geringer Anregung mit falschem α vorgeheizt wird — im Sommer/warmen Raum bleibt Optimal-Start daher inaktiv und schaltet sich erst mit echten kalten Heizzyklen scharf. Die Setback-Absenkung respektiert die harten Floors aus ADR-0023, sodass Schimmel-/Frostschutz nie der Energieersparnis geopfert wird.

## Konsequenzen
**Positiv:** Nachtabsenkung + bedarfsgerechtes Vorheizen ohne Ventil-Hardware; Optimal-Start ist physikbasiert statt heuristisch und sicher gegated; rein beratend → keine Re-Entry-Gefahr. **Negativ/Offen:** (a) Zeitplan vorerst ein Komfortfenster pro Tag (kein Wochentag-Profil, kein Multi-Fenster — bewusst minimal, erweiterbar über `from_windows`). (b) **Wettbewerber-Optimal-Start ist noch nicht gegen realen Code re-verifiziert** (ThermoSmart/RoomMind-Klasse); die Entscheidung stützt sich hier auf die eigene, verifizierbare EKF-Physik und die Norm. Re-Verifizierung als Folgeschritt vor dem Live-Scharfschalten in der kalten Saison. (c) Optimal-Start liefert erst nach EKF-Identifikation echte Vorlaufzeiten.

## Nachgelagerte Verifizierung gegen realen Code (2026-06-19)
Der in „Konsequenzen (b)" offen gelassene Punkt ist nun erledigt. Geprüft wurde der **reale Quellcode** der Wettbewerber (nicht Doku):

- **RoomMind** (`snazzybean/roommind`, `control/mpc_controller.py`/`mpc_optimizer.py`/`utils/schedule_utils.py`): Optimal-Start **implizit über MPC**. `make_target_resolver`/`resolve_targets_at_time` liefern eine **Ziel-Zeitreihe** aus den Schedule-Blöcken; der Controller baut „dual target series with schedule lookahead for **pre-heating/pre-cooling**" und der Optimizer plant on/off über einen Horizont, der **adaptiv aus der geschätzten Aufheizzeit** dimensioniert wird (`_compute_horizon_blocks`: `est_minutes × HORIZON_MULTIPLIER`, min 2 h). Outdoor-/Solar-/Residual-**Zeitreihen** fließen ein → veränderliche Außentemperatur über den Horizont. Stärkste Lösung.
- **ThermoSmart** (`Mikasmarthome/ThermoSmart`, `learning_engine.py`/`coordinator.py`): Optimal-Start **explizit, aber linear**. `async_get_preheat_minutes`: `minutes = min(Δ / effective_rate, PREHEAT_MAX_MINUTES=180)`, `effective_rate = heat_rate − cool_rate` (Boden `0.3×rate`), Auslöseschwelle `PREHEAT_MIN_DELTA = 2.0 K`. Trigger im Coordinator: `0 < mins_until_comfort ≤ preheat_minutes ∧ base_target < comfort` → `base_target = comfort`. **Architektonisch identisch zu Poise**, jedoch lineare Aufheizrate statt Exponential-Inversion.
- **Versatile Thermostat** (`jmcollin78/versatile_thermostat`, `auto_start_stop_algorithm.py`): **kein** termingebundenes Vorheizen. `should_be_turned_off` extrapoliert linear über die Steigung (`temp_at_dt = current + slope_min·dt`) → reaktiver Auto-Start/Stop-Energiesparer, keine Schedule-Deadline.
- **Better Thermostat** (`KartoffelToby/better_thermostat`): **kein** Optimal-Start (reine TRV-Kalibrierung/-Übersetzung).
- **Adaptive Climate** (`msinhore/adaptive-climate-blueprint`): **kein** Optimal-Start (ASHRAE-55-Adaptivkomfort-Blueprints).
- **Vesta** (`portbusy/ha-vesta`): **kein** Optimal-Start (einzelne `climate.py`).
- **Eigenes ha-preheat** (`Ecronika/ha-preheat`, `math_preheat.py`): Vorheizzeit per **numerischem Root-Finding über eine wetterprognose-integrierte** Bedarf/Angebot-Kurve (`resample_curve`/`integrate_forecast`, 5-min-Schritte); Coast/Optimal-Stop dagegen geschlossen-exponentiell `t = −τ·ln((T_floor−T_out)/(T_start−T_out))`. **Forecast-bewusst** über das Fenster.

### Bewertung von Poise ADR-0025
Poise liegt mit der **geschlossenen Exponential-Inversion** (`t = −ln((T*−t_eq)/(T0−t_eq))/α`, `t_eq = t_out + drive/α`) **physikalisch vor ThermoSmart** (linear `Δ/rate` über- bzw. unterschätzt nahe der Asymptote) und behandelt **Unerreichbarkeit** sauber (`t_eq ≤ Ziel`), was die lineare Variante nicht kennt. Das `identified`-Gate (ADR-0024) ist die strengste Reifeprüfung im Feld. Architektur (Schedule-Deadline → `start_now`-Vergleich, Setback-Aufhebung) deckt sich exakt mit ThermoSmart und dem MPC-Lookahead von RoomMind.

**Eine bestätigte Lücke:** Poise rechnet mit **konstanter aktueller Außentemperatur**. Die beiden stärksten Referenzen — RoomMind (Outdoor-Zeitreihe) **und das eigene ha-preheat** (Forecast-Integration) — nutzen die **Außentemperatur-Prognose über das Vorheizfenster**. Bei langen Vorläufen in veränderlichem Wetter (z. B. Morgendämmerung) ist Konstant-Außen ungenauer. → Folge-Kandidat: optionaler `weather`-Forecast als `t_out`-Reihe (mittlere prognostizierte Außentemperatur über `minutes_to_comfort`) in `heatup_minutes`. Erst nach EKF-Identifikation in der kalten Saison relevant.

**Fazit:** Der Optimal-Start-Ansatz von Poise ist code-verifiziert solide und auf der Physikseite überlegen; die einzige sinnvolle Aufwertung ist die Forecast-bewusste Außentemperatur.

## Nachtrag (v0.8.1): Forecast-bewusste Außentemperatur — Lücke geschlossen
Die unter „Bewertung" identifizierte Lücke (Konstant-Außen) ist umgesetzt. Neu:
- **Pure** `optimal_start.mean_forecast_outdoor(samples, horizon_min, fallback)`: zeitgewichtetes Mittel der prognostizierten Außentemperatur über `[0, horizon]` (stückweise-linear zwischen `(minutes_from_now, temp)`-Stützstellen, außerhalb flach gehalten — analog ha-preheats `integrate_forecast`). Fehlt der Forecast/Horizont → `fallback` (= konstante aktuelle Außentemperatur). Voll unit-getestet.
- **Coordinator** `_forecast_outdoor(horizon, fallback)`: ruft `weather.get_forecasts` (hourly, `return_response`), cached bis `FORECAST_TTL_S=900 s`, baut die Stützstellen aus den Forecast-Einträgen und mittelt über `minutes_to_comfort` (das Vorheiz-Deadlinefenster). Jede Störung/fehlende `weather`-Entity → Fallback, d. h. Optimal-Start hängt nie vom Forecast ab.
- **Config:** optionales `weather_entity` (EntitySelector domain=weather). **Diagnose:** `preheat_outdoor` (verwendete Außentemperatur).
- Damit nutzt Poise — wie RoomMind und das eigene ha-preheat — die **Außentemperatur über das Vorheizfenster** statt eines Momentanwerts, behält aber die geschlossene Exponential-Inversion (physikalisch genauer als ThermoSmarts lineare Rate). Gate v0.8.1: ruff (inkl. `format --check`), mypy strict, pytest+cov grün.
