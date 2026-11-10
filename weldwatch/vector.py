"""Einlesen eines Vektor-PDFs: Linien der Anmerkungsebene, Wörter, Seitenart."""
import pdfplumber
from dataclasses import dataclass

@dataclass
class Seg:
    x0: float; y0: float; x1: float; y1: float
    @property
    def length(self):
        return ((self.x0-self.x1)**2 + (self.y0-self.y1)**2) ** 0.5

@dataclass
class Word:
    text: str; x0: float; y0: float; x1: float; y1: float
    @property
    def cx(self): return (self.x0 + self.x1) / 2
    @property
    def cy(self): return (self.y0 + self.y1) / 2

def _is_annot(color, cfg):
    if not isinstance(color, (list, tuple)) or len(color) != 3:
        return False
    t = cfg["annot_color_tol"]
    return all(abs(a - b) <= t for a, b in zip(color, cfg["annot_color"]))

def page_kind(page):
    """'vektor' (Textebene vorhanden), 'raster' (nur Bilder) oder 'leer'"""
    n_chars = len(page.chars)
    n_vec = len(page.lines) + len(page.curves) + len(page.rects)
    if n_chars >= 20 and n_vec > 200:
        return "vektor"
    if page.images and n_vec < 500:
        return "raster"
    return "vektor" if n_chars else "leer"

def read_page(page, cfg):
    segs = []
    for o in page.lines:
        c = o.get("stroking_color") or o.get("non_stroking_color")
        if not _is_annot(c, cfg):
            continue
        pts = o["pts"]
        for i in range(len(pts) - 1):
            (a, b), (c2, d) = pts[i], pts[i + 1]
            segs.append(Seg(a, b, c2, d))
    for o in page.curves:
        c = o.get("stroking_color") or o.get("non_stroking_color")
        if not _is_annot(c, cfg):
            continue
        pts = o["pts"]
        if len(pts) > 40:
            continue
        closed = o.get("fill") or (len(pts) > 2 and abs(pts[0][0]-pts[-1][0]) < 0.1 and abs(pts[0][1]-pts[-1][1]) < 0.1)
        n = len(pts)
        for i in range(n - 1 + (1 if closed and n > 2 else 0)):
            (a, b), (c2, d) = pts[i], pts[(i + 1) % n]
            if abs(a - c2) > 0.01 or abs(b - d) > 0.01:
                segs.append(Seg(a, b, c2, d))
    words = [Word(w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
             for w in page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)]
    return segs, words
