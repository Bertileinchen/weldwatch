"""Auswertung von Rasterbildern (Scan / 'Print to PDF'): Anmerkungsebene per Farbe herausfiltern,
Linien erkennen, Texte per OCR lesen. Danach läuft dieselbe Symbolerkennung wie bei Vektor-PDFs."""
import math, os, sys, re
import numpy as np
import cv2
import pypdfium2 as pdfium
from .vector import Seg, Word
from .grid import build_grid_raster

def _find_tesseract():
    try:
        import pytesseract
    except ImportError:
        return None
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for cand in (os.path.join(base, "tesseract", "tesseract.exe"), os.path.join(base, "tesseract", "tesseract")):
        if os.path.exists(cand):
            pytesseract.pytesseract.tesseract_cmd = cand
            break
    try:
        pytesseract.get_tesseract_version()
        return pytesseract
    except Exception:
        return None

def render(pdf_path, dpi, page_index=0):
    pg = pdfium.PdfDocument(pdf_path)[page_index]
    img = pg.render(scale=dpi / 72.0).to_pil().convert("RGB")
    return np.array(img)

def annotation_mask(rgb, cfg):
    """Pixel in der Farbe der Anmerkungsebene (Türkis) -> uint8-Maske 0/255"""
    r, g, b = [rgb[:, :, i].astype(int) for i in range(3)]
    ref = [c * 255 for c in cfg["annot_color"]]
    # Abstand zur Anmerkungsfarbe, Weiß/Schwarz/Grau ausschließen
    # auch blasse (anti-aliasing) Pixel der dünnen Linien erfassen
    sat = (g - r > 14) & (b - r > 14) & (abs(g - b) < 50) & (g > 60)
    m = sat.astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return m

def _merge(segs_px, ang_tol=3.0, dist_tol=2.6, gap=6.0):
    """Kollineare, überlappende Linienstücke zusammenfassen"""
    items = []
    for x0, y0, x1, y1 in segs_px:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 2: continue
        th = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        d = -x0 * s + y0 * c
        t0, t1 = sorted((x0 * c + y0 * s, x1 * c + y1 * s))
        items.append([th, d, t0, t1])
    items.sort(key=lambda a: (round(a[0] / ang_tol), a[1]))
    used = [False] * len(items)
    out = []
    for i, a in enumerate(items):
        if used[i]: continue
        grp = [a]; used[i] = True
        changed = True
        while changed:
            changed = False
            for j, b in enumerate(items):
                if used[j]: continue
                dth = min(abs(b[0] - a[0]), 180 - abs(b[0] - a[0]))
                if dth > ang_tol or abs(b[1] - a[1]) > dist_tol: continue
                lo = min(g[2] for g in grp); hi = max(g[3] for g in grp)
                if b[3] >= lo - gap and b[2] <= hi + gap:
                    grp.append(b); used[j] = True; changed = True
        th = sum(g[0] for g in grp) / len(grp); d = sum(g[1] for g in grp) / len(grp)
        lo = min(g[2] for g in grp); hi = max(g[3] for g in grp)
        # senkrecht/waagrecht einrasten
        if min(th, 180 - th) < ang_tol: th = 0.0
        elif abs(th - 90) < ang_tol: th = 90.0
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        out.append((lo * c - d * s, lo * s + d * c, hi * c - d * s, hi * s + d * c))
    return out

