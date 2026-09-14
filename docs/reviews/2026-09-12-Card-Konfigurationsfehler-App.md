# Befund 2026-09-12: „Konfigurationsfehler" — die Card lädt in der Companion-App nicht

**Status:** Ursache eingegrenzt, Fix in v0.194.1 · **Symptom:** Android-Companion-App zeigt für **jede** Poise-Card „Konfigurationsfehler"; Desktop-Chrome zeigt dieselben Cards auf demselben Dashboard und derselben URL einwandfrei · **Bezug:** ADR-0040 (Card gebündelt & auto-registriert) und dessen Nachtrag 1, ADR-0016 (Attributvertrag)

## 1. Befundlage

| Beobachtung | Quelle |
|---|---|
| 5 von 5 Poise-Cards fallen aus, uniform; die eingebauten Tile-Cards derselben Entitäten darunter rendern | App-Screenshot |
| Dieselbe Ansicht (`/lovelace-test/poise`) auf `http://homeassistant.local:8123` am Desktop: alle 5 Cards korrekt | Desktop-Screenshot |
| `customElements.get("poise-card")` am Desktop `true`, sechs weitere Custom Cards registriert | Live-Probe |
| HA Core **2026.6.2** (nicht 2026.9 — das ist der Supervisor) | `hass.config.version` |
| Andere HACS-Karten funktionieren **in der App** | Betreiber |
| Frontend-Cache der App leeren ändert nichts | Betreiber |
| Registerkarte wechseln half **einmal**; nach App-Neustart nicht mehr | Betreiber |

## 2. Was ausgeschlossen wurde

**Die Cards selbst.** Gleiches Dashboard, gleiche URL, gleiches ausgeliefertes HTML — am Desktop tadellos. Es gibt im Code weder eine User-Agent-Abfrage noch einen Android-Pfad.

**Die Entitäten.** Die Tile-Cards derselben Entitäten stehen im selben App-Screenshot und zeigen Werte.

**Eine veraltete App-Shell mit 404 (meine eigene Hypothese, widerlegt).** Gemessen hatte ich: Die Index-Antwort trägt weder `Cache-Control` noch ETag noch `Last-Modified`, ist also heuristisch cachebar; `/poise/poise-card-0.194.0.js` liefert 200, `/poise/poise-card-0.193.1.js` **404**. Eine gecachte Shell hätte also auf einen toten Pfad gezeigt. Der Test des Betreibers — Frontend-Cache leeren — hat die Hypothese erledigt: Das Bild blieb. Der 404-Fallstrick ist trotzdem real und bleibt unter §6 als eigener Punkt stehen.

**Der fehlende `hass`-Guard in `render()`.** Real (§5), aber nicht dieses Symptom: „Konfigurationsfehler" ist HAs `hui-error-card`, die bei nicht definiertem Custom Element oder werfendem `setConfig` erscheint. Ein `TypeError` innerhalb von `render()` landet als unbehandelter Fehler in der Konsole und hinterlässt eine halb gerenderte Karte.

## 3. Der Mechanismus

Poise lud die Card über `add_extra_js_url`, also die **Modul-URL-Liste des Frontends**. Diese Liste wird in die ausgelieferte App-Shell gebacken, und ihre Importe werden von der Kartenerzeugung **nicht abgewartet**. HACS-Karten dagegen stehen in der **Lovelace-Ressourcen-Collection**, die das Lovelace-Panel zur Laufzeit holt und vor dem Kartenbau auflöst.

Damit erklären sich alle sieben Zeilen aus §1 ohne Rest:

* **Desktop schnell, Telefon langsam.** Kein Zufallsrennen, sondern ein systematischer Timing-Unterschied: Der Import gewinnt am Desktop jedes Mal und verliert auf dem Telefon jedes Mal.
* **Nur die zuerst gebaute Ansicht ist betroffen** — danach ist das Modul da.
* **Registerkarte wechseln half einmal, dann nicht mehr.** Beim ersten Versuch startete die App auf einer anderen Ansicht, die Poise-Ansicht wurde also erstmals und spät gebaut — Cards da. Nach dem Neustart stellt die App die zuletzt besuchte Ansicht wieder her, baut „Poise" also zuerst; und weil das Frontend gerenderte Ansichten im Speicher hält, liefert das Zurückwechseln die bereits kaputte Ansicht statt einer neuen.
* **Cache leeren hilft nicht**, weil nichts Veraltetes im Spiel ist.
* **HACS-Karten funktionieren**, weil ihr Ladeweg abgewartet wird.

