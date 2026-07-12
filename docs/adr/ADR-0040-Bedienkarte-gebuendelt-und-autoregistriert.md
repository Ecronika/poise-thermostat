# ADR-0040: Bedienkarte — eigene Lit/TS-Card, gebündelt & auto-registriert

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-22 · **Bezug:** ADR-0016 (Entity-/Card-Vertrag), ADR-0011 (Pure-Core/Test-first), ADR-0021 (i18n), ADR-0022 (Security/Supply-Chain), ADR-0008 (Config-Flow) · **Grundlage:** `Card-Entwurf_Poise.md`, `Wettbewerbsvergleich_Poise-Ist.md`, `Meinungsbild_Mehrzonen-Koordination.md` · **Verifizierung:** HA-Dev-Doc *Registering resources* + Entwickler-Guide *embedded Lovelace card in integration* (Mechanik code-geprüft)

## Kontext
Poise braucht eine erklärende, steuernde Bedienkarte — laut Wettbewerbsvergleich (§3.5) das einzige verbliebene 🟡 in „Bedienung & Adoption" und laut Meinungsbild der zentrale Massenmarkt-Hebel. Der Alt-Prototyp (`card/`) ist gegen das **abgelöste** Blueprint/ha-preheat-Ökosystem verdrahtet; seine zwei Kernprobleme (Climate-Link „Track A", Komfortmodell-Exposition „Track B") sind für Poise **obsolet**, weil Poise als **eine** Integration sein Modell bereits als ~50 Climate-Attribute trägt (ADR-0016) plus den Hub-`binary_sensor` (ADR-0038/0039). Die Card kann also **echte Engine-Werte** lesen statt nachzurechnen. Offen ist nur: Bauform, Best-of-Funktionsumfang und **Verpackung** (eigenes Repo vs. gebündelt).

## Entscheidungstreiber
Einbettbarkeit = Adoption; Versionskonsistenz Card↔Attribut-Vertrag; minimale Installationsreibung (eine Sache installieren); Wartbarkeit/Publizierbarkeit; Generizität (Charta); Test-first wie der Integrations-Pure-Core.

## Befund am Feld (Card-Quellcode geprüft)
Best-of: **Better Thermostat** = sauberstes Lit/TS-Skelett + Blur-Safety-Overlays + eingebettetes Mini-HA-Frontend (kein internes-API-Risiko); **Versatile Thermostat** = `ha-chart-base`-Graph (HA-Core-ECharts, keine Fremd-Lib) + Superstruct + Begründungs-Popups; **ThermoSmart** = sichtbarer Lernzustand (Confidence/Observation). **RoomMind** = Panel + eigene WebSocket-API — bewusst **verworfen** (nicht einbettbar, riesig, Adoptionsgift).

