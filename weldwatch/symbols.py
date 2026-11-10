"""Erkennung von Schweißsymbolen nach ISO 2553 in der Vektorgeometrie."""
import re, math
from dataclasses import dataclass, field
from .werkstoff import parse_group_token
from .vector import Seg

SIZE = re.compile(r"^(a|z|s)?\d+([.,]\d+)?$")
SPEC = re.compile(r"^(\d*|n)[xX]\d+\(\d+\)$")

@dataclass
class Found:
    x0: float; x1: float; y: float              # Bezugslinie
    sides: dict = field(default_factory=dict)   # 'up'/'down' -> dict(kind, size, spec, segs)
    groups: list = field(default_factory=list)
    words: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    has_dash: bool = False
    dash_side: str = ""

def _near(a, b, t): return abs(a - b) <= t

def find_reference_lines(segs, cfg):
    tol = cfg["tol"]
    H = [s for s in segs if _near(s.y0, s.y1, 0.05)]
    longs = [s for s in H if s.length >= cfg["ref_min_len"]]
    refs = []
    for s in longs:
        x0, x1 = sorted((s.x0, s.x1)); y = s.y0
        # Teilstück einer längeren Linie auf gleicher Höhe (z. B. Dreiecksbasis) überspringen
        if any(o is not s and _near(o.y0, y, 0.05) and min(o.x0, o.x1) <= x0 + tol and max(o.x0, o.x1) >= x1 - tol
               and o.length > s.length + 0.5 for o in longs):
            continue
        refs.append((x0, x1, y))
    refs = sorted(set((round(a, 2), round(b, 2), round(c, 2)) for a, b, c in refs))
    return refs, H

def _dashes(H, x0, x1, y, cfg):
    res = {}
    for side, sgn in (("down", 1), ("up", -1)):
        n = [t for t in H if _near(t.y0, y + sgn * cfg["dash_offset"], cfg["dash_offset_tol"])
             and min(t.x0, t.x1) >= x0 - cfg["tol"] and max(t.x0, t.x1) <= x1 + cfg["tol"]
             and cfg["dash_len_min"] < t.length < cfg["dash_len_max"]]
        if len(n) >= 2:
            res[side] = len(n)
    return res

def _component(start, pool, tol):
    comp, todo = list(start), list(start)
    rest = [p for p in pool if p not in comp]
    while todo:
        c = todo.pop()
        for p in rest[:]:
            if any(math.hypot(px - qx, py - qy) < tol
                   for px, py in ((p.x0, p.y0), (p.x1, p.y1)) for qx, qy in ((c.x0, c.y0), (c.x1, c.y1))) \
               or _on_segment(p, c, tol) or _on_segment(c, p, tol):
                comp.append(p); todo.append(p); rest.remove(p)
    return comp

def _on_segment(p, c, tol):
    """liegt ein Endpunkt von p auf Segment c?"""
    for px, py in ((p.x0, p.y0), (p.x1, p.y1)):
        dx, dy = c.x1 - c.x0, c.y1 - c.y0
        L2 = dx * dx + dy * dy
        if L2 == 0: continue
        t = ((px - c.x0) * dx + (py - c.y0) * dy) / L2
        if -0.02 <= t <= 1.02:
            qx, qy = c.x0 + t * dx, c.y0 + t * dy
            if math.hypot(px - qx, py - qy) < tol:
                return True
    return False

