"""Planquadrat aus den Rahmenbeschriftungen (Zahlen oben, Buchstaben links)."""
import re

class Grid:
    def __init__(self, cols, rows, width, height, xb=None, yb=None):
        self.cols = cols      # [(label, x_center)]
        self.rows = rows      # [(label, y_center)]
        self.width, self.height = width, height
        self.xb = xb if xb is not None else [(a[1] + b[1]) / 2 for a, b in zip(cols, cols[1:])]
        self.yb = yb if yb is not None else [(a[1] + b[1]) / 2 for a, b in zip(rows, rows[1:])]
    def square(self, x, y):
        ci = sum(1 for b in self.xb if x > b)
        ri = sum(1 for b in self.yb if y > b)
        return f"{self.rows[ri][0]}{int(self.cols[ci][0]):02d}"

def build_grid(words, width, height):
    top = sorted([(float(w.text), w.cx) for w in words
                  if w.y1 < 35 and re.fullmatch(r"\d{1,2}", w.text)], key=lambda a: a[1])
    left = sorted([(w.text, w.cy) for w in words
                   if w.x1 < 62 and re.fullmatch(r"[A-Z]", w.text)], key=lambda a: a[1])
    # doppelte Nummern (z. B. Maßzahlen) herausfiltern: aufsteigende Folge 1..n verlangen
    cols, last = [], 0
    for n, x in top:
        if int(n) == last + 1:
            cols.append((int(n), x)); last = int(n)
    if len(cols) < 4 or len(left) < 4:
        return None
    return Grid(cols, left, width, height)


ROW_LETTERS = "ABCDEFGHJKLMNPQR"

def _chain(ticks, pitch, tol):
    """längste Kette von Teilungsmarken mit gleichem Abstand"""
    best = []
    for t in ticks:
        ch = [t]
        while True:
            nxt = [u for u in ticks if abs(u - (ch[-1] + pitch)) <= tol]
            if not nxt: break
            ch.append(nxt[0])
        if len(ch) > len(best):
            best = ch
    return best

def _clusters(idx, gap=3):
    out, s, p = [], None, None
    for c in idx:
        if s is None: s = p = c
        elif c - p > gap: out.append((s + p) / 2); s = p = c
        else: p = c
    if s is not None: out.append((s + p) / 2)
    return out

def build_grid_raster(dark, dpi, ocr_cols=None):
    """Planquadrat-Raster aus den Teilungsmarken des Rahmens im Rasterbild.
    dark: bool-Array (dunkle Pixel). ocr_cols: optional [(Spaltennummer, x_px)] zur Nummerierung."""
    import numpy as np
    H, W = dark.shape
    pt = 72.0 / dpi
    # Rahmenlinien oben (waagrecht) finden
    rp = dark[:int(70 * dpi / 72), :].mean(axis=1)
    hl = _clusters([i for i, v in enumerate(rp) if v > 0.5], 2)
    if len(hl) < 3: return None
    y0, y1 = int(hl[1]) + 3, int(hl[2]) - 3          # Beschriftungsband
    cp = dark[y0:y1, :].mean(axis=0)
    xt = _clusters([i for i, v in enumerate(cp) if v > 0.8])
    pitch = 141.7 / pt
    chain = _chain(xt, pitch, 6)
    if len(chain) < 4: return None
    # Linkes Band: Zeilenmarken
    cpv = dark[:, :int(120 * dpi / 72)].mean(axis=0)
    vl = _clusters([i for i, v in enumerate(cpv) if v > 0.5], 2)
    if len(vl) < 3: return None
    x0, x1 = int(vl[-2]) + 3, int(vl[-1]) - 3
    rpv = dark[:, x0:x1].mean(axis=1)
    yt = _clusters([i for i, v in enumerate(rpv) if v > 0.8])
    ych = _chain(yt, pitch, 6)
    if len(ych) < 3: return None
    # Zeilen: erste Zeile reicht vom oberen Rahmen (hl[1]) bis zur ersten Marke der Kette (ggf. mehrere Zeilen links davon)
    yb = [t for t in ych]
    top = hl[1]
    while yb[0] - pitch > top + 0.4 * pitch:
        yb.insert(0, yb[0] - pitch)
    bottom = yt[-1] if yt and yt[-1] > ych[-1] + 0.3 * pitch else None
    rows = []
    edges = [top] + yb + ([bottom] if bottom else [])
    for i in range(len(edges) - 1):
        if i < len(ROW_LETTERS):
            rows.append((ROW_LETTERS[i], (edges[i] + edges[i + 1]) / 2 * pt))
    yb_pt = [e * pt for e in edges[1:len(rows)]]
    # Spalten: Intervall k (k Marken links davon) hat die Nummer k + 1 + shift.
    # shift aus OCR-Treffern der Spaltennummern; ohne OCR gilt: erste Marke = Ende von Spalte 1.
    xb = list(chain)
    shift = 0
    if ocr_cols:
        votes = {}
        for n, x in ocr_cols:
            k = sum(1 for b in xb if b < x)
            votes[n - (k + 1)] = votes.get(n - (k + 1), 0) + 1
        if votes and max(votes.values()) >= 2:
            shift = max(votes, key=votes.get)
    cols = []
    for k in range(len(xb) + 1):
        left = xb[k - 1] if k > 0 else xb[0] - pitch
        right = xb[k] if k < len(xb) else xb[-1] + pitch
        n = k + 1 + shift
        if n >= 1:
            cols.append((n, (left + right) / 2 * pt))
        else:
            xb_skip = True
    # Marken, die zu Spalten < 1 gehören, entfallen
    drop = max(0, 1 - (1 + shift))
    xb_pt = [b * pt for b in xb[drop:]]
    return Grid(cols, rows, W * pt, H * pt, xb=xb_pt, yb=yb_pt)
