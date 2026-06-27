# ADR-0019: KNX-/Norm-Expose-Schnittstelle

**Status:** Vorgeschlagen · **Datum:** 2026-06-18 · **Bezug:** E15, G28, G29 · **Verifizierung:** Code-Review (kein Feld-Vorbild — Alleinstellung)

## Kontext
KNX-Expose ist Teil des Norm-/Gewerbe-Moats (EN ISO 52120-1 Klasse B, VDI 3813) und im gesamten Wettbewerbsfeld konkurrenzlos. Offen: welche Objekte in welche Richtung exponiert werden und wie das die Schichtarchitektur berührt.

## Entscheidungstreiber
Gewerbe-/GA-Anbindung ohne den Laien-Pfad zu belasten; klare Richtung (Status vs. Steuerung); generisch (Gruppenadressen konfigurierbar); kein Sonderweg im Regelkern.

## Befund
- **Kein Wettbewerber exponiert KNX** (alle `iot_class: local_*`, reine HA-Entities). Das ist reine Differenzierung, kein Vorbild — die Schnittstelle ist Eigenentwicklung auf Basis der HA-KNX-Integration (Gruppenadressen).

## Entscheidung
1. **KNX-Expose ist ein optionales Modul** (`integrations/knx_expose`), nur geladen, wenn konfiguriert — Progressive Disclosure (G22), für Laien unsichtbar.
2. **Ausgehend (Status, Standardrichtung):** bindender Sollwert, Operativtemperatur, T_rm, Komfortband (unten/oben), Heizbedarf/Leistung, Schimmel-Mindesttemperatur, Konfidenz/Reife — je auf eine konfigurierbare **Gruppenadresse**. Lesbar für die Gebäudeautomation, ohne Rückwirkung auf die Regelung.
3. **Eingehend (optional):** externer Sollwert/Präsenz/Fenster aus KNX werden als **`Reading`** in die Degradationsleiter (ADR-0005/0012) eingespeist — mit Quelle-Tag `knx`, denselben Plausibilitäts-/Konfidenzregeln wie jeder Sensor. Sie kommandieren nicht direkt, sondern durchlaufen Arbitrierung (ADR-0013/Strukturplan-Ebene 7).
4. **Generisch:** alle Gruppenadressen und Datentypen (DPT) sind Konfiguration; keine geräte-/herstellerspezifischen Sonderwege im Kern (G29). Normbezug (EN ISO 52120-1 Klasse B / VDI 3813) ist Framing, kein Sonderpfad.

## Begründung
Als optionales, richtungsklares Status-Modul fügt sich KNX-Expose ohne Eingriff in den Regelkern ein: ausgehende Werte sind reine Projektionen vorhandener Größen, eingehende werden zu gewöhnlichen `Reading`s — beides nutzt die bestehende Schichtarchitektur. So bleibt der Moat erhalten, ohne den Zero-Question-Pfad (ADR-0008) zu belasten.

## Konsequenzen
**Positiv:** Gewerbe-/GA-Anbindung als echtes Alleinstellungsmerkmal; keine Belastung des Laien-Onboardings; eingehende KNX-Werte erben Robustheit/Degradation der Pipeline.
**Negativ/Kosten:** zusätzliche optionale Abhängigkeit von der HA-KNX-Integration; DPT-/Gruppenadress-Konfiguration ist Expertenstoff (bewusst hinter Progressive Disclosure); Pflege der Expose-Liste bei neuen Diagnose-Größen.

## Compliance
Eigenentwicklung; generische Gruppenadressen; kein Code-Copy (es gibt keins). Vollständig lokal (KNX ist Feldbus, keine Cloud).

## Verknüpfungen
Ausgehende Werte = Projektion der Diagnose-/Comfort-Größen (ADR-0016/0009). Eingehende = `Reading` der Degradationsleiter (ADR-0005/0012). Bleibt P2/optional.
