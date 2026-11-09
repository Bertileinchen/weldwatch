"""Einstellungen. Alles Wesentliche kann in weldwatch_config.json überschrieben werden."""
import json, os

DEFAULTS = {
    # Farbe der Anmerkungs-Ebene (Maße, Schweißsymbole) im CAD-Export: RGB 0..1
    "annot_color": [0.0, 0.502, 0.502],
    "annot_color_tol": 0.06,
    # Bezugslinie
    "ref_min_len": 18.0,        # pt, kürzere Linien sind keine Bezugslinien
    "dash_offset": 2.4,         # pt, Abstand Strichlinie zur Bezugslinie
    "dash_offset_tol": 0.5,
    "dash_len_min": 4.0, "dash_len_max": 14.0,
    "tol": 0.6,                 # pt, Geometrie-Toleranz
    "symbol_max_h": 26.0,       # pt, max. Symbolhöhe
    # Text
    "text_band": 18.0,          # pt, Höhe des Textbandes über/unter der Bezugslinie
    # Bereiche, die ignoriert werden (allgemeine Angaben im Schriftkopf)
    "exclude_anchors": ["Anbindung", "Connection", "Kanten", "Edges", "Beispiel", "Example",
                        "sämtliche", "Ecken", "Rändern", "I-Nähte", "I-seam", "Schwingrahmen",
                        "Schweißnahtvorbereitung", "discontinuous"],
    "exclude_margin": [60.0, 12.0, 140.0, 60.0],   # links, oben, rechts, unten um die Anker (pt)
    "exclude_min_anchors": 6,
    # Zeichnungsnummer im Schriftfeld (regulärer Ausdruck); sonst Dateiname
    "drawing_no_regex": r"^[A-Z]{1,3}\d{3}-\d{5}-\d$",
    # Werkstoffgruppen
    "alu_text": "Gr.22/23",
    "gr_alu": [22, 23],
    "default_group": 1,
    # Rasterbilder
    "raster_dpi": 200,
    "raster_tol": 2.8,
    "raster_symbol_min_len": 11.0,   # pt: kürzere Striche sind Ziffern/Rauschen
}

def load(path=None):
    cfg = dict(DEFAULTS)
    path = path or "weldwatch_config.json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg
