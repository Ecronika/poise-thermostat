# Nachprüfung: v0.167.0 gegen Review und Nachprüfung v0.166.0

*Geprüfter Stand: Commit `88d4d0a` (main, v0.167.0, Tag `v0.167.0-alpha`) gegen das Review zu v0.163.0 und die Nachprüfung zu v0.166.0 (beide in `docs/reviews/`).*

## Prüfstand

| Prüfung | Ergebnis |
| --- | --- |
| `ruff check` / `format` | ✅ sauber (232 Dateien) |
| `mypy` (strict, lokal mit HA 2024.12.5) | ⚠️ 22 Fehler — unverändert nur HA-Glue-Typing; CI-Blindstelle P3-17 besteht |
| Pure-Core | ✅ **747 Tests grün**, Coverage 97,72 % |
| HA-Integration | ✅ **184 Tests grün** (v0.166: 173; +11), Glue-Coverage lokal **95,02 % — das 95-%-Gate ist damit erstmals auch lokal grün** (v0.163: 94,70 %; v0.166: 94,63 %) — die neuen Gate-/Defer-Tests decken genau die zuvor ungedeckten config_flow-Zeilen |
| Coverage-Flake | ⚠️ **Reproduzierbares Muster:** Unter Coverage-Instrumentierung schlagen einzelne `test_config_flow`-Tests nichtdeterministisch im **Teardown** fehl (2 von 6 Läufen; wechselnde Tests) — „Lingering timer … `Store._async_schedule_callback_delayed_write`“. Quelle ist ein **HA-Core-Store** mit verzögertem Write (Poise selbst nutzt ausschließlich `async_save`, verifiziert). Ohne Coverage: 0 Fehler in mehreren Läufen. Da der CI-Integrationsjob exakt diese Kombination fährt, ist das ein latentes CI-Flake-Risiko. |
| CI / Releases | **Diesmal nicht verifizierbar** (GitHub-API über den Proxy 403, MCP-Anbindung getrennt). Verifiziert per Git: **erster Tag `v0.167.0-alpha` auf `88d4d0a`** — Beginn von J1; ob ein GitHub-Release-Objekt existiert, konnte nicht geprüft werden. |

## A. Erledigt in v0.167.0

