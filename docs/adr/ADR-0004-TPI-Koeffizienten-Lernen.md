# ADR-0004: TPI-Koeffizienten-Lernen — physikalischer Seed + Online-Nachführung

**Status:** In Arbeit (45 %) · **Datum:** 2026-06-18 · **Bezug:** E21, K7 · **Verifizierung:** V2

## Kontext
Der direkte Ventil-/TPI-Aktorpfad (`control/tpi_valve`) braucht die Koeffizienten `coef_int`, `coef_ext` für `on_percent = coef_int·ΔT_int + coef_ext·ΔT_ext`. Zwei Wettbewerber lösen das Lernen unterschiedlich — beide am Code gelesen.

## Entscheidungstreiber
Konvergenz **ohne** Nutzer-/Gebäudedaten-Eingabe, plausibles Verhalten beim Cold-Start (keine wilde Anfangsphase), laufende Drift-Korrektur, Robustheit gegen Ausreißer/Regimewechsel, Transparenz.

## Betrachtete Optionen
1. **ThermoSmart — physikalisch-statisch:** `coef_int = heat_loss / heat_rate` (aus Gebäudedaten), `coef_ext = coef_int/50`, geklammert. Sofort plausibel, transparent, aber driftet nicht nach.
2. **Versatile — ratio-error-EMA:** `coeff_new = coeff·(theoretisch/real·aggressiveness)`, adaptive EMA `α=0.15/(1+0.08·cycles)`, **Student-t-Regimewechsel** (t>2 → α-Boost), harte Klammern + Lern-Gates. Selbstkalibrierend, reifer — aber heuristiklastig.
3. Manuelles Tuning (Status quo vieler TPI-Regler) — verworfen (widerspricht G19).

## Entscheidung
**Kombination: physikalischer Seed (Option 1) + Online-Nachführung (Option 2).**
- **Initialisierung:** `coef_int` aus dem EKF-Zustand (Verlust `U` und gelernte/geschätzte Heizrate) statt blinder Default-Saat — vermeidet Versatiles 0.1/0.01-Blindstart.
- **Nachführung:** Versatiles **ratio-error-EMA mit adaptiver Lernrate + Student-t-Regimeschutz** und dessen Plausibilitäts-Klammern/Lern-Gates (Sättigung, Boiler-off, Setpoint-Sprung, kleines Außendelta überspringen).
- **`coef_ext`:** konservativ aus dem EKF-Verlustterm ableiten; **Versatiles Kext-Umverteilung wird NICHT 1:1 übernommen** (Identifizierbarkeit fragil, nur Nahfeld `gap<1.0`).
- **Geltungsbereich:** TPI-Pfad nur für **ventilfähige** Geräte (`valve_position`/`pi_heating_demand` schreibbar) — Pfadwahl exklusiv je Gerät (K7).

## Begründung
V2 belegt: Versatiles Lernen ist mächtiger und selbstkalibrierend (ratio-error statt EMA-Rohwert, t-Test-Regimeschutz), konvergiert nutzerdatenfrei — ideal als Online-Schicht. Aber sein Blindstart (0.1/0.01) und die heuristische Kext-Umverteilung sind Schwächen. ThermoSmarts Formel ist transparent und cold-start-sicher, driftet aber nicht. Die Kombination nimmt von beiden die Stärke: physikalisch korrekter Start **plus** laufende Selbstkorrektur. Da wir ohnehin einen EKF (ADR-0002) führen, ist der physikalische Seed „gratis" verfügbar — besser als ThermoSmarts separate Heat-Loss-Schätzung.

## Konsequenzen
**Positiv:** sicherer, plausibler Cold-Start; adaptive Drift-Korrektur; robust gegen Regimewechsel; keine Nutzer-Eingabe nötig (G19).
**Negativ/Kosten:** zwei Mechanismen sind aufeinander abzustimmen (Seed-Übergabe → EMA-Startwert, effective_count-Begrenzung). Die **`coef_ext`-Behandlung bleibt teiloffen** (Ableitung aus EKF vs. eingeschränktes Lernen) → als Detail in E21/E17 zu fixieren. Versatiles Lern-Gates müssen auf unsere Eingänge gemappt werden.

## Verifizierung
V2: Versatile `auto_tpi_manager.py` (`_learn_indoor` ratio/EMA, `_get_adaptive_alpha`, `_detect_regime_change` t>2, Klammern `MIN_KINT`/`MAX_KEXT`, Lern-Gates `_should_learn`), `prop_algo_tpi.py` (Konsum-Formel + `update_parameters`). ThermoSmart `tpi.py` (`coef_int=heat_loss/heat_rate`). Tests: Konvergenz im Replay-Harness aus physikalischem Seed; Property-Test „Koeffizienten bleiben in Klammern"; Regimewechsel-Test (Fenster auf → Lernen pausiert/boostet korrekt).

## Compliance
Lernverfahren eigenständig nachimplementiert (kein Code-Copy aus VT/TS); generisch, gerätunabhängig; gerätespezifische Ventil-Eigenheiten liegen in der Adapter-/model_fixes-Schicht, nicht hier.

## Verknüpfungen
Nutzt den EKF-Zustand aus ADR-0002 (Seed). Aktorpfad-Exklusivität gehört zu K7/E21. Offene Folge: `coef_ext`-Detail (E21), Abstimmung Lernrate mit EKF-Reife (E17).