def _axis_lines(mask, dpi, horizontal):
    k = dpi / 72.0
    minlen = int(11 * k)
    if horizontal:
        bridged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (int(3 * k), 1)))
        opened = cv2.morphologyEx(bridged, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (minlen, 1)))
    else:
        bridged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(3 * k))))
        opened = cv2.morphologyEx(bridged, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, minlen)))
    n, lab, st, cen = cv2.connectedComponentsWithStats(opened, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if horizontal and h <= int(2.5 * k) and w >= minlen:
            yy = y + h / 2.0
            out.append((x, yy, x + w, yy))
        elif not horizontal and w <= int(2.5 * k) and h >= minlen:
            xx = x + w / 2.0
            out.append((xx, y, xx, y + h))
    return out

def detect_segments(mask, dpi):
    """Waagrechte/senkrechte Linien per Morphologie, schräge per LSD."""
    k = 72.0 / dpi
    segs = []
    for horiz in (True, False):
        for x0, y0, x1, y1 in _axis_lines(mask, dpi, horiz):
            segs.append(Seg(x0 * k, y0 * k, x1 * k, y1 * k))
    lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines = lsd.detect(mask)[0]
    diag = []
    if lines is not None:
        for x0, y0, x1, y1 in np.asarray(lines).reshape(-1, 4):   # Form je nach OpenCV-Version (N,1,4) oder (N,4)
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180
            off = min(ang % 90, 90 - ang % 90)       # Abweichung von der nächsten Achse
            if off >= 12 and math.hypot(x1 - x0, y1 - y0) >= 8:
                diag.append((x0, y0, x1, y1))
    for x0, y0, x1, y1 in _merge(diag):
        if math.hypot(x1 - x0, y1 - y0) >= 8:
            segs.append(Seg(x0 * k, y0 * k, x1 * k, y1 * k))
    return segs

# ------------------------------------------------------------------ OCR
def ocr_symbol_words(tess, mask, dpi, found, cfg):
    """Texte rund um eine Bezugslinie lesen: oberhalb und unterhalb getrennt (nur Anmerkungsfarbe, vergrößert)."""
    k = dpi / 72.0
    band = cfg["text_band"]
    words = []
    for (ya, yb) in ((found.y - band, found.y + 0.8), (found.y - 0.8, found.y + band)):
        x0 = max(0, int((found.x0 - 3) * k)); x1 = int((found.x1 + 3) * k)
        y0 = max(0, int(ya * k)); y1 = int(yb * k)
        crop = mask[y0:y1, x0:x1]
        if crop.size == 0 or crop.sum() == 0:
            continue
        img = 255 - cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        img = cv2.copyMakeBorder(img, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
        for psm in (7, 11):
            d = tess.image_to_data(img, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789()xXazs/+.,n",
                                   output_type=tess.Output.DICT)
            got = []
            for i, t in enumerate(d["text"]):
                t = t.strip()
                if not t or float(d["conf"][i]) < 10:
                    continue
                wx0 = (d["left"][i] - 24) / 4 / k + x0 / k; wy0 = (d["top"][i] - 24) / 4 / k + y0 / k
                got.append(Word(t, wx0, wy0, wx0 + d["width"][i] / 4 / k, wy0 + d["height"][i] / 4 / k))
            if got:
                words += got
                break
    return words

def ocr_page_words(tess, rgb, dpi, tile=1500, ov=150, scale=1.5):
    """Grobe Volltext-OCR (für Ausschluss-Block und Spaltennummern)."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    H, W = gray.shape
    k = 72.0 / dpi
    out = []
    y = 0
    while y < H:
        x = 0
        while x < W:
            crop = gray[y:y + tile, x:x + tile]
            img = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            d = tess.image_to_data(img, config="--psm 11", output_type=tess.Output.DICT)
            for i, t in enumerate(d["text"]):
                t = t.strip()
                if len(t) < 2 or float(d["conf"][i]) < 30:
                    continue
                wx0 = (x + d["left"][i] / scale) * k; wy0 = (y + d["top"][i] / scale) * k
                out.append(Word(t, wx0, wy0, wx0 + d["width"][i] / scale * k, wy0 + d["height"][i] / scale * k))
            x += tile - ov
        y += tile - ov
    return out

def ocr_column_numbers(tess, gray, dpi, band_h_pt=45):
    k = 72.0 / dpi
    top = gray[:int(band_h_pt / k), :]
    d = tess.image_to_data(top, config="--psm 11 -c tessedit_char_whitelist=0123456789", output_type=tess.Output.DICT)
    res = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if t.isdigit() and 1 <= int(t) <= 30 and float(d["conf"][i]) > 40:
            res.append((int(t), d["left"][i] + d["width"][i] / 2))
    return res
