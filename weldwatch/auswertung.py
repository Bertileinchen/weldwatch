"""Aus den Funden Tabellenzeilen machen."""
from dataclasses import dataclass, field
from . import exclude, stoss, symbols
from .werkstoff import format_groups

PREFIX = {"V-Naht": "V", "HV-Naht": "HV", "Y-Naht": "Y", "HY-Naht": "HY", "I-Naht": "I"}
DOUBLE = {"V-Naht": "DV-Naht", "HV-Naht": "DHV-Naht", "Y-Naht": "DY-Naht", "HY-Naht": "DHY-Naht",
          "Kehlnaht": "Kehlnaht", "I-Naht": "I-Naht"}

@dataclass
class Entry:
    square: str; x: float; y: float
    art: str; angabe: str; dicke: str; gruppe: str
    bemerkung: list = field(default_factory=list)
    ok: bool = True
    quelle: str = "ISO"
    box: tuple = (0, 0, 0, 0)
    nr: int = 0
    stoss: str = ""      # Zusatz unter der Nahtart (T-Stoß), nie bei Kehlnähten
    wps: str = ""        # Zusatzinfo (Winkelangabe) für die manuelle WPS-Auswahl
    extra: dict = field(default_factory=dict)   # Spaltenbuchstabe -> Text (weitere Spalten der Excel-Vorlage, von Hand ausgefüllt)

def _side_text(kind, d):
    size = d.get("size", "")
    if kind == "Kehlnaht":
        core = size if size[:1] in ("a", "z") else (f"a{size}" if size else "a?")
    elif kind in PREFIX:
        core = f"{PREFIX[kind]}{size}" if size else f"{PREFIX[kind]}?"
    else:
        core = f"?{size}"
    return core.strip()   # abgesetzte Nähte (3x30(50)) bewusst weggelassen - ändern die WPS nicht

def _gleich(sides):
    """Beide Seiten einer Bezugslinie komplett gleich (Nahtart und Maß)? Nur dann eine beidseitige Zeile."""
    (_, x), (_, y) = sides
    kx, ky = x["kind"].rstrip("?"), y["kind"].rstrip("?")
    return kx == ky and _side_text(kx, x) == _side_text(ky, y)

def build_entries(found, pt_labels, grid, ex, cfg):
    out = []
    for f in found:
        cx = (f.x0 + f.x1) / 2
        if exclude.inside(ex, cx, f.y):
            continue
        alle = [(s, f.sides[s]) for s in ("up", "down") if s in f.sides]
        # Beidseitig nur bei komplett gleichen Angaben; unterschiedliche Seiten sind getrennte Nähte (eigene WPS je Naht)
        getrennt = len(alle) == 2 and not _gleich(alle)
        for sides in ([[alle[0]], [alle[1]]] if getrennt else [alle]):
            kinds = [d["kind"] for _, d in sides]
            ok = all(k != "unbekannt" and not k.endswith("?") for k in kinds)
            rem = []
            if len(sides) == 2:
                rem.append("beidseitig")
                art = DOUBLE.get(kinds[0].rstrip("?"), "?") if kinds[0] == kinds[1] else " + ".join(kinds)
                angabe = "\n".join(_side_text(d["kind"].rstrip("?"), d) for _, d in sides)
            else:
                art = kinds[0].rstrip("?") if ok or kinds[0].endswith("?") else "Symbol unbekannt"
                angabe = _side_text(kinds[0].rstrip("?"), sides[0][1])
                if getrennt:
                    rem.append("Symbol oberhalb der Bezugslinie" if sides[0][0] == "up" else "Symbol unterhalb der Bezugslinie")
            if "?" in angabe:
                ok = False
                rem.append("Maß nicht gelesen - prüfen")
            if any(k == "unbekannt" for k in kinds):
                rem.append("Symbol nicht erkannt - prüfen")
            elif any(k.endswith("?") for k in kinds):
                rem.append("Symbol unsicher (evtl. Maßhilfslinie) - prüfen")
            for n in f.notes:
                rem.append(n)
            dicke = ""      # Spalte D ist nur für Materialstärken reserviert, das Nahtmaß steht in der Angabe
            out.append(Entry(grid.square(cx, f.y) if grid else "-", cx, f.y, art, angabe, dicke,
                             format_groups(f.groups, cfg), rem, ok, "ISO",
                             (f.x0, f.y - 22, f.x1, f.y + 22)))
    for p in pt_labels:
        w = p["word"]
        if exclude.inside(ex, w.cx, w.cy):
            continue
        q = p.get("second")
        if q:
            w2 = q["word"]
            art = DOUBLE.get(p["art"], "?") if p["art"] == q["art"] else f"{p['art']} + {q['art']}"
            angabe = f"{p['angabe']}\n{q['angabe']}"
            rem = ["beidseitig", f"interne Bezeichnung {p['pt']} / {q['pt']}"]
            box = (min(w.x0, w2.x0) - 4, w.y0 - 4, max(w.x1, w2.x1) + 4, w2.y1 + 4)
            cx, cy = (w.cx + w2.cx) / 2, (w.cy + w2.cy) / 2
        else:
            art, angabe, rem = p["art"], p["angabe"], [f"interne Bezeichnung {p['pt']}"]
            box = (w.x0 - 4, w.y0 - 4, w.x1 + 4, w.y1 + 4); cx, cy = w.cx, w.cy
        zusatz, wps = stoss.zusatz(p.get("prefix"), p.get("form"))
        if wps:
            wps = "Auswahlhilfe: " + wps
        if art == "Kehlnaht":   # Kehlnähte sind meist T-Stöße und bekommen den Zusatz nie
            zusatz = ""
        out.append(Entry(grid.square(cx, cy) if grid else "-", cx, cy, art, angabe, "",
                         format_groups(None, cfg), rem, True, "Altbezeichnung", box, stoss=zusatz, wps=wps))
    out.sort(key=lambda e: (e.square[0], int(e.square[1:]) if e.square[1:].isdigit() else 0, e.y, e.x))
    for i, e in enumerate(out, 1):
        e.nr = i
    return out
