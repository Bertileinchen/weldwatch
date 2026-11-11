"""Schweißnahtgüteklasse (CP) / Schweißnahtprüfklasse (CT) und daraus der Prüfumfang UT, MT, VT (Tabelle vom Anwender, 11.11.2026).
Die Prozentwerte hängen an der Prüfklasse (CT); die Güteklasse schlägt die zugehörige Prüfklasse vor.
Standard für alle Nähte: CP C2 / CT 3."""
import re

STANDARD_CP = "CP C2"
STANDARD_CT = "CT 3"

# Güteklasse -> Prüfklasse (Reihenfolge wie in der Tabelle)
CP_ZU_CT = {"CP A": "CT 1", "CP B2": "CT 2", "CP C2": "CT 3", "CP B1": "CT 2", "CP C3": "CT 4", "CP C1": "CT 2", "CP D": "CT 4"}
CP_LISTE = list(CP_ZU_CT)
# Prüfklasse -> (UT, MT, VT) als Text in der Excel-Liste
CT_ZU_UMFANG = {"CT 1": ("100 %", "100 %", "100 %"), "CT 2": ("10 %", "10 %", "100 %"),
                "CT 3": ("-", "-", "100 %"), "CT 4": ("-", "-", "100 %")}
CT_LISTE = list(CT_ZU_UMFANG)

_ROLLEN = (("cp", r"g[üu]e?teklasse"), ("ct", r"pr[üu]e?fklasse"), ("ut", r"\bUT\b|volumetr"),
           ("mt", r"\bMT\b|oberfl"), ("vt", r"\bVT\b|sichtpr"))


def rollen(labels):
    """{Spaltenbuchstabe: 'cp'|'ct'|'ut'|'mt'|'vt'} anhand der Überschriften der Vorlage."""
    out = {}
    for b, t in labels.items():
        for rolle, muster in _ROLLEN:
            if rolle not in out.values() and re.search(muster, t, re.I):
                out[b] = rolle
                break
    return out


def umfang(ct):
    """(UT, MT, VT) zur Prüfklasse; unbekannte Prüfklasse -> leere Texte."""
    return CT_ZU_UMFANG.get((ct or "").strip(), ("", "", ""))
