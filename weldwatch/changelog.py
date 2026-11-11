"""Änderungsprotokoll für Hilfe > Änderungsprotokoll (neueste Version zuerst)."""

CHANGELOG = [
    ("0.8.1", "11.11.2026", [
        "Spalte D der Excel-Liste enthält jetzt die Blechstärken beider Nahtpartner ('5mm / 10mm')",
        "Das Nahtmaß (s20, a5) steht nicht mehr in Spalte D, es ist schon in der Nahtangabe; das Feld 'Dicke' entfällt",
    ]),
    ("0.8.0", "11.11.2026", [
        "Blechstärken beider Nahtpartner je Naht ('5mm / 10mm'): Teil A und Teil B im Reiter 'Naht' wählen, Dicke kommt als Vorschlag",
        "Datei > STP-Datei laden: Teile und Dicke werden aus dem 3D-Modell berechnet (unsichere Werte mit '?' markiert, von Hand änderbar)",
        "Datei > Stücklisten (PDF) laden: Positionen der Zeichnung und Teilenummern; ohne STP bleibt nur die Eingabe von Hand",
        "Blechstärken werden in die Excel-Liste geschrieben; Rückfrage beim Export, wenn Blechstärken fehlen",
    ]),
    ("0.7.0", "11.11.2026", [
        "Neue Zeichnungen werden nur aufgenommen, der Scan startet nicht mehr automatisch",
        "Zwei Scan-Knöpfe: 'Scan: aktuelle Zeichnung' und 'Scan: alle Zeichnungen'",
        "Laufender Scan lässt sich abbrechen (fertige Zeichnungen bleiben erhalten)",
        "Nicht gescannte Zeichnungen sind markiert; Excel erst nach Scan und Prüfung aller Zeichnungen",
        "Reiter 'Weitere Excel-Spalten' heißt jetzt 'Prüfangaben'",
    ]),
    ("0.6.0", "11.11.2026", [
        "Güteklasse/Prüfklasse als Auswahllisten, Prüfumfang UT/MT/VT folgt aus der Prüfklasse (Standard CP C2 / CT 3); Angabe ohne Umbruch (100%)",
        "Bemerkung in der Excel-Liste: jeder Vermerk in eigener Zeile",
        "Nahtliste filterbar (Quadrat, Nahtart, Angabe, Gruppe, Status); die Knöpfe '→ alle' und 'Alle angezeigten bestätigen' wirken nur auf die angezeigten Nähte",
        "Zeichnungen lassen sich jederzeit hinzufügen (PDF oder Ordner) und aus dem Projekt entfernen; Auswahlliste aller Zeichnungen oben",
        "Nummern der Nähte bleiben stabil: von Hand gesetzte Nähte bekommen die nächste Nummer, nichts wird neu nummeriert",
        "WPS-Zusatzinfo beginnt mit 'Auswahlhilfe: '",
        "'Neue Naht setzen' sieht jetzt wie ein Knopf aus, Eingabefeld Zeichnungsangabe kleiner",
        "Hilfe neu gegliedert, Versionsnummer in der Statusleiste, Änderungsprotokoll",
    ]),
    ("0.5.2", "11.11.2026", [
        "Erstes Speichern mit 'Speichern unter', Frage nach Kopie der Zeichnungen ins Projekt; danach wird nur überspeichert",
        "Zeichnungen frei umschaltbar (Knöpfe, Reiter, Strg+Bild auf/ab)",
        "Eingabefelder für alle weiteren Excel-Spalten (Reiter 'Prüfangaben')",
        "Excel-Export mit optionalen Prüf-PDFs im Unterordner",
    ]),
    ("0.5.1", "10.11.2026", [
        "Beidseitig nur bei komplett gleichen Angaben (auch ISO-Symbole)",
        "Zeilenhöhe der Nahtliste an die Schrift gekoppelt",
        "T-Stoß-Zusatz und Winkelangabe für Altbezeichnungen",
    ]),
    ("0.5.0", "10.11.2026", [
        "Prüf-Fenster mit Bearbeiten, Löschen und manuellem Setzen von Nähten",
        "Projektdatei (.wwp), Excel-Liste erst nach vollständiger Prüfung",
    ]),
]
