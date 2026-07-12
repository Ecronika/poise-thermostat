# ADR-0028: Seasonless-Rate als EKF-Cold-Start-Prior

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-20 · **Bezug:** Charta G12/G6, ADR-0004 (Seed), ADR-0009 (EKF), ADR-0026 (Schatten-Schätzer), Phase 2 · **Verifizierung:** ThermoSmart `learning_engine.py` (Feat 2, normalisierte Rate + Gauss-Kernel + 180d-Halbwertszeit)

## Kontext
Der EKF startet β_h (Heiz-Responsivität) auf einem statischen Default und braucht echte Heizzyklen, um ihn zu lernen. Zu Saisonbeginn (erste kalte Tage) ist β_h daher unsicher. Charta G12 fordert **saisonübergreifendes, alterungsbewusstes** Lernen: Raten gegen das treibende ΔT normalisiert, nach Ähnlichkeit gewichtet, mit Halbwertszeit vergessen.

## Entscheidung
1. **Pure `estimation/seasonless_rate.py`** (ThermoSmart-Methode, code-verifiziert): normalisierte Rate `heat_rate/(target−outdoor)`; Pooling per **Gauss-Außentemp-Kernel** (σ=5 K) × **Halbwertszeit** (180 d); Lernphasen <5/<50/<150/≥150. `heat_rate_prior(target, outdoor, day)` rekonstruiert die erwartete Aufheizrate für die aktuellen Bedingungen.
2. **Shadow-Schätzer (ADR-0026):** akkumuliert in jedem Heiz-Tick (Rate aus Raumtemperaturanstieg bei `u_h>0`), persistiert im Store (`{ekf, trm, seasonless}`), als Diagnose exponiert (`seasonless_phase`, `seasonless_rate`).
3. **Nur Cold-Start-Seed, nie parallel (G6, Strukturplan):** β_h wird beim Bootstrap aus `heat_rate_prior` geseedet **ausschließlich solange `ekf.n_heating == 0`** (der EKF hat noch nie Heizen beobachtet) und seasonless reif ist. Sobald der EKF aus echtem Heizen lernt, besitzt er β_h allein. Physik: zu Beginn der Aufheizung ist `dT/dt ≈ β_h` (Verlustterm noch klein), daher taugt die vorhergesagte Aufheizrate als β_h-Seed (geklemmt auf EKF-Bounds via `seed_beta_h`).

## Begründung
Die Normalisierung gegen ΔT macht Oktober- und Januar-Daten vergleichbar; der Gauss-Kernel gewichtet ähnliche Außenbedingungen; die Halbwertszeit lässt das Gebäude altern. Das `n_heating==0`-Gate greift genau dann, wenn der EKF für das Heizen noch nichts gelernt hat — typischerweise zu Saisonbeginn — und nutzt den über den Vorwinter akkumulierten, saison-normalisierten Prior, ohne je parallel zu regeln.

## Konsequenzen
**Positiv:** schnellerer, datengestützter β_h-Cold-Start zu Saisonbeginn; saison-/alterungsbewusst (G12); rein beratend (G6); Schatten-Persistenz. **Negativ/Offen:** (a) der Seed feuert nur bei `n_heating==0` — im Hochwinter mit gelerntem EKF inaktiv (gewollt); (b) Mapping „Aufheizrate ≈ β_h" ist eine Näherung (Verlustterm vernachlässigt), bewusst konservativ + geklemmt; (c) Seed nutzt das mittlere Beobachtungs-Außenniveau als repräsentative Bedingung. **Damit ist Phase 2 (Lern-Kern) abgeschlossen.**
