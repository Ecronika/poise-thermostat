# ADR-0003: Residual-Heat / Optimal-Stop als advisory Dienst

**Status:** akzeptiert · **Datum:** 2026-06-18 · **Bezug:** K5, E18 · **Verifizierung:** V4

## Kontext
Optimal Start und Optimal Stop/Coasting können entweder **eigenständig** Stellbefehle erzeugen oder dem MPC nur **Information** liefern. Zwei konkurrierende Trajektorien-Eigentümer (MPC-Horizont *und* dedizierter Optimal-Start) sind die Konfliktklasse **K5** — und entsprechen exakt der real aufgetretenen Re-Entry-Bugklasse des eigenen Stacks (`_start_preheat` ohne Guard).

## Entscheidungstreiber
Genau **ein** Trajektorien-Eigentümer (Re-Entry-Vermeidung), Messbarkeit des Nutzens (Outcome-Scoring, G11), Vermeidung von Doppelzählung der Restwärme.

## Betrachtete Optionen
1. **Advisory:** `optimal_start`/`optimal_stop`/`residual_heat` liefern Schätzgrößen, die der MPC in Vorhersage/Kostenfunktion konsumiert; **der MPC besitzt die Trajektorie**.
2. **Eigenständiger Optimal-Stop-Regler:** ein Modul entscheidet selbst „jetzt abschalten" und schreibt/sperrt — parallel zum MPC.

## Entscheidung
**Option 1 (advisory).** `residual_heat` ist ein **reines Berechnungsmodul** ohne Aktorik. Es liefert eine **normierte Restwärme-Fraktion ∈ [0,1]** mit getrennten Lade-/Entlade-Zeitkonstanten `τ_charge`/`τ_discharge`. Diese wird als Parameter `q_residual` in die Vorhersage `RCModel.predict()` eingespeist und dort **HVAC-aus-gegated** (nur wirksam, wenn nicht aktiv geheizt/gekühlt wird), um Doppelzählung zu vermeiden. **Coasting/Optimal-Stop entsteht emergent**, weil der Optimierer wegen des advisory Restwärme-Terms früher auf IDLE plant. `optimal_start` liefert analog Zielzeit/Vorlaufschätzung an den Horizont, kommandiert nicht selbst (mit Idempotenz-Guard).

## Begründung
V4 hat am RoomMind-Code belegt, dass `residual_heat.py` ausschließlich reine Funktionen enthält (keine Service-Calls, kein Mode-Entscheid), eine Fraktion ∈[0,1] zurückgibt und als additiver, gegateter Term in `predict()` einfließt. Option 2 würde genau den K5-Konflikt (zweiter Trajektorien-Eigentümer, Re-Entry) herstellen, den Option 1 baulich ausschließt. Der Nutzen des Coastings bleibt über das Outcome-Scoring messbar, statt blind „eingebaut" zu sein.

## Konsequenzen
**Positiv:** kein Doppel-Trigger/Re-Entry; ein konsistenter Trajektorien-Eigentümer; Restwärme physikalisch korrekt (τ_charge/τ_discharge) und nur im Drift wirksam; Nutzen messbar.
**Negativ/Kosten:** Coasting ist **nicht separat kommandierbar**. Ein im UI **explizit sichtbarer** „Optimal-Stop"-Zustand (falls gewünscht) existiert bei RoomMind nicht und muss von uns als **reiner Diagnose-Wert** aus dem advisory-Term abgeleitet/gekapselt werden — ohne eigenen Schreibpfad.

## Verifizierung
V4: `residual_heat.py` (`compute_residual_heat`, `build_residual_series` — reine Funktionen, Rückgabe Fraktion); `mpc_controller.py` (`_build_residual_series`, Übergabe `residual_series` an `optimizer.optimize`); `thermal_model.py:predict()` (`Q_residual = Q_heat·q_residual` nur bei `Q_active==0`). Tests: „residual_heat erzeugt keine Service-Calls"; Szenario-Test Coasting im Replay-Harness; Regressionstest gegen Re-Entry (Startzeit wird nicht jeden Tick zurückgesetzt).

## Compliance
Advisory-Schnittstelle eigenständig nachimplementiert; generisch (Systemtyp-Profil FBH/Radiator als Parameter, nicht gerätespezifisch).

## Verknüpfungen
Konsumiert das `RCModel`/`predict()` aus ADR-0002, gehört in den Horizont von ADR-0001. Offene Folge: E18 (Glättung/Verhalten bei fehlendem MRT der Operativ→Luft-Kette berührt die Drift-Schätzung).