| Befund | Umsetzung | Beleg | Bewertung |
| --- | --- | --- | --- |
| **B1** (Nachprüfung): ADR-0046 dokumentierte nicht implementierten atomaren Write samt nicht existierender Tests | **Aufgelöst über Weg „Doku korrigieren“:** Der Nachtrag §8 wurde neu gefasst — „Ausgeliefert: Guard-Defer“, „**Zurückgestellt (NICHT implementiert):** der atomare Mode+Setpoint-Write“, mit nachvollziehbarer technischer Begründung (ein pauschales `hvac_mode`-Mitsenden in `service_call_for` hätte über die Safe-State-/Frost-Rescue-Pfade den Verdichterschutz umgangen) und Wiederaufnahme-Plan (opt-in Command-Flag). Die irreführenden Coordinator-Kommentare wurden ebenfalls korrigiert („the actuator currently writes temperature only … was reverted“). | docs/adr/ADR-0046 Nachtrag §8; coordinator.py:2629–2649 | ✅ sauber gelöst; ADR und Code stimmen wieder überein. Rest siehe B-neu-1. |
| **B2** (Nachprüfung): Flow-Gates und Guard-Defer ungetestet | **Vollständig geschlossen:** `test_p2_gates_and_defer.py` mit 8 Tests — °F-Gate (user + reconfigure), heat_cool-Gate (room + reconfigure), **Guard-Defer** (min-off geseedet → `mode_nudge_blocked` gesetzt → kein einziger `set_temperature`-Call; Testkörper verifiziert, inkl. des subtilen Re-Arm-Details der Service-Mocks nach Setup) + 3 Flow-Randfälle | tests/integration/test_p2_gates_and_defer.py | ✅ |
| **B3** (Nachprüfung): Register-Prosa widersprach den Wirkung-Headern | Prosa korrigiert: 0050/0051/0052 jetzt ausdrücklich „**Live aktuiert** … `Live-A`“, 0054/0055 `Live-D`, 0056 `Shadow` | docs/adr/README.md „Umsetzungsstand“ | ✅ (Rest: Registertabelle weiterhin ohne Wirkung-Spalte, kein Header↔Register-Lint — kosmetisch) |
| **P2-2** (Review): kein Keep-Alive des External-Temp-Feeds | Pure Funktion `external_feed_due` (Wertänderung ≥ 0,1 K **oder** Keep-Alive abgelaufen; `0` deaktiviert), `EXTERNAL_FEED_KEEPALIVE_S = 600`, `_last_fed_ts` monotonic, nur bei erfolgreichem Call fortgeschrieben; 2 Integrationstests (Re-Push nach Ablauf, Sofort-Push bei Änderung) | tick_resolve.py:163–187; const.py:30–34; coordinator.py:2691–2708; tests/integration/test_external_feed_keepalive.py | ✅ 600 s liegt sicher unter dem Danfoss-30-min- und TRVZB-1-h-Fallback. Fester Wert (keine Option) und im README nicht erwähnt — akzeptabel, siehe C. |
| **P1-4b** (Review): Override-Ablauf ohne Poise-Card unsichtbar | Neuer `override_expires_at`-Sensor (device_class TIMESTAMP, **default-enabled**), README-Entitätenliste aktualisiert (17 Sensoren), strings/de/en, Timestamp-Rendering-Test + angepasster Default-Enabled-Test | sensor.py:241–250, 56–70; tests/integration/test_entity_defaults.py | ✅ Sichtbar sind jetzt 6 Entities/Zone (climate, Bypass, operative Temp., Konfidenz, Lernphase, Override-Ablauf) — das Review-Kriterium „≤ 6“ wird exakt eingehalten. |
| **J1** (Review): keine Releases/Tags | Erster Tag **`v0.167.0-alpha`** | `git ls-remote --tags` | ✅ begonnen; Release-Objekt/Changelog unbestätigt (API nicht erreichbar) |

## B. Neue bzw. verbliebene Fehler und Unvollständigkeiten

**B-neu-1 (P3, Ein-Satz-Fix) — Inverse Drift im frisch korrigierten ADR-0046-Nachtrag.** Der neue Nachtrag schließt mit *„Das Guard-Defer-Gate ist derzeit **ohne dedizierten Test**“* — im selben Release liegt aber `test_guard_defers_setpoint_write_under_min_off`, der genau dieses Gate prüft. Die Korrektur der einen Drift hat eine kleine gegenläufige erzeugt. Abhilfe: Satz streichen bzw. durch den Testverweis ersetzen.

**B-neu-2 (P3, mit CI-Risiko) — Coverage-Teardown-Flake in `test_config_flow`.** Reproduzierbar nur unter `--cov` (2/6 Läufen, wechselnde Tests): „Lingering timer after test `Store._async_schedule_callback_delayed_write()`“ im pytest-hacc-Teardown. Poise selbst schreibt seinen Store ausschließlich synchron (`async_save`, storage.py:46/80) — der verzögerte Write stammt aus einem HA-Core-Store (Registry/Config-Entries), dessen Timer beim Testende noch anhängt; Coverage-Verlangsamung öffnet das Zeitfenster. Der CI-Integrationsjob fährt exakt diese Kombination — der Flake kann also jederzeit einen grünen Commit rot machen. Abhilfe: in den betroffenen Flow-Tests abschließend `await hass.async_block_till_done()` nach Entry-Setup/-Abort konsequent setzen bzw. angelegte Entries explizit entladen; alternativ das bekannte pytest-hacc-Muster `expected_lingering_timers` gezielt nicht nutzen, sondern die Store-Flushes abwarten.

**B4 (Nachprüfung, unverändert) — `review_verification_report.md` liegt weiter an der Repo-Wurzel** und beschreibt den alten F1–F18-Zyklus. Gehört nach `docs/reviews/` oder gelöscht — am jetzigen Ort suggeriert es fälschlich den aktuellen Abarbeitungsstand.

