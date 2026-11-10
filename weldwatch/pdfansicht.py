"""Ansicht einer PDF-Seite mit Zoom/Verschieben (ohne GUI-Abhängigkeit, daher testbar).
Koordinaten: Punkte (pt), Ursprung links oben - wie in den Erkennungsergebnissen."""
import pypdfium2 as pdfium


class PdfSeite:
    def __init__(self, pfad, seite=0):
        self.doc = pdfium.PdfDocument(pfad)
        self.page = self.doc[seite]
        self.w, self.h = self.page.get_size()

    def bereich(self, x0, y0, x1, y1, scale):
        """Rendert den Ausschnitt (pt) mit scale Pixel je pt. Gibt (PIL-Bild, (links, oben)) des tatsächlich
        gerenderten, an die Seite gekürzten Ausschnitts zurück oder (None, None), wenn nichts sichtbar ist."""
        l, t = max(0.0, x0), max(0.0, y0)
        r, b = min(self.w, x1), min(self.h, y1)
        if r - l < 0.5 or b - t < 0.5:
            return None, None
        img = self.page.render(scale=scale, crop=(l, self.h - b, self.w - r, t)).to_pil().convert("RGB")
        return img, (l, t)

    def schliessen(self):
        try:
            self.page.close()
            self.doc.close()
        except Exception:
            pass


class Ansicht:
    """Zoom und Lage: scale = Bildschirmpixel je pt, (ox, oy) = pt-Koordinate der linken oberen Fensterecke."""
    MAX_SCALE = 10.0

    def __init__(self, seite=(1.0, 1.0), fenster=(1, 1)):
        self.seite = seite
        self.w, self.h = fenster
        self.scale, self.ox, self.oy = 1.0, 0.0, 0.0
        self.einpassen()

    def setze_fenster(self, w, h):
        self.w, self.h = max(1, w), max(1, h)

    def setze_seite(self, seite):
        self.seite = seite
        self.einpassen()

    def min_scale(self):
        sw, sh = self.seite
        return min(self.w / max(sw, 1), self.h / max(sh, 1)) * 0.5

    def einpassen(self, rand=8):
        sw, sh = self.seite
        s = min((self.w - 2 * rand) / max(sw, 1), (self.h - 2 * rand) / max(sh, 1))
        self.scale = max(s, 1e-3)
        self.ox = (sw - self.w / self.scale) / 2
        self.oy = (sh - self.h / self.scale) / 2

    def zu_px(self, x, y):
        return (x - self.ox) * self.scale, (y - self.oy) * self.scale

    def zu_pt(self, px, py):
        return px / self.scale + self.ox, py / self.scale + self.oy

    def sichtfeld(self):
        return self.ox, self.oy, self.ox + self.w / self.scale, self.oy + self.h / self.scale

    def zoom(self, faktor, px, py):
        """um den Bildschirmpunkt (px, py) vergrößern (faktor > 1) oder verkleinern"""
        x, y = self.zu_pt(px, py)
        self.scale = min(self.MAX_SCALE, max(self.min_scale(), self.scale * faktor))
        self.ox = x - px / self.scale
        self.oy = y - py / self.scale

    def verschieben(self, dpx, dpy):
        self.ox -= dpx / self.scale
        self.oy -= dpy / self.scale

    def sichtbar(self, box, anteil=1.0):
        """Liegt die Box (x0,y0,x1,y1) vollständig (anteil=1) im Fenster?"""
        fx0, fy0, fx1, fy1 = self.sichtfeld()
        return box[0] >= fx0 and box[1] >= fy0 and box[2] <= fx1 and box[3] <= fy1

    def zentrieren(self, x, y, min_scale=None):
        if min_scale is not None and self.scale < min_scale:
            self.scale = min(self.MAX_SCALE, min_scale)
        self.ox = x - self.w / self.scale / 2
        self.oy = y - self.h / self.scale / 2
