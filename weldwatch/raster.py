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

def render_gray(pdf_path, dpi, page_index=0):
    pg = pdfium.PdfDocument(pdf_path)[page_index]
    return np.array(pg.render(scale=dpi / 72.0, grayscale=True).to_pil().convert("L"))

def ocr_gray_words(tess, gray, dpi, tile=2400, ov=240):
    """Volltext-OCR in Kacheln für Scans ohne Farbanmerkungen (A0 bei 300 dpi). Liefert Wörter in pt."""
    H, W = gray.shape
    k = 72.0 / dpi
    out = []
    y = 0
    while y < H:
        x = 0
        while x < W:
            crop = gray[y:y + tile, x:x + tile]
            if crop.min() < 128:
                d = tess.image_to_data(crop, config="--psm 11", output_type=tess.Output.DICT)
                for i, t in enumerate(d["text"]):
                    t = t.strip()
                    if len(t) < 2 or float(d["conf"][i]) < 30:
                        continue
                    wx0 = (x + d["left"][i]) * k; wy0 = (y + d["top"][i]) * k
                    out.append(Word(t, wx0, wy0, wx0 + d["width"][i] * k, wy0 + d["height"][i] * k))
            x += tile - ov
        y += tile - ov
    # Doppelte aus den Kachelrändern entfernen
    uniq = []
    for w in out:
        if not any(u.text == w.text and abs(u.cx - w.cx) < 3 and abs(u.cy - w.cy) < 3 for u in uniq):
            uniq.append(w)
    return uniq

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
    lim = int(2.5 * k)
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if horizontal and h <= lim and w >= minlen:
            yy = y + h / 2.0
            out.append((x, yy, x + w, yy))
        elif not horizontal and w <= lim and h >= minlen:
            xx = x + w / 2.0
            out.append((xx, y, xx, y + h))
        elif (horizontal and w >= minlen and h > lim) or (not horizontal and h >= minlen and w > lim):
            # Linie klebt an Ziffern/Kreis: nur die Zeilen (Spalten) mit der längsten Ausdehnung nehmen
            comp = (lab[y:y + h, x:x + w] == i)
            if not horizontal:
                comp = comp.T
            sums = comp.sum(axis=1)
            best = sums.max()
            if best < minlen:
                continue
            sel = np.where(sums >= 0.8 * best)[0]
            if sel.max() - sel.min() + 1 > lim:
                continue
            pos = (y if horizontal else x) + (sel.min() + sel.max() + 1) / 2.0
            cols = np.where(comp[sel].any(axis=0))[0]
            a0, a1 = (x if horizontal else y) + cols.min(), (x if horizontal else y) + cols.max() + 1
            out.append((a0, pos, a1, pos) if horizontal else (pos, a0, pos, a1))
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

_RING_CACHE = {}

def _ring_kernels(k):
    key = round(k, 3)
    if key not in _RING_CACHE:
        ks = []
        for r in (4.0, 4.8, 5.6, 6.4):
            rp = r * k; n = int(rp * 2 + 5) | 1
            yy, xx = np.mgrid[:n, :n] - n // 2
            d = np.hypot(xx, yy)
            ring = ((d >= rp - 1.0) & (d <= rp + 1.0)).astype(np.float32)
            inner = (d <= rp * 0.55).astype(np.float32)
            ks.append((ring / ring.sum(), inner / inner.sum()))
        _RING_CACHE[key] = ks
    return _RING_CACHE[key]

def ring_near(mask, dpi, ex, ey, reach=13.0):
    """Gibt es am Ende einer Bezugslinie (ex, ey in pt) einen kleinen Kreis (Rundumnaht-Zeichen, Ø ~8-13 pt)?
    Ring: Rand fast lückenlos gesetzt, Innenfläche leer."""
    k = dpi / 72.0
    pad = int(8 * k)
    x0 = max(0, int((ex - reach) * k) - pad); x1 = int((ex + reach) * k) + pad
    y0 = max(0, int((ey - reach) * k) - pad); y1 = int((ey + reach) * k) + pad
    crop = mask[y0:y1, x0:x1]
    if crop.size == 0 or crop.sum() == 0:
        return False
    D = cv2.dilate(crop, np.ones((3, 3), np.uint8)).astype(np.float32) / 255.0
    ccx, ccy = ex * k - x0, ey * k - y0
    lim = reach * k
    for ring, inner in _ring_kernels(k):
        R = cv2.filter2D(D, -1, ring, borderType=cv2.BORDER_CONSTANT)
        I = cv2.filter2D(D, -1, inner, borderType=cv2.BORDER_CONSTANT)
        ok = (R >= 0.75) & (I <= 0.4)
        yy, xx = np.nonzero(ok)
        if len(yy) and np.any(np.hypot(xx - ccx, yy - ccy) <= lim):
            return True
    return False

