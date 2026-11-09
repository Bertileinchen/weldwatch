"""Zeichnungsnummer und Benennung aus dem Schriftfeld."""
import re

def read_title(words, cfg, fallback):
    rx = re.compile(cfg["drawing_no_regex"])
    cands = [w for w in words if rx.match(w.text) and w.y0 > 0.8 * max(x.y1 for x in words)]
    if not cands:
        cands = [w for w in words if rx.match(w.text)]
    if not cands:
        return fallback, ""
    # unterste Fundstelle = Schriftfeld
    dn = max(cands, key=lambda w: w.y0)
    line = sorted([w for w in words if abs(w.cy - dn.cy) < 4 and w.x0 > dn.x1 - 1],
                  key=lambda w: w.x0)
    name = " ".join(w.text for w in line if w.x0 < dn.x1 + 450)
    return dn.text, name.strip()
