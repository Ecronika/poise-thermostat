# ADR-0045: Effizienz-Report — Heating-Degree-Hours → kWh/€

**Status:** Implementiert · **Wirkung:** Live-D · **Datum:** 2026-06-24 (verdrahtet 2026-06-30, v0.97.0) · **Bezug:** ADR-0025 (Setback/Schedule liefert die Einsparung), ADR-0011 (Test-first), ADR-0026 (Schatten-Prinzip) · **Grundlage:** `Konzept_Best-of-Integration.md` Feat 20; Vesta `climate.py`/`sensor.py` (quellcode-verifiziert, `portbusy/ha-vesta`)

## Kontext
Eine der 5 echten Konzept-Lücken (Feat 20, ⬜): ein verständlicher €/kWh-Einsparungsreport für Laien (Adoptions-Hebel). **Quellcode-verifiziert (Vesta):** je Minute `ΔT_saved/ΔT_base/60` akkumulieren (`ΔT_base = max(1, comfort−outdoor)`), `saved_fraction = Σ_saved/Σ_eligible_min`, `saved_kWh = saved_fraction · Jahres-kWh/12`, `× Preis = €/Monat`, Monats-Reset, ~11 Sensor-Entities. **Korrekturen am Konzept (am Code geprüft):** *keine* Fraunhofer-kWh/m²-Raten — die Fallbacks sind feste Brüche; Fenster nutzt `comfort−Frostschutz`, nicht den Live-Sollwert. Es ist eine **Schätzung** aus einem konfigurierten Jahresverbrauch, keine kWh-Messung — ehrlich by design.

## Entscheidung
1. **Pure Helfer `control/hdh_savings.py` (test-first):** `saved_fraction_tick(comfort, setpoint, outdoor, dt_min)` (0, sobald `comfort ≤ outdoor` oder Sollwert = Komfort), `HdhSavings`-Akkumulator (Monats-Reset, `report()` → kWh/€/%), persistierbar. Vesta-Methode re-implementiert (kein Copy).
2. **Einsparung = Poises Absenkung gegen Vollkomfort:** `comfort = comfort_base`, `setpoint = effektiver Heiz-Sollwert` (niedriger bei Nachtabsenkung/Eco/Coasting). Misst also genau, was Poises Setback/Preset/Optimal-Stop spart.
3. **Ehrliche Schätzung:** Default Jahres-kWh 12000 + 0,30 €/kWh; per Config überschreibbar. Kein Anspruch auf Messgenauigkeit (Attribut-Benennung + Doku machen das klar).
4. **Coordinator-Glue:** Monatswechsel + `observe` je Tick, Diagnose `savings_kwh_month`/`savings_eur_month`/`savings_pct`, im Save-Payload.

## Konsequenzen
**Positiv:** schließt eine benannte Konzept-Lücke; verständlicher Laien-Mehrwert; pure+getestet; **Sommer akkumuliert sauber 0** (kein Heizgradient) und rampt ab der Heizsaison. **Negativ/ehrlich:** Schätzung, nicht gemessen (wie bei Vesta); braucht eine kleine Config (Jahresverbrauch/Preis) für genaue €-Werte, sonst Defaults; primär im Winter wirksam (im Sommer Anzeige 0).

## Verifizierung
**Verdrahtet (v0.97.0):** Der Coordinator akkumuliert je Tick `HdhSavings.observe(comfort=comfort_base, setpoint=heat_sp, outdoor=t_out_eff, dt_min=Tick, now_month=…)` (`control/hdh_savings.py`, Monats-Reset) und exponiert `savings_kwh_month`/`savings_eur_month`/`savings_pct` im Tick-Return; `HdhSavings` im Save-Payload (`hdh_savings`) + Bootstrap-Restore. **Tarif konfigurierbar:** `CONF_ANNUAL_KWH`/`CONF_PRICE_EUR_KWH` (Default 12000 kWh / 0,30 €/kWh) als NumberSelector im Options-Flow (`_options_schema`) + **Hot-Apply** (`async_apply_options` liest `HdhConfig` neu) + i18n de/en. **Defensiv gekapselt** (gemeinsam mit Outcome-Scoring; ein Diagnose-Fehler killt nie den Regel-Tick). **Pure (bestehende `hdh_savings`-Tests grün):** monatliche Akkumulation, Sommer→0, kWh/€/%-Report. Glue (Coordinator/Config-Flow) CI-verdrahtet, von mir nicht ausgeführt (Sandbox-Dehydrierung). **Schätzung, keine Messung** — Attribut-Benennung (`*_month`) + Doku machen das klar.