# ------------------------------------------------------------------ OCR
_GRP = re.compile(r"^\(\s*(\d{1,2})(?:\s*[/+]\s*(\d{1,2}))?\s*\)$")
_VALID_GR = set(range(1, 12)) | set(range(21, 27))

def _read_cluster(tess, img, gray=None):
    """Eine Zeichengruppe lesen. Sieht sie nach Werkstoffgruppe '(..)' aus, mehrere Aufbereitungen abstimmen lassen
    und nur gültige Gruppen (ISO TR 15608: 1-11, 21-26) akzeptieren."""
    from collections import Counter
    cfgs = "--psm 7 -c tessedit_char_whitelist=0123456789()xXazs/+.,n"
    first = None
    votes = Counter()
    for fx in (4, 3, 6):
        for dil in (0, 1):
            if gray is not None:
                t = cv2.resize(gray, None, fx=fx, fy=fx, interpolation=cv2.INTER_CUBIC)
                if dil:
                    t = cv2.erode(t, np.ones((2, 2), np.uint8))     # dunkle Striche etwas kräftigen
            else:
                t = cv2.dilate(img, np.ones((2, 2), np.uint8)) if dil else img
                t = 255 - cv2.resize(t, None, fx=fx, fy=fx, interpolation=cv2.INTER_CUBIC)
            t = cv2.copyMakeBorder(t, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
            r = tess.image_to_string(t, config=cfgs).strip().replace(" ", "")
            if first is None:
                first = r
                if not ("(" in r or ")" in r):
                    return r                       # kein Gruppenkandidat -> eine Lesung genügt
            m = _GRP.match(r)
            if m and all(int(g) in _VALID_GR for g in m.groups() if g):
                votes[r] += 1
    if votes:
        return votes.most_common(1)[0][0]
    return first or ""

def ocr_symbol_words(tess, mask, dpi, found, cfg, rgb=None):
    """Texte rund um eine Bezugslinie lesen (Maß, Werkstoffgruppe, Abgesetzt-Angabe).
    Vorgehen: Symbol- und Hinweislinien (lange/dünne Komponenten) entfernen, die übrigen Zeichen
    zu Gruppen nach waagrechtem Abstand bündeln und jede Gruppe einzeln lesen."""
    k = dpi / 72.0
    band = cfg["text_band"]
    words = []
    for (ya, yb) in ((found.y - band, found.y - 0.8), (found.y + 0.8, found.y + band)):
        x0 = max(0, int((found.x0 - 3) * k)); x1 = int((found.x1 + 3) * k)
        y0 = max(0, int(ya * k)); y1 = int(yb * k)
        crop = mask[y0:y1, x0:x1]
        if crop.size == 0 or crop.sum() == 0:
            continue
        n, lab, st, _ = cv2.connectedComponentsWithStats(crop, connectivity=8)
        comps = []
        for i in range(1, n):
            x, y, w, h, area = st[i]
            wp, hp = w / k, h / k
            if area < 8:
                continue
            if hp > 15.5:                                  # senkrechte Symbolstriche, Hinweislinien
                continue
            if hp < 5.5 and wp > 6:                        # waagrechte Reste
                continue
            if max(wp, hp) > 8 and area / float(w * h) < 0.2:   # dünne Schrägstriche
                continue
            comps.append((x, y, w, h, i))
        comps.sort()
        clusters = []
        for c in comps:
            if clusters and c[0] - max(q[0] + q[2] for q in clusters[-1]) < 4.5 * k:
                clusters[-1].append(c)
            else:
                clusters.append([c])
        for cl in clusters:
            xa = min(q[0] for q in cl); xb = max(q[0] + q[2] for q in cl)
            ya_ = min(q[1] for q in cl); yb_ = max(q[1] + q[3] for q in cl)
            img = np.zeros((yb_ - ya_, xb - xa), np.uint8)
            for q in cl:
                m = (lab[q[1]:q[1] + q[3], q[0]:q[0] + q[2]] == q[4])
                yy, xx = m.nonzero()
                img[yy + q[1] - ya_, xx + q[0] - xa] = 255
            gray = None
            if rgb is not None:   # Graustufen statt Binärmaske: die Maske verklebt dicht stehende Ziffern ("22")
                sel = cv2.dilate(img, np.ones((3, 3), np.uint8)) > 0
                r = rgb[y0 + ya_:y0 + yb_, x0 + xa:x0 + xb, 0]
                gray = np.where(sel, r, 255).astype(np.uint8)
            txt = _read_cluster(tess, img, gray)
            parts = txt.split()
            if not parts:
                continue
            gx0 = (x0 + xa) / k; gx1 = (x0 + xb) / k; gy0 = (y0 + ya_) / k; gy1 = (y0 + yb_) / k
            wpart = (gx1 - gx0) / len(parts)
            for j, t in enumerate(parts):
                words.append(Word(t, gx0 + j * wpart, gy0, gx0 + (j + 1) * wpart, gy1))
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


# ---------------------------------------------------------------- Bezugslinien-Beschriftungen (P&T-Text, Scan)
_PT_RX = re.compile(r"^(L|I|V|VH|VX|VK|Y|YH|YX|YK)(\d+(?:,\d)?)-(\d+)(?:\s*\(T\))?$")

def _pt_read(tess, img):
    """Ein Textstreifen -> interne Bezeichnung (mehrere Varianten, die erste gültige gewinnt)."""
    im = cv2.copyMakeBorder(img, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    cfg = "--psm 7 -c tessedit_char_whitelist=LIVYHXKT()0123456789,-"
    for sc in (1.0, 1.4, 1.8):
        i2 = im if sc == 1.0 else cv2.resize(im, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
        try:
            t = tess.image_to_string(i2, config=cfg).strip().replace("–", "-").replace("—", "-")
        except Exception:
            return None
        if _PT_RX.match(t):
            return t
    return None

def find_pt_by_reflines(tess, gray, dpi):
    """Sucht waagrechte Bezugslinien (ca. 10-80 pt) und liest den Text direkt darüber und darunter.
    Liefert Word-Objekte (pt) mit dem tatsächlichen Text-Rahmen. Findet auch Beschriftungen, die die
    Seiten-OCR übersieht (Text dicht an der Linie)."""
    S = dpi / 72.0
    b = (gray < 140).astype(np.uint8)
    h = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(10 * S), 1)))
    n, _, st, _ = cv2.connectedComponentsWithStats(h, connectivity=8)
    H = int(13 * S)
    res = []
    for i in range(1, n):
        x, y, w, hh, _a = st[i]
        if hh > 6 or not (10 * S <= w <= 80 * S):
            continue
        for up in (True, False):
            x0 = max(0, x - int(3 * S)); x1 = x + w + int(8 * S)
            if up:
                y0 = max(0, y - H); y1 = y - 1
            else:
                y0 = y + hh + 1; y1 = y0 + H
            bb = b[y0:y1, x0:x1]
            if bb.size == 0:
                continue
            cols = np.where(bb.sum(0) > 0)[0]; rows = np.where(bb.sum(1) > 0)[0]
            if len(cols) < 10 or len(rows) < int(4 * S):
                continue
            ch = rows[-1] - rows[0] + 1; cw = cols[-1] - cols[0] + 1
            if not (6 * S <= ch <= 13 * S + 4 and 3 * S < cw < 60 * S):
                continue
            # Vorfilter: Text besteht aus mehreren getrennten Zeichen
            sub = bb[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
            nc, _, cst, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
            if sum(1 for k in range(1, nc) if cst[k][3] >= 0.5 * ch) < 3:
                continue
            crop = gray[y0:y1, x0:x1][rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
            txt = _pt_read(tess, crop)
            if not txt:   # Pfeile/Linien rechts neben der Beschriftung abschneiden
                sub2 = bb[rows[0]:rows[-1] + 1, :int(x + w - x0 + 2 * S)]
                c2 = np.where(sub2.sum(0) > 0)[0]
                if len(c2) > 10:
                    txt = _pt_read(tess, gray[y0:y1, x0:x1][rows[0]:rows[-1] + 1, c2[0]:c2[-1] + 1])
            if txt:
                res.append(Word(txt, (x0 + cols[0]) / S, (y0 + rows[0]) / S,
                                (x0 + cols[-1] + 1) / S, (y0 + rows[-1] + 1) / S))
    return res

def merge_pt_words(words, new):
    """Neue Beschriftungen übernehmen, Seiten-OCR-Wörter an derselben Stelle ersetzen."""
    def hit(a, b):
        return not (a.x1 < b.x0 - 1 or a.x0 > b.x1 + 1 or a.y1 < b.y0 - 1 or a.y0 > b.y1 + 1)
    keep = [w for w in words if not any(hit(w, n) for n in new)]
    return keep + list(new)
