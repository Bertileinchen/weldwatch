"""T-Stöße der Altbezeichnung (interne Schweißnorm) anhand der Formnummer.

Tabelle vom Anwender festgelegt (11.11.2026) und fest im Code, ändert sich nicht mehr.
Schlüssel: Nahtform der Altbezeichnung (L, VH, VK, YH, YK), Formnummer -> Zusatzinfo für die WPS-Auswahl (Winkelangabe).
Formnummern sind nur zusammen mit der Nahtform eindeutig (Nr. 20 ist bei VH ein T-Stoß, bei V ein Stumpfstoß).
Kehlnähte (L) stehen nur wegen der Winkelangabe in der Tabelle und bekommen nie den Zusatz "T-Stoß".
"""

T_STOSS = "T-Stoß"

_ROHDATEN = {
    "L": {
        "45°": (
            60, 61, 62
        ),
        "135°": (
            67, 101, 102, 103, 111, 112, 113
        ),
    },
    "VH": {
        "T90": (
            20, 21, 22, 23, 30, 31, 32, 40, 41, 50, 51
        ),
        "T135": (
            24, 33, 42, 52, 60, 61, 62, 63, 64
        ),
    },
    "VK": {
        "T90": (
            20, 21, 30, 31, 60, 61, 62, 70, 71, 72, 100, 105, 106, 110, 115, 120, 125, 126, 127, 128,
            140, 145, 146, 147, 148
        ),
    },
    "YH": {
        "T90": (
            20, 21, 22, 23, 30, 31, 32, 40, 41, 50, 51, 125, 126
        ),
        "T135": (
            24, 33, 42, 52, 60, 61, 62, 63, 64
        ),
    },
    "YK": {
        "T90": (
            20, 21, 30, 31, 40, 41, 42, 50, 51, 52, 60, 61, 62, 70, 71, 72, 110, 115, 116, 120, 125,
            130, 135, 136, 137, 138, 150, 155, 156, 157, 158, 175, 176, 180, 181, 182, 190, 191, 192,
            200, 210, 240, 250, 260, 270
        ),
    },
}

TABELLE = {pre: {n: wert for wert, nummern in gruppen.items() for n in nummern}
           for pre, gruppen in _ROHDATEN.items()}


def zusatz(prefix, form):
    """Altbezeichnung (Nahtform, Formnummer) -> (Zusatz für die Nahtart, Zusatzinfo für die WPS).
    Nicht in der Tabelle: ("", "")."""
    try:
        wps = TABELLE.get(prefix, {}).get(int(form))
    except (TypeError, ValueError):
        wps = None
    if wps is None:
        return "", ""
    return ("" if prefix == "L" else T_STOSS), wps
