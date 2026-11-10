# WeldWatch – Schweißnähte aus Zeichnungen in den Prüfplan (Version 0.2)

Liest **Vektor-PDF-Zeichnungen** (zuverlässig) und **Rasterbilder/Scans** (EXPERIMENTELL) und erstellt je Zeichnung
einen Prüfplan im Format der Firmenvorlage (Blatt SNP). Läuft komplett **offline**.

## Benutzung
- **Doppelklick-Variante:** PDF-Datei oder ganzen Ordner auf `Auswerten.bat` ziehen
  (`Auswerten_mit_Kontrolle.bat` erzeugt zusätzlich ein Kontroll-PDF).
- **Kommandozeile:** `python -m weldwatch.main <PDF oder Ordner> -o ausgabe [--kontroll]`
- Ergebnis im Ordner `ausgabe`: `<Name>_Pruefplan.xlsx`, optional `<Name>_Kontrolle.pdf`, `Zusammenfassung.txt`.

## Python-Pfad (portables Python)
Pfad zur `python.exe` einmalig in die Datei `python_pfad.txt` schreiben (eine Zeile). Pakete einmalig installieren:
`python -m pip install -r requirements.txt` (und für die exe zusätzlich `pyinstaller`).

## exe bauen
`bauen.bat` ausführen → Ordner `dist\WeldWatch` (Ordner weitergeben, dort liegt auch die `vorlage`).

## Was ausgefüllt wird
| Spalte | Inhalt |
|---|---|
| A | Zeichnungsnummer aus dem Schriftfeld |
| B | Planquadrat (aus dem Rahmen; Lage der Bezugslinie) |
| C | Nahtart (Kehlnaht, V-, HV-, Y-, HY-, I-Naht; beidseitig: DV, DHV, DY, DHY, sonst Kombination) |
| D | Nahtdicke `s<Maß>` bei Stumpfnähten |
| E | Normbezeichnung wie gezeichnet (`a3`, `HY7 5x30(50)`, `V20`) |
| H | Werkstoffgruppe: keine Klammer = `Gr.1`, `(22)`/`(23)` = `Gr.22/23`, `(1/8)` oder `(1+8)` = `Gr.1 + Gr.8` |
| O | `Nr. n` (gleiche Nummer im Kontroll-PDF), „beidseitig“, Hinweise zum Prüfen |
Alle anderen Spalten (WPS, WPQR, Arbeitsprobe, Klassen, Prüfumfang) bleiben leer. Blatt „Protokoll“ listet alle Funde.

## Ignorierter Bereich
Der Block „allgemeine Angaben“ (Anbindungen I–XI, Kanten ISO 13715, I-Nähte …) wird über seinen Text gefunden und
ignoriert, egal wo er steht. Im Kontroll-PDF ist er grau hinterlegt.

## Rasterbilder / Scans (experimentell)
Seiten ohne Textebene werden automatisch als Raster ausgewertet: Die Anmerkungsebene wird über ihre **Farbe (Türkis)** aus dem Bild geholt,
Linien werden erkannt, Maße und Werkstoffgruppen per **OCR (Tesseract)** gelesen. Voraussetzungen und Grenzen:
- **Tesseract** liegt der per GitHub Actions gebauten exe bereits im Ordner `tesseract\` bei. Selbst bauen/ohne Actions: portable Version in den Ordner `tesseract\` neben das Programm legen
  (`tesseract.exe` + Ordner `tessdata` mit `eng.traineddata`), oder Tesseract installieren. Ohne Tesseract werden nur Symbolformen erkannt,
  keine Maße/Gruppen, und der Block „allgemeine Angaben“ wird nicht ignoriert.
- Funktioniert nur, wenn die Anmerkungen in der Farbe der Anmerkungsebene vorliegen (bei schwarz/weiß-Scans geht es nicht).
- **Erkennungsrate deutlich schlechter als bei Vektor-PDFs** (Probe Seitenwand: gut die Hälfte der Symbole, Maße oft nicht gelesen).
  Alle unsicheren Funde stehen orange im Kontroll-PDF und mit „prüfen“ in der Bemerkung. Nie ungeprüft übernehmen.
- I-Nähte und ähnliche kleine Symbole werden im Raster nicht ausgewertet (zu viele Fehltreffer).

## Grenzen dieser Version
- Vektor-PDFs sind die zuverlässige Hauptfunktion (siehe oben für Raster).
- **Stoßart (T-Stoß …) wird nicht ermittelt**, Spalte bleibt leer.
- Symbole mit gerundeten Flanken (U/J) und weitere Sonderformen werden als „Symbol unbekannt – prüfen“ geführt.
- Ein Kreis an der Bezugslinie wird als Hinweis „Kreis (rundum?)“ vermerkt, nicht ausgewertet.
- Pfeilseite/Gegenseite wird nicht bewertet; beidseitige Symbole stehen in **einer** Zeile mit Vermerk „beidseitig“.
- Interne Bezeichnungen (z. B. `YH5-125`), die als Text in der Zeichnung stehen, werden auf ISO-Schreibweise umgesetzt (`HY5`).
- Ergebnis immer stichprobenartig mit dem Kontroll-PDF prüfen.

## Einstellungen
`weldwatch_config.json` (optional). Z. B. Farbe der Anmerkungsebene (`annot_color`), Ausschlussrand, Format der Zeichnungsnummer.
