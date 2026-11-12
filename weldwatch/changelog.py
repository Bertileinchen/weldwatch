"""Änderungsprotokoll für Hilfe > Änderungsprotokoll (neueste Version zuerst)."""

CHANGELOG = [
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