**B5 (Nachprüfung, unverändert, mild):** `_window_open_since` (P2-1-Unterdrückung) ist monotonic und nicht persistiert — nach HA-Neustart bei offenem Fenster beginnt die 30-min-Unterdrückung erneut.

**Randnotizen:** Der Ext-Feed-Keep-Alive ist im README nicht dokumentiert (die Konfigurationstabelle erwähnt den Feed, nicht das 10-min-Re-Push-Verhalten — für Danfoss-/TRVZB-Nutzer wäre genau das ein Kaufargument). `EXTERNAL_FEED_KEEPALIVE_S` ist bewusst konstant statt Option — vertretbar, sollte aber in einer künftigen Gerätematrix (J9) je Gerätetyp begründet werden.

## C. Weiterhin offen (aus dem „Jetzt“-Block des Reviews)

| Punkt | Status v0.167.0 |
| --- | --- |
| **P1-4a** Geräteseitige Sollwertänderung (TRV-Rad) wird binnen ≤ 60 s überschrieben | unverändert offen — mit P1-4b ist die *Sichtbarkeit* gelöst, die *Kontrolle* nicht; die README-Aussage „Poise übernimmt den von Hand gestellten Wert“ (gilt nur für die Poise-Entity) steht unverändert |
| **P1-3** Frontend/Backend-Vertragstest (~100 Card-Attribute) | offen |
| **P2-5** Harness: Plant ≙ EKF-Prior; `replay.py`-„same code path“; README „production-identical“ | offen |
| **J9** Troubleshooting-Guide + Gerätekompatibilitätsmatrix | offen |
| **J1** Release-Prozess | begonnen (erster Tag); Changelog/Release-Objekte und HACS-Versionierungspraxis noch offen |
| P3-Reste | unverändert: PI-Shadow-dt/acc, Ratelimit „pro Aufruf“, `identified` richtungsagnostisch, FBH-4-h-Preheat-Horizont, virtuelle-MRT-Kopplung 0,08, CO₂-Karte ohne Backend, Card-Editor nur Englisch, i18n-Paritätstest, mypy-CI-Blindstelle, HA-Minimum 2025.1 ungeprüft (lokal läuft die Suite auf HA 2024.12.5) |

## D. Gesamtbewertung

v0.167.0 arbeitet die Nachprüfung fast vollständig ab: **B1 wurde auf dem ehrlichen Weg gelöst** (Doku an den Code angepasst statt umgekehrt, mit technisch stichhaltiger Begründung für die Rücknahme), **B2 und B3 sind geschlossen**, und mit **P2-2** und **P1-4b** sind zwei der wirkungsvollsten kleinen Review-Punkte umgesetzt — beide sauber mit pure Funktion + Integrationstests, und das Glue-Coverage-Gate ist dadurch erstmals auch lokal grün. Der erste Git-Tag markiert den Einstieg in J1.

Damit sind von den ursprünglichen Beta-Blockern des Reviews noch offen: **P1-4a** (Geräte-Sollwert-Adoption — der größte verbleibende Anwenderschmerz und jetzt der klar nächste große Block), **P1-3** (Vertragstest), **Feldnachweis/Gerätematrix** (J9/J12) und die Vervollständigung des Release-Prozesses. Kurzfristig empfohlen: den einen falschen Satz im ADR-0046-Nachtrag streichen (B-neu-1), den Coverage-Teardown-Flake entschärfen, bevor er die CI trifft (B-neu-2), und `review_verification_report.md` verschieben (B4) — alles Kleinaufwand. Danach ist P1-4a der sinnvolle Schwerpunkt für v0.168.

---

*Nachprüfung erstellt am 13.07.2026 gegen `88d4d0a`; lokale Läufe mit Python 3.13.12, HA 2024.12.5. CI-/Release-Status war in dieser Sitzung nicht abrufbar (Proxy 403); Tag-Existenz per `git ls-remote` verifiziert. Methodik: vollständiger `git diff d9dcc91..88d4d0a`, Ausführung aller Suiten (Coverage-Läufe sequenziell/isoliert), Verifikation der Testkörper (Guard-Defer) und der Flake-Ursache (6 instrumentierte Wiederholungsläufe, Traceback-Analyse).*