def classify(comp, y, sgn, tol, base=(), dash_off=None):
    """Symbolart aus den Linien einer Komponente (Koordinate v = Höhe über der Bezugslinie)."""
    def v(py): return (py - y) * sgn
    base = list(base)
    vert = [s for s in comp if _near(s.x0, s.x1, 0.05)]
    diag = [s for s in comp if not _near(s.x0, s.x1, 0.05) and not _near(s.y0, s.y1, 0.05)]
    others = [s for s in comp if s not in vert and s not in diag]
    comp = comp + base
    if others:
        return "unbekannt"
    if base and len(vert) == 1 and len(diag) == 1:
        return "Kehlnaht"
    if base:
        return "unbekannt"
    if len(vert) == 2 and not diag:
        gap = abs(vert[0].x0 - vert[1].x0)
        if max(vert[0].length, vert[1].length) <= 14 and 1.5 <= gap <= 7:
            return "I-Naht"
        return "I-Naht?"
    if len(vert) == 1 and len(diag) == 1:
        vs, ds = vert[0], diag[0]
        # Dreieck ohne eigene Basislinie (Basis liegt auf der Bezugslinie): Spitzen treffen sich oben
        vtop = max(((vs.x0, vs.y0), (vs.x1, vs.y1)), key=lambda q: v(q[1]))
        dtop = max(((ds.x0, ds.y0), (ds.x1, ds.y1)), key=lambda q: v(q[1]))
        dlow = min(((ds.x0, ds.y0), (ds.x1, ds.y1)), key=lambda q: v(q[1]))
        vlen = vs.length
        base_ok = abs(v(dlow[1])) < tol * 2 or (dash_off is not None and abs(v(dlow[1]) - dash_off) < tol * 2)
        if (math.hypot(vtop[0] - dtop[0], vtop[1] - dtop[1]) < tol * 2 and base_ok
                and abs(abs(dlow[0] - vs.x0) - vlen) < max(2 * tol, 0.3 * vlen)):
            return "Kehlnaht"
        foot_v = min(vs.y0, vs.y1, key=lambda q: abs(v(q)))
        low = min(((ds.x0, ds.y0), (ds.x1, ds.y1)), key=lambda p: v(p[1]))
        hv = v(low[1]); hv_total = abs(vs.y0 - vs.y1)
        if abs(hv) < tol and abs(low[0] - vs.x0) < tol * 2:
            return "HV-Naht"
        if abs(low[0] - vs.x0) < tol * 2 and tol < hv < hv_total - tol:
            return "HY-Naht"
        return "unbekannt"
    if not vert and len(diag) == 2:
        lows = [min(((d.x0, d.y0), (d.x1, d.y1)), key=lambda p: v(p[1])) for d in diag]
        if all(abs(v(l[1])) < tol for l in lows) and abs(lows[0][0] - lows[1][0]) < tol * 2:
            return "V-Naht"
        return "unbekannt"
    if len(vert) == 1 and len(diag) == 2:
        vs = vert[0]
        top = max(((vs.x0, vs.y0), (vs.x1, vs.y1)), key=lambda p: v(p[1]))
        lows = [min(((d.x0, d.y0), (d.x1, d.y1)), key=lambda p: v(p[1])) for d in diag]
        if all(abs(l[0] - top[0]) < tol * 2 and abs(l[1] - top[1]) < tol * 2 for l in lows):
            return "Y-Naht"
    return "unbekannt"

