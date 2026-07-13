# Nachprüfung: v0.168.1 — Hotfix für den P1-Befund der v0.168.0-Nachprüfung

*Geprüfter Stand: Commit `5d38ab8` (main, v0.168.1, Release `v0.168.1-alpha`) gegen die Nachprüfung zu v0.168.0.*

## Prüfstand

| Prüfung | Ergebnis |
| --- | --- |
| CI | **#1188/#1189 auf `5d38ab8` grün** (main + Release-Tag); Zwischen-Uploads rot (bekanntes Muster) |
| Release | `v0.168.1-alpha` (Prerelease) — ohne Release-Notes-Text (v0.168.0 hatte eine Changelog-Zeile; Randnotiz) |
| `ruff check` | ✅ sauber |
| Pure-Core / Integration | ✅ 755 bzw. **188** Tests grün (+1 Regressionstest); Glue-Coverage lokal 95,34 %, Gate grün, kein Teardown-Flake |

## Ergebnis: B1 und B2 vollständig und exakt wie empfohlen behoben

**B1 (P1 — selbst-verlängernder In-Band-Hold):** Nach einer Adoption werden jetzt `_last_written_sp = snap_to_step(adopted, step)` und `_last_sp_write_ts = now` gestampt (coordinator.py:2661–2671) — der Gerätewert ist ab sofort die bekannte Echo-Baseline. Der Begründungskommentar erklärt auch den Out-of-Band-Fall korrekt (der geklemmte Folge-Write re-stampt die Baseline selbst).

**B2 (P3 — Safe-State-Werte als „Nutzerintent“):** Beide Pfade am regulären Write vorbei — `_write_unavailable_safe_state` (:1778) und Frost-Rescue (:2811) — setzen die Baseline auf `None` zurück; der Baseline-Guard des Detektors unterdrückt damit jede Adoption bis zum nächsten regulären Write. Das ist die robustere der beiden vorgeschlagenen Varianten.

**Regressionstest:** `test_adopted_hold_is_stable_across_ticks` prüft exakt das Akzeptanzkriterium der Nachprüfung — über zwei Ticks plus Resume: Expiry unverändert, L1-Statistik wächst nicht, `resume_schedule` bleibt bestehen.

**Laufzeit-Gegenprobe (unabhängig vom mitgelieferten Test):** Der Zwei-Tick-PoC aus der v0.168.0-Nachprüfung wurde erneut gegen `5d38ab8` ausgeführt und schlägt jetzt erwartungsgemäß fehl — gemessen: Expiry-Drift **0,0** (vorher +1,1 s je 1,1 s Wall-Zeit), Statistik **1 → 1** (vorher +1/Tick), Override nach Resume + 1 Tick **None** (vorher wieder 23.0). Die Resume-Semantik ist konsistent: Nach dem Resume wird der Gerätewert nicht re-adoptiert (Baseline = Gerätewert) und Poise setzt im Folge-Tick den Planwert durch.

## Offen bleibt

- **B3 (P3, v0.168.0-Nachprüfung) — nicht adressiert:** Der Lost-Command-Fall (Poises Write geht verloren, Gerät behält den alten Wert) wird nach Ablauf des Echo-Fensters weiterhin als Nutzer-Hold adoptiert statt re-asserted. Abhilfe unverändert: Baseline-Historie über die letzten zwei Writes. Klein, aber genau die flaky Geräte betreffend, denen die Adoption dienen soll (Community-Cluster 8).
- **B4 — vierte Runde offen:** `review_verification_report.md` (Alt-Zyklus F1–F18) liegt weiterhin an der Repo-Wurzel.
- Unverändert aus dem Review: **P1-3** (Frontend/Backend-Vertragstest), **P2-5** (Harness ≙ Prior, „production-identical“-Behauptung), **J9** (Troubleshooting + Gerätematrix), **J12** (Feldtests/CA-Berichte) sowie die bekannten P3-Reste (u. a. mypy-CI-Blindstelle — lokal weiterhin 22 Fehler, `identified` richtungsagnostisch, FBH-Preheat-Horizont, virtuelle-MRT-Kopplung).

## Fazit

Der Hotfix ist vollständig, minimal-invasiv und deckungsgleich mit der empfohlenen Abhilfe; der laufzeitbestätigte P1 aus v0.168.0 ist beseitigt und per Regressionstest dauerhaft abgesichert. **P1-4 (geräteseitige manuelle Eingriffe) ist damit funktional komplett** — bis auf den B3-Randfall, der sich als kleiner Folgepunkt anbietet. Ab diesem Stand ist die Adoption als Teststand-Feature vertretbar; als nächste Schwerpunkte bleiben Vertragstest (P1-3), Feldnachweis/Gerätematrix (J9/J12) und die Harness-Ehrlichkeit (P2-5).

---

*Nachprüfung erstellt am 13.07.2026 gegen `5d38ab8`; lokale Läufe mit Python 3.13.12, HA 2024.12.5. Methodik: `git diff e32c1ac..5d38ab8`, Ausführung aller Suiten, PoC-Gegenprobe.*