## 4. Die Entscheidung

**Umstellung auf die Lovelace-Ressourcen-Collection, genau ein Ladeweg.** Das ist keine Neuerfindung, sondern die **Rückkehr zur ursprünglichen Entscheidung von ADR-0040 §5** — dort stand `lovelace.resources.async_create_item` mit Storage-Mode-Gate, YAML-Fallback und WS-Versionscheck. Nachtrag 1 hat das in v0.49/0.50 auf `add_extra_js_url` umgestellt, weil die `.loaded`/`.mode`-Erkennung damals fehlschlug und die Card nicht im Picker landete. Dieser Tausch ist jetzt sichtbar: Ein Startreihenfolge-Problem wurde gegen ein Ladereihenfolge-Rennen eingetauscht, und das zweite ist teurer, weil es nicht beim Entwickler auffällt, sondern beim Nutzer auf dem langsameren Gerät.

Das Startreihenfolge-Problem wird diesmal behandelt statt umgangen: auf `EVENT_HOMEASSISTANT_STARTED` warten, `resources.loaded` pollen (5 s, bis zu zwölf Versuche), `.mode` sowohl am Dataclass als auch am Legacy-Dict lesen. Erst wenn das alles nicht trägt — YAML-Modus, unbekannte API, Ausnahme — bleibt `add_extra_js_url` als **Fallback** mit WARNING im Log. Genau ein Weg, nie beide.

**Der versionsgestempelte Pfad bleibt.** Nachtrag 2 ist davon unberührt: Der Service-Worker ignoriert Query-Strings, also gehört die Version in den Pfad. Über die Ressourcen-Collection entsteht dabei der 404-Fallstrick aus §2 gar nicht erst, weil die Collection Live-Daten sind und bei jedem Upgrade hier neu geschrieben wird.

**Abgleich mit der Praxis.** Die offiziellen HA-Developer-Docs beschreiben ausschließlich den Ressourcen-Weg; `add_extra_js_url`/`extra_module_url` kommen dort nicht vor. Der einschlägige Community-Developer-Guide zu integrationsgebündelten Karten empfiehlt Statik-Pfad **plus** Ressourcen-Collection, nennt das Warten auf `resources.loaded` samt Retry, das Storage-Mode-Gate — und hält ausdrücklich fest, dass `?v=` allein nicht reicht und dass Desktop-Hard-Refresh das Problem maskiert, während es in den Companion-Apps bestehen bleibt.

## 5. Zweiter Befund, unabhängig behoben

`poise-card.ts` und `poise-system-card.ts` lasen in `render()` `this.hass.states[id]`, obwohl die Zeile darüber `this.hass?.locale` schreibt — der Guard war also bekannt und nur nicht zu Ende geführt. `_setpoint()` trägt ihn seit M12 mit Kommentar, beide Editoren hatten ihn immer. Nachgezogen in v0.194.1.

## 6. Offene Punkte

1. **Der 404 auf alte gestempelte Pfade bleibt bestehen.** Über die Ressourcen-Collection ist er nicht mehr erreichbar, aber er ist eine scharfe Kante: Wer eine Ressource von Hand einträgt und Poise aktualisiert, zeigt danach auf einen toten Pfad. Eine Route, die jede `/poise/poise-card-*.js` auf die aktuelle Datei abbildet, würde das entschärfen — nicht in v0.194.1 gebaut, weil der Fix ohne sie auskommt.
2. **Keine Deregistrierung bei Deinstallation.** Die Registrierung sitzt in `async_setup` und hat keinen Gegenhaken; wird Poise entfernt, bleibt ein Ressourceneintrag auf einen 404 zurück. Dieselbe Klasse wie die verwaisten Repair-Issues aus ADR-0072 N1.2, aber ohne zuverlässigen Auslöser.
3. **Kein DOM-/Browser-Lifecycle-Test.** Die Card-Tests sind reine Logiktests; „Element erzeugen → `setConfig` → rendern ohne `hass` → darf nicht werfen" ist weiterhin nur durch Codelektüre abgesichert.
4. **Die zitierten HA-Frontend-Issues des externen Reviews konnten nicht verifiziert werden** (keine Nummern angegeben). Gefunden wurde ein verwandtes offenes Core-Issue (#159553, Cast-Empfänger, „Configuration error" bei Custom Cards seit 2025.12.x). Der hier beschriebene Mechanismus steht unabhängig davon.