def find_symbols(segs, words, cfg, word_provider=None):
    tol = cfg["tol"]
    refs, H = find_reference_lines(segs, cfg)
    out = []
    for (x0, x1, y) in refs:
        dash = _dashes(H, x0, x1, y, cfg)
        f = Found(x0, x1, y, has_dash=bool(dash), dash_side=(list(dash)[0] if dash else ""))
        # Texte zu dieser Bezugslinie bestimmen (bei Raster: OCR) und Textstriche aus der Geometrie nehmen
        f.words = word_provider(f) if word_provider else words
        boxes = [(w.x0 - 1.2, w.y0 - 1.2, w.x1 + 1.2, w.y1 + 1.2) for w in f.words
                 if re.fullmatch(r"[\d()xXazs/+.,n]+", w.text)] if word_provider else []
        def _txt(sg):
            return any(b[0] <= sg.x0 <= b[2] and b[0] <= sg.x1 <= b[2] and b[1] <= sg.y0 <= b[3] and b[1] <= sg.y1 <= b[3]
                       for b in boxes)
        # Segmente, die innerhalb der Linie (nicht an den Enden) auf ihr ansetzen
        minlen = 0 if cfg.get("pattern_mode") else cfg.get("symbol_min_len", 0)
        near = [s for s in segs if minlen <= s.length < cfg["symbol_max_h"] * 1.6
                and x0 - 2 <= min(s.x0, s.x1) and max(s.x0, s.x1) <= x1 + 2
                and any(abs(py - y) <= cfg["symbol_max_h"] for py in (s.y0, s.y1))
                and (not _txt(s) or cfg.get("pattern_mode"))]
        # Linien, die die Bezugslinie kreuzen (z. B. senkrechter Strich bei beidseitigen Symbolen), teilen
        split = []
        for sg in near:
            lo, hi = min(sg.y0, sg.y1), max(sg.y0, sg.y1)
            if lo < y - 2 * tol and hi > y + 2 * tol and abs(sg.y1 - sg.y0) > 1e-6:
                t = (y - sg.y0) / (sg.y1 - sg.y0)
                xm = sg.x0 + t * (sg.x1 - sg.x0)
                split += [Seg(sg.x0, sg.y0, xm, y), Seg(xm, y, sg.x1, sg.y1)]
            else:
                split.append(sg)
        near = split
        if cfg.get("pattern_mode"):   # zerrissene Schrägstriche erst verbinden, dann kurze Striche (Ziffern/Rauschen) verwerfen
            near = [q for q in _chain_diags(near) if q.length >= cfg.get("symbol_min_len", 0)
                    and not (_txt(q) and q.length < 14.5)]   # Textstriche (Ziffernhöhe ~13 pt) raus, lange Symbolstriche bleiben
        def attempt(side, sgn, yy, on_dash):
            """Symbol einer Seite auswerten; yy = Grundlinie (Bezugslinie oder - bei Strichlinienseite - die Strichlinie)."""
            side_segs = [s for s in near if all((py - yy) * sgn >= -tol for py in (s.y0, s.y1))
                         and (on_dash or not (_near(s.y0, s.y1, 0.05) and abs(s.y0 - yy) > tol
                                  and abs(abs(s.y0 - yy) - cfg["dash_offset"]) < cfg["dash_offset_tol"]))]
            if not on_dash:   # Strichlinie (Kennzeichnungslinie) nicht als Symbol zählen
                side_segs = [s for s in side_segs if not (_near(s.y0, s.y1, 0.05) and
                             abs(abs(s.y0 - yy) - cfg["dash_offset"]) < cfg["dash_offset_tol"])]
            tiny = [s for s in side_segs if s.length < 3.6]
            if len(tiny) >= 3 and "umlaufend" not in f.notes:
                f.notes.append("umlaufend")
            side_segs = [s for s in side_segs if s.length >= 3.6]
            on_line = [s for s in side_segs if _near(s.y0, s.y1, 0.05) and abs(s.y0 - yy) < tol]
            vd = [s for s in side_segs if s not in on_line]
            start = [s for s in vd if any(abs(py - yy) < tol and x0 + 1 < px < x1 - 1
                                          for px, py in ((s.x0, s.y0), (s.x1, s.y1)))]
            if not start:
                return None
            if cfg.get("pattern_mode"):
                kind, comp = classify_patterns(vd, yy, sgn, tol, x0, x1)
                if kind is None:
                    return None
                return dict(kind=kind, segs=comp,
                            xmin=min(min(q.x0, q.x1) for q in comp), xmax=max(max(q.x0, q.x1) for q in comp))
            comp = _component(start, vd, tol)
            feet = [(px, py) for s in comp for px, py in ((s.x0, s.y0), (s.x1, s.y1)) if abs(py - yy) < tol]
            base = [s for s in on_line if s.length <= cfg["symbol_max_h"]
                    and sum(any(math.hypot(px - fx, py - fy) < tol for fx, fy in feet)
                            for px, py in ((s.x0, s.y0), (s.x1, s.y1))) >= 1
                    and any(abs(s.x0 - fx) < tol or abs(s.x1 - fx) < tol for fx, fy in feet)]
            # Dreiecksbasis: beide Enden an Fußpunkten
            base = [b for b in base if sum(any(math.hypot(px - fx, py - fy) < tol for fx, fy in feet)
                                           for px, py in ((b.x0, b.y0), (b.x1, b.y1))) == 2]
            kind = classify(comp, yy, sgn, tol, base, cfg.get("dash_offset"))
            comp = comp + base
            return dict(kind=kind, segs=comp,
                        xmin=min(min(s.x0, s.x1) for s in comp), xmax=max(max(s.x0, s.x1) for s in comp))
        for side, sgn in (("up", -1), ("down", 1)):
            d = attempt(side, sgn, y, False)
            if d is None and dash.get(side):
                # CAD zeichnet das Symbol auf der Strichlinienseite manchmal ab der Strichlinie statt ab der Bezugslinie
                ys = [t.y0 for t in H if _near(t.y0, y + sgn * cfg["dash_offset"], cfg["dash_offset_tol"])
                      and min(t.x0, t.x1) >= x0 - tol and max(t.x0, t.x1) <= x1 + tol]
                if ys:
                    d = attempt(side, sgn, sorted(ys)[len(ys) // 2], True)
            if d is not None:
                f.sides[side] = d
        if not f.sides:
            continue
        if cfg.get("ring_fn") and any(cfg["ring_fn"](ex, y) for ex in (x0, x1)) and "umlaufend" not in f.notes:
            f.notes.append("umlaufend")     # Kreis am Linienende (Rundumnaht)
        if cfg.get("pattern_mode"):
            lead = [q for q in segs if q.length >= 8 and abs(q.x0 - q.x1) > 0.05 and abs(q.y0 - q.y1) > 0.05
                    and any(math.hypot(px - ex, py - y) <= (16.0 if "umlaufend" in f.notes else 3 * tol)
                            for px, py in ((q.x0, q.y0), (q.x1, q.y1)) for ex in (x0, x1))]   # Kreis am Linienende schiebt den Pfeil nach außen
            if not lead:
                continue
        if not f.has_dash and all(v["kind"] == "unbekannt" for v in f.sides.values()):
            continue
        if not f.has_dash and not cfg.get("pattern_mode"):
            lead = [q for q in segs if q.length >= 6 and abs(q.x0 - q.x1) > 0.05 and abs(q.y0 - q.y1) > 0.05
                    and any(math.hypot(px - ex, py - y) <= 1.2 for px, py in ((q.x0, q.y0), (q.x1, q.y1))
                            for ex in (x0, x1))]
            if not lead:      # Maßkette / Form- und Lagetoleranzrahmen
                continue
        out.append(f)
    # Texte zuordnen
    for f in out:
        _assign_text(f, f.words, cfg)
    if cfg.get("pattern_mode") and not cfg.get("no_text_filter"):
        # Raster: ganz ohne lesbares Maß und ohne Werkstoffgruppe ist es fast immer Beschriftung (z. B. "Schnitt A-A"), keine Naht
        out = [f for f in out if f.groups or any(d.get("size") for d in f.sides.values())]
    return out

def _assign_text(f, words, cfg):
    band = cfg["text_band"]
    for side, d in f.sides.items():
        sgn = -1 if side == "up" else 1
        ymin, ymax = (f.y - band, f.y + 0.5) if side == "up" else (f.y - 0.5, f.y + band)
        ws = [w for w in words if f.x0 - 2 <= w.cx <= f.x1 + 2 and ymin <= w.cy <= ymax]
        ws.sort(key=lambda w: w.x0)
        left = [w for w in ws if w.cx < d["xmin"]]
        right = [w for w in ws if w.cx > d["xmax"]]
        d["size"] = next((w.text for w in reversed(left) if SIZE.match(w.text)), "")
        d["spec"] = " ".join(w.text for w in right if SPEC.match(w.text))
        for w in ws:
            g = parse_group_token(w.text)
            if not g:   # Gruppe klebt an Folgetext, z. B. "(22)x30(100)"
                m = re.match(r"^(\(\s*\d{1,2}(?:\s*[/+]\s*\d{1,2})?\s*\))", w.text)
                g = parse_group_token(m.group(1)) if m else None
            if g and not f.groups:
                f.groups = g
        d["words"] = [w.text for w in ws]

# ---------------------------------------------------------------- Altbezeichnungen als Text
PT = re.compile(r"^(L|I|V|VH|VX|VK|Y|YH|YX|YK)(\d+(?:,\d)?)-(\d+)(?:\s*\(T\))?$")
PT_MAP = {"L": ("Kehlnaht", "a"), "I": ("I-Naht", "I"), "V": ("V-Naht", "V"), "VH": ("HV-Naht", "HV"),
          "VX": ("DV-Naht", "DV"), "VK": ("DHV-Naht", "DHV"), "Y": ("Y-Naht", "Y"), "YH": ("HY-Naht", "HY"),
          "YX": ("DY-Naht", "DY"), "YK": ("DHY-Naht", "DHY")}

def find_pt_labels(words, taken_boxes, pair=False):
    """Interne Bezeichnungen (z. B. YH5-125, L3-1), die als Text in der Zeichnung stehen."""
    res = []
    for w in words:
        m = PT.match(w.text)
        if not m:
            continue
        if any(b[0] - 2 <= w.cx <= b[2] + 2 and b[1] <= w.cy <= b[3] for b in taken_boxes):
            continue
        art, pre = PT_MAP[m.group(1)]
        res.append(dict(word=w, art=art, angabe=f"{pre}{m.group(2)}", pt=w.text, form=m.group(3)))
    return _pair_pt(res) if pair else res

def _pt_key(t):
    return re.sub(r"\s*\(T\)$", "", t.strip())

def _pair_pt(res):
    """Übereinander stehende Bezeichnungen (oben = Pfeilseite, unten = Gegenseite) gehören zu einer
    Bezugslinie -> eine beidseitige Naht, aber nur bei komplett gleicher Bezeichnung."""
    res = sorted(res, key=lambda r: (r["word"].cy, r["word"].x0))
    used, out = set(), []
    for i, a in enumerate(res):
        if i in used:
            continue
        wa = a["word"]; ha = wa.y1 - wa.y0
        best = None
        for j in range(i + 1, len(res)):
            if j in used:
                continue
            wb = res[j]["word"]
            if _pt_key(res[j]["pt"]) != _pt_key(a["pt"]):   # nur komplett gleiche Bezeichnung -> sonst getrennte Zeilen (eigene WPS)
                continue
            if wb.cy - wa.cy > 2.2 * max(ha, 6):
                break
            gap = wb.y0 - wa.y1
            ov = min(wa.x1, wb.x1) - max(wa.x0, wb.x0)
            if wb.cy > wa.cy + 0.6 * ha and -2 <= gap <= 0.9 * ha and (ov > 0 or abs(wa.x0 - wb.x0) < 8):
                d = abs(wa.x0 - wb.x0) + gap
                if best is None or d < best[0]:
                    best = (d, j)
        if best:
            used.add(best[1]); b = res[best[1]]
            out.append(dict(word=wa, art=a["art"], angabe=a["angabe"], pt=a["pt"], form=a["form"], second=b))
        else:
            out.append(a)
    return out

# ---------------------------------------------------------------- Musterbasierte Erkennung (für Rasterbilder)
def _chain_diags(side_segs, max_perp=2.2, max_gap=3.5, max_ang=8.0):
    """Zerrissene Schrägstriche (Raster: Doppelkante / Lücke) zu einer Linie verbinden."""
    diag = [s for s in side_segs if abs(s.x0 - s.x1) > 0.05 and abs(s.y0 - s.y1) > 0.05]
    rest = [s for s in side_segs if s not in diag]
    def ang(q): return math.degrees(math.atan2(q.y1 - q.y0, q.x1 - q.x0)) % 180
    done = True
    while done:
        done = False
        for i, a in enumerate(diag):
            for b in diag[i + 1:]:
                da = abs(ang(a) - ang(b)); da = min(da, 180 - da)
                if da > max_ang: continue
                L = math.hypot(a.x1 - a.x0, a.y1 - a.y0)
                ux, uy = (a.x1 - a.x0) / L, (a.y1 - a.y0) / L
                pts = [(b.x0, b.y0), (b.x1, b.y1)]
                perp = max(abs((px - a.x0) * -uy + (py - a.y0) * ux) for px, py in pts)
                if perp > max_perp: continue
                ta = sorted((0.0, L)); tb = sorted(((px - a.x0) * ux + (py - a.y0) * uy) for px, py in pts)
                if tb[1] < ta[0] - max_gap or tb[0] > ta[1] + max_gap: continue
                lo, hi = min(ta[0], tb[0]), max(ta[1], tb[1])
                n = Seg(a.x0 + lo * ux, a.y0 + lo * uy, a.x0 + hi * ux, a.y0 + hi * uy)
                diag = [d for d in diag if d is not a and d is not b] + [n]
                done = True
                break
            if done: break
    return rest + diag

def classify_patterns(side_segs, y, sgn, tol, x0, x1, cfg_no_i=True):
    """Sucht die typischen ISO-2553-Formen als Linienmuster; unabhängig von zufällig anliegenden Textstrichen.
    Rückgabe: (kind, used_segments) oder (None, [])"""
    def v(py): return (py - y) * sgn
    verts, diags = [], []
    side_segs = _chain_diags(side_segs)
    for s in side_segs:
        if abs(s.x0 - s.x1) < 0.05 + 0.0 and True:
            lo, hi = sorted((v(s.y0), v(s.y1)))
            verts.append((s, s.x0, lo, hi))
        elif abs(s.y0 - s.y1) >= 0.05 * 0 and abs(s.x0 - s.x1) >= 0.05:
            (xa, ya), (xb, yb) = ((s.x0, v(s.y0)), (s.x1, v(s.y1)))
            if abs(ya - yb) > 2 * tol and abs(xa - xb) > 2 * tol:       # nicht (fast) waagrecht
                ang = math.degrees(math.atan2(abs(ya - yb), abs(xa - xb)))
                if 25 <= ang <= 75:
                    if ya <= yb: diags.append((s, (xa, ya), (xb, yb)))      # (tief, hoch)
                    else:        diags.append((s, (xb, yb), (xa, ya)))
    foot = [t for t in verts if abs(t[2]) <= tol and 4 <= t[3] <= 26]
    # 1) Kehlnaht: Senkrechte am Fuß + Schräge, deren Spitze oben an der Senkrechten liegt, Fuß auf der Linie
    for vs, vx, lo, hi in foot:
        for ds, low, high in diags:
            if (math.hypot(high[0] - vx, high[1] - hi) <= 1.6 * tol and abs(low[1]) <= 1.6 * tol
                    and abs(abs(low[0] - vx) - hi) <= max(2 * tol, 0.3 * hi)):
                return "Kehlnaht", [vs, ds]
    # 2) V: zwei Schrägen mit gemeinsamem Fußpunkt auf der Linie, gegensinnig
    for i, (s1, l1, h1) in enumerate(diags):
        for s2, l2, h2 in diags[i + 1:]:
            if (abs(l1[1]) <= 1.6 * tol and abs(l2[1]) <= 1.6 * tol and abs(l1[0] - l2[0]) <= 1.6 * tol
                    and (h1[0] - l1[0]) * (h2[0] - l2[0]) < 0 and h1[1] >= 4 and h2[1] >= 4):
                return "V-Naht", [s1, s2]
    # 3) HY / HV: Senkrechte am Fuß + eine Schräge
    for vs, vx, lo, hi in foot:
        if hi < 8: continue
        for ds, low, high in diags:
            if abs(low[0] - vx) <= 1.6 * tol:
                if abs(low[1]) <= 1.6 * tol and high[1] >= 4:
                    return "HV-Naht", [vs, ds]
                if 0.25 * hi <= low[1] <= 0.75 * hi and high[1] >= 0.5 * hi:
                    return "HY-Naht", [vs, ds]
    # 4) I: zwei kurze parallele Senkrechte (im Raster zu fehleranfällig -> aus)
    for i, a in enumerate(foot if not cfg_no_i else []):
        for b in foot[i + 1:]:
            if 1.5 <= abs(a[1] - b[1]) <= 7 and abs(a[3] - b[3]) <= 2 * tol and a[3] <= 14:
                return "I-Naht", [a[0], b[0]]
    return None, []
