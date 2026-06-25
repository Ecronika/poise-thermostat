# ADR-0010: Solar-Buchhaltung

**Status:** akzeptiert · **Datum:** 2026-06-18 · **Bezug:** E19, K3 · **Verifizierung:** Code-Review RoomMind `solar.py`/`mpc_controller.py`/`thermal_model.py`, BT `mpc.py` (Thema F)

## Kontext
Solareintrag droht doppelt zu wirken: als Störgröße im Wärmemodell **und** als MRT-Anhebung der Operativtemperatur (K3). Zusätzlich kann eine orientierungsabhängige Solar-Rückkopplung mit der Verschattung oszillieren. Offen: ein einziger, definierter Solar-Pfad.

## Entscheidungstreiber
Doppelzählung vermeiden; Oszillations-Rückkopplung Cover↔Solar vermeiden; Orientierung dort nutzen, wo sie hilft (Verschattung), nicht dort, wo sie schadet (Regelung).

## Befund am Code (Belege)
- **RoomMind = sauberes Vorbild:** Solar ist gelernte **Störgröße `β_s` im EKF-Zustand** (`_predict_step`: `u = u_hvac + beta_s·q_solar + beta_o·q_occupancy + …`; Jacobian lernt `β_s` nur bei `q_solar>0`); Eingang `q_solar = GHI/1000` (normiert, damit β_s größenvergleichbar bleibt). **Im MPC-Pfad bewusst ungerichtetes/unbeschattetes GHI** — expliziter Kommentar: *„MPC uses unshaded solar to avoid oscillation feedback loop: covers deployed → low solar prediction → retract → high solar → deploy"*. `build_oriented_solar_series` (Fassaden-Azimut) existiert, wird aber **nur im Cover-Pfad** genutzt. Im Komfort-/Peak-Vorhersagepfad: `q_solar = self.q_solar · shading_factor`.
- **BT = Negativbeleg:** Solar verdrahtet, aber **inert** — die Solar-Subtraktion im u0-Baseload ist **auskommentiert** (`# - (solar_gain_factor·solar_intensity)`); Felder existieren, einziger Verbrauchspunkt deaktiviert.

## Entscheidung
1. **Ein einziger physikalischer Solar-Pfad: gelernte Störgröße `β_s` im Zustandsschätzer.** Solar wirkt genau **einmal** als additiver Wärmeeintrag im Modell.
2. **MPC-Stellgrößenoptimierung nutzt ungerichtetes/unbeschattetes GHI** (Anti-Oszillation, RoomMind-Muster).
3. **Verschattung wirkt nur auf den Eingang des Komfort-/Vorhersagepfads** (`q_solar·shading_factor`), **nie** als Rückkopplung in die Cover-Stellgröße selbst.
4. **Fassadenorientierung ausschließlich im Cover-/Verschattungspfad**, nicht im β_s-/MPC-Pfad.
5. **Operativtemperatur/MRT-Pfad** bringt Strahlung als Strahlungsasymmetrie ein — Doppelzählung ist ausgeschlossen, **solange der MRT-Pfad nicht denselben konvektiven Wärmeeintrag verbucht** wie β_s (β_s = konvektiver Eintrag in die Luftbilanz; MRT = Strahlungstemperatur-Empfinden, getrennte Größe).

## Begründung
RoomMind hat die Doppelzählungs- und Oszillationsfalle bereits gelöst und im Code dokumentiert; BT zeigt, dass selbst eine vorhandene Solar-Logik ungenutzt bleibt, wenn die Buchhaltung ungeklärt ist. Die strikte Pfadtrennung (β_s = Modell, shading = nur Komfort-Eingang, Orientierung = nur Cover) ist die einzige konsistente Lösung.

## Konsequenzen
**Positiv:** kein systematischer Unterheiz-/Überkühl-Bias an sonnigen Tagen; keine Cover↔Solar-Pendelschleife; gemessene Globalstrahlung (eigener Sensor) als β_s-Beobachtung **und** MRT-Eingang nutzbar, ohne sie doppelt zu zählen.
**Negativ/Kosten:** erfordert klare Disziplin an der Grenze β_s ↔ MRT (Invariante testen, dass nicht derselbe Wärmestrom zweimal eingeht); Verschattung muss saison-/zielbewusst bleiben (K17/ADR-Folge), damit sie im Heizregime nicht Gratiswärme aussperrt.

## Compliance
Physikmodell eigenständig nachimplementiert; gemessene Globalstrahlung ist ein generischer Eingang (kein gerätespezifischer Sonderweg).

## Verknüpfungen
Konkretisiert K3 und die Estimation-Ebene aus ADR-0002. Verschattungs-Saison-Logik bleibt offene Folge (K17). Invariantentest „Solar nicht doppelt verbucht" gehört in ADR-0011.

## Nachtrag (v0.10.0): Solar-Schatten-Schätzer verdrahtet
Die in dieser ADR beschlossene β_s-Buchhaltung war im EKF vorhanden (`predict(q_solar)`, Jacobian `f[T][BS]`, mode-gated Prozessrauschen `if q_solar>0: p[BS][BS]+=Q[BS]`), aber der Coordinator speiste konstant `q_solar=0` → β_s untrainierbar. Jetzt umgesetzt (ADR-0026-Schatten-Prinzip):
- **Pure `estimation/solar.py`:** `clear_sky_normalized(elevation_deg)=max(0,sin(elev))` (interner Clear-Sky-Proxy aus Sonnenstand) + `normalize_irradiance(ghi, ref=1000)` (gemessene Globalstrahlung → [0,1], RoomMind-Normierung GHI/1000).
- **Coordinator:** interner q_solar läuft **immer** (aus `sun.sun`-Elevation); optionaler Globalstrahlungssensor (`irradiance_sensor`, device_class=irradiance) **überschreibt nur den verwendeten Wert**. q_solar des Vortakts geht in `_learn`→`predict` (deckt das verstrichene Intervall). Diagnose-Attribute `q_solar`, `q_solar_source` (sensor/internal/none), `q_solar_internal` (Schatten), `beta_s` (live lernend sichtbar).
- **Wirkung:** β_s wird tagsüber angeregt und lernt; MPC/Optimal-Start werden solarbewusst. Anti-Oszillation/Doppelzählung unverändert gemäß Punkten 2–5 dieser ADR (ungerichtetes GHI, getrennt von MRT). Gate v0.10.0: 168 Tests, ruff+format+mypy grün.