## Entscheidung
1. **Eigene Card, Lit + TypeScript + Build**, **einbettbar pro Zone** (kein Panel, keine eigene WS-API als Datenquelle). Best-of: BT-Skelett + VTherm-Graph/Popups + ThermoSmart-Lernzustand.
2. **Datenquelle ausschließlich HA-Entity-Attribute** — Poise-Climate (ADR-0016) als Ein-Feld-Anker (`getStubConfig`), optionale „Poise System"-Card liest den Hub-`binary_sensor`. Generisch, keine geräte-/herstellerspezifische Logik.
3. **Drei Alleinstellungen:** (a) EN-16798-Komfortband als Hero aus echten `comfort_low`/`comfort_high`/`category`/`t_rm`; (b) **Shadow-Transparenz** (MPC/TPI/PI-Shadow sichtbar — „was die Engine würde", adressiert die Blackbox-Skepsis); (c) Lernzustand (`confidence`/`learning_phase`/`identified`).
4. **Pure `comfort.ts`** (seiteneffektfreie Bandmathematik) **test-first** gegen Norm-Referenz, vom Rendering getrennt (ADR-0011-Disziplin).
5. **Verpackung = gebündelt + auto-registriert** (nicht separates HACS-Plugin-Repo): die gebaute `poise-card.js` liegt im selben Repo unter `custom_components/poise/frontend/`; `manifest.json` deklariert `dependencies: ["frontend","http"]`; eine `JSModuleRegistration` in **`async_setup`** (einmalig, nicht per Entry) ruft `http.async_register_static_paths(...)` und registriert im **Storage-Mode** die Lovelace-Ressource automatisch (`lovelace.resources.async_create_item`); im **YAML-Mode** ist die Datei erreichbar, der Nutzer trägt die Ressource einmal selbst ein. Ein WS-Befehl `poise/version` + Frontend-Versionscheck + Cache-Clear-Reload deckt das Application-Cache-Problem ab (`?v=` allein genügt nicht).
6. **Versionskopplung Card↔Integration ist gewollt** — die Card liest Poises Attribut-Vertrag; sie wird mit der Integration versioniert und in **einem** Release ausgeliefert (`card/`-Source → Build-Output nach `custom_components/poise/frontend/`).

## Begründung
HACS führt ein Repo unter **genau einer** Kategorie (Integration *oder* Plugin) — die gebündelte Auslieferung umgeht diese Hürde elegant, indem die **Integration** die Card selbst ausliefert/registriert (HA-nativ). Das ergibt **eine** Installation (Poise über HACS), Card erscheint nach Neustart automatisch im Karten-Picker — passend zu Poises Kernthese (eine Integration, minimale Reibung). Lit/TS schlägt ThermoSmarts Vanilla-Weg in Wartbarkeit/Typsicherheit; der Nutzer bekommt trotzdem Null-Build (gebündelte `.js`). Das Panel/WS-Modell (RoomMind) gäbe die Einbettbarkeit auf, die für Adoption entscheidend ist.

## Konsequenzen
**Positiv:** eine Installation, automatische Versionskonsistenz, echtes Komfortband statt Näherung, einzigartige Shadow-Transparenz, einbettbar pro Zone, kein HACS-Kategorie-Konflikt. **Negativ/Kosten:** die Card ist an Poise gebunden (nicht generisch ohne Poise nutzbar — hier gewollt); `async_setup`-Frontend-Registrierung + Cache-/Versions-Disziplin sind zusätzliche Glue (untestbar im Sandbox → Live-Verifikation); Frontend-Toolchain (Lit/TS/Rollup) als **Dev**-Abhängigkeit. **Failsafe:** fehlt eine Entität/ein Attribut, blendet die betroffene Sektion aus statt zu brechen.

## Compliance
ADR-0022: die gebündelte `.js` wird **lokal** ausgeliefert, keine zusätzlichen **Laufzeit**-Deps, Build-Deps nur dev. ADR-0016: Card liest exakt den publizierten Attribut-Vertrag. ADR-0021: de/en. ADR-0011: `comfort.ts` test-first. Charta-Generizität: nur HA-Attribute, keine geräte-/herstellerspezifische Logik.

## Verknüpfungen
Konkretisiert ADR-0016 (Card-Vertrag) auf der Frontend-Seite; nutzt den Hub aus ADR-0038/0039 für die optionale System-Card. Detail-Entwurf + Roadmap: `Card-Entwurf_Poise.md`. Separates HACS-Plugin-Repo bleibt eine bewusst **nicht** gewählte Alternative (nur sinnvoll bei generischer Card-Nutzung ohne Poise).

## Umsetzungsstand & Nachträge (v0.49–0.59, live verifiziert)

Die Entscheidung steht; zwei **Mechanik-Details aus #5 wurden bei der Umsetzung präzisiert** (Treiber unverändert):

1. **Registrierung: `add_extra_js_url` statt Lovelace-Ressourcen-Collection.** Der Storage-Mode-Weg (`lovelace.resources.async_create_item`) erwies sich live als HA-versions-fragil (`.loaded`/`.mode`-Erkennung) → Card landete nicht im Picker (v0.49). Umgestellt auf `homeassistant.components.frontend.add_extra_js_url` (lädt das Modul auf jeder Seite, Card self-registriert im Picker) — robust, von Core-Komponenten genutzt (v0.50).
2. **Cache-Bruch: versionsgestempelter Dateiname statt `?v=`-Query.** Der HA-Frontend-Service-Worker cached Asset-URLs hart und ignoriert Query-Strings → veraltetes Modul trotz neuer `?v=` (Ursache eines hartnäckigen Grid-Overflows, weil das alte Modul feste `rows` meldete). Lösung: Modul-URL trägt die Version im **Pfad** (`/poise/poise-card-<VERSION>.js`, per-file `StaticPathConfig` auf die eine on-disk-Datei gemappt) → nie zuvor gecachte URL = garantiert frischer Load bei jedem Upgrade (v0.58). Der WS-Versionscheck (`poise/card_version`, Self-Heal-Toast) bleibt als Zweitsicherung.

**Grid-Sizing (ADR-0016-Card-Vertrag, HA-konform):** Aus dem HA-Frontend-Quellcode verifiziert — `hui-card.getGridOptions()` **merged Element-Defaults mit im Dashboard gespeicherten `grid_options`, Config gewinnt**; `computeCardGridSize` clamped numerische Werte auf `min_/max_`. Daraus die richtige Konsequenz: Default `rows:"auto"` (Zelle = Inhaltshöhe) **+ `min_rows`-Boden** (voll 9 / kompakt 6 / System 4). Der Nutzer kann frei größer ziehen, aber nicht so klein, dass Inhalt clippt; ein veralteter numerischer Override (Altlast aus der Festwert-Ära) wird vom Boden **hochgeclampt und heilt automatisch**. Live verifiziert: Zelle = Inhalt exakt, Overflow 0.

**Funktionsumfang gebaut (P1–P3 + Best-of):** Drag-Dial-Hero mit EN-16798-Band als grüne Arc-Zone, Operativ-Mitte (klick→more-info, getrennt vom Drag), Sollwert-Stepper, 24-h-SVG-Graph (self-contained, rendert am Dashboard — VTherm-Editor-Only-Bug vermieden), Status-Chips (klick→more-info), Lern-/Shadow-Pille (TPI %/PI °/MPC °), `compact`-Modus, `integration:poise`-gefilterter Editor, `poise-system-card` fürs Hub. Self-contained Lit/TS (nur `lit` Laufzeit-Dep), 13 Pure-Geometrie-Tests (comfort/history/dial). **Bewusst aufgeschoben:** Themes, weitere Sprachen, Mode-/Lock-Buttons, Release-Politur (Screenshots/Forenpost), Superstruct (durch manuelle Validierung ersetzt).
