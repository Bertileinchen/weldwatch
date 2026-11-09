"""Findet den Block 'allgemeine Angaben' (Anbindungen, Kanten, I-Nähte ...) über seinen Text,
unabhängig von seiner Lage auf dem Blatt."""

def find_exclusion(words, cfg):
    keys = [k.lower() for k in cfg["exclude_anchors"]]
    anchors = [w for w in words if any(w.text.lower().startswith(k) or k in w.text.lower() for k in keys)]
    if len(anchors) < cfg["exclude_min_anchors"]:
        return None
    # dichtester Cluster: größte Gruppe von Ankern innerhalb eines 1200x250 pt Fensters
    best = []
    for a in anchors:
        grp = [b for b in anchors if abs(b.cx - a.cx) < 700 and abs(b.cy - a.cy) < 130]
        if len(grp) > len(best):
            best = grp
    if len(best) < cfg["exclude_min_anchors"]:
        return None
    l, t, r, b = cfg["exclude_margin"]
    return (min(w.x0 for w in best) - l, min(w.y0 for w in best) - t,
            max(w.x1 for w in best) + r, max(w.y1 for w in best) + b)

def inside(rect, x, y):
    return rect is not None and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]
