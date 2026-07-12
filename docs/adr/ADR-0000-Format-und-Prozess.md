# ADR-0000: ADR-Format und -Prozess

**Status:** Gültig · **Wirkung:** Gültig · **Datum:** 2026-06-18 · **Bezug:** Festlegung E27 aus `Offene_Festlegungen_und_Verifizierung.md`

## Kontext
Das Designpaket (Best-of-Konzept, Charta, Konflikt-Analyse, Strukturplan, Festlegungs-Register) trifft viele Architektur- und Algorithmik-Entscheidungen. Es fehlt ein einheitliches, nachvollziehbares Gefäß, das **je Entscheidung** Kontext, Optionen, Wahl, Begründung, Konsequenzen und **Code-Beleg** festhält und unveränderlich dokumentiert. Das ist Grundsatz G3/G27 (Auditierbarkeit, Determinismus) auf Projektebene.

## Entscheidung
Jede nicht-triviale Architektur-/Algorithmik-Entscheidung wird als **Architecture Decision Record (ADR)** im Ordner `docs/adr/` festgehalten, fortlaufend nummeriert (`ADR-NNNN-kurztitel.md`).

**Pflichtfelder je ADR:**
1. **Status** — `vorgeschlagen` → `akzeptiert` → ggf. `abgelöst durch ADR-XXXX` / `zurückgezogen` (Umsetzungsstufen s. `docs/adr/README.md`)
1a. **Wirkung** — die **Aktuierungswirkung** des ADR im laufenden System, **orthogonal zum Status** (der Status misst *wie weit umgesetzt*, die Wirkung misst *ob und wie es den Aktor bewegt*). Steht auf der Status-Zeile direkt hinter dem Status-Token (`**Status:** … · **Wirkung:** <Token> · **Datum:** …`). Genau **ein** Token aus:
   - **Live-A** — aktuiert im Live-Schreibpfad (bewegt den Aktor/Sollwert echt).
   - **Live-D** — läuft in jedem Tick, aber rein **diagnostisch** (berechnet/exponiert, kein Write).
   - **Shadow** — berechnet, schreibt **nie** (gated Schatten-Pfad, ADR-0026-Politik).
   - **teilw.** — teilweise verdrahtet (einzelne Stufen live, andere Shadow/offen).
   - **Harness** — nur Test-/Harness-Pfad, nicht im Produktions-Tick.
   - **Doku** — reine Dokumentations-/Abgrenzungs-/Entscheidungs-Entscheidung ohne Laufzeit-Code.
   - **Gültig** — Meta-/Prozess-Record (kein Aktuierungsbezug, z. B. dieser ADR).
   - **n.a.** — nicht anwendbar / noch nicht gebaut.
2. **Datum** + **Bezug** (E-/K-Punkte, Quelldokumente)
3. **Kontext** — Problem, das entschieden werden muss
4. **Entscheidungstreiber** — die maßgeblichen Kriterien
5. **Betrachtete Optionen** — mindestens zwei, mit Quelle (Wettbewerber/eigener Code)
6. **Entscheidung** — die gewählte Option, präzise
7. **Begründung** — warum, gegen die Alternativen
8. **Konsequenzen** — positiv **und** negativ/Kosten
9. **Verifizierung** — Code-Belege (Datei:Funktion), Tests, die die Wahl absichern
10. **Compliance** — Lizenz-/Allgemeingültigkeits-Check (G29/G30): Methode nachimplementiert, kein Code-Copy; keine gerätespezifischen Sonderwege im Kern
11. **Verknüpfungen** — abhängige/abgelöste ADRs, offene Folge-Entscheidungen

## Prozess
- ADRs sind nach `akzeptiert` **unveränderlich**; eine geänderte Entscheidung entsteht als **neuer** ADR, der den alten *ablöst* (Status-Update nur um den Ablöse-Verweis).
- Jeder **P0**-Punkt aus dem Festlegungs-Register soll vor Implementierungsbeginn einen `akzeptiert`-ADR haben.
- Code-belegte Entscheidungen zitieren die konkrete Datei/Funktion der Verifizierung (Runde 1/2).
- ADRs sind theoretische Festlegungen für dieses Konzept — keine Aussage über die realen, publizierten Produkte.

## Konsequenzen
**Positiv:** nachvollziehbare Entscheidungshistorie; neue Mitwirkende verstehen *warum*; Verhindert stilles Re-Litigieren entschiedener Punkte; erfüllt die Auditierbarkeits-Charta.
**Negativ/Kosten:** Disziplin nötig; ADRs müssen gepflegt (abgelöst) werden, sonst veralten sie wie jedes Dokument.

## Verknüpfungen
Index: `docs/adr/README.md` (alleiniger, maßgeblicher Ablageort). Erste akzeptierte Records: ADR-0001…0004. Offene P0-Punkte ohne ADR: E1, E2, E4, E6, E7/E8, E10/E11, E17, E19, E22/E23 (künftige ADRs).
