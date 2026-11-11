"""Teilekatalog für die Blechstärken je Naht (Version 0.8.0).

Quellen: STP-Modell (Teile und berechnete Dicke, siehe stp.py) und Stücklisten-PDFs (Pos. -> Teilenummer, stueckliste.py).
Je Naht werden die zwei Nahtpartner von Hand gewählt; die Dicke kommt als Vorschlag aus dem Katalog und bleibt änderbar.
Ohne STP bleibt nur die Eingabe von Hand.
"""
import re
from dataclasses import dataclass

from .stp import Teil, OK, UNSICHER, FEHLT
from .stueckliste import Zeile


def norm(teilenummer):
    return (teilenummer or "").upper().replace("_", ".").strip()


def fmt_mm(wert):
    """5.0 -> '5', 3.6 -> '3,6', 10.75 -> '10,75'"""
    if wert is None:
        return ""
    s = f"{wert:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def zahl(text):
    """'3,6' / '3.6' / '3,6mm' -> 3.6; leer oder ungültig -> None"""
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group(0).replace(",", ".")) if m else None


def blech_text(dicke_a, dicke_b):
    """'5mm / 10mm'; fehlt eine Seite, steht dort '?' (sichtbar unvollständig); fehlen beide: leer."""
    a, b = fmt_mm(zahl(dicke_a)), fmt_mm(zahl(dicke_b))
    if not a and not b:
        return ""
    return f"{a + 'mm' if a else '?'} / {b + 'mm' if b else '?'}"


_HALBZEUG = (  # Halbzeug-Teilenummern tragen die Abmessung: WN-BL-452X140X5-01 (Blech), WN-FL-60X5-973-01 (Flach), ...
    (re.compile(r"^WN-BL-\d+(?:[.,]\d+)?X\d+(?:[.,]\d+)?X(\d+(?:[.,]\d+)?)(?:-|$)", re.I), "Blech"),
    (re.compile(r"^WN-FL-\d+(?:[.,]\d+)?X(\d+(?:[.,]\d+)?)(?:-|$)", re.I), "Flachstahl"),
    (re.compile(r"^WN-FR-\d+(?:[.,]\d+)?X\d+(?:[.,]\d+)?X(\d+(?:[.,]\d+)?)(?:-|$)", re.I), "Formrohr"),
    (re.compile(r"^WN-ROHR-\d+(?:[.,]\d+)?X(\d+(?:[.,]\d+)?)(?:-|$)", re.I), "Rohr"),
)


def dicke_aus_halbzeugnummer(teilenummer):
    for muster, _art in _HALBZEUG:
        m = muster.match(teilenummer or "")
        if m:
            return float(m.group(1).replace(",", "."))
    return None


@dataclass
class Wahl:
    """Ein auswählbares Teil für 'Teil A / Teil B'."""
    key: str
    label: str
    dicke: float = None
    status: str = FEHLT
    hinweis: str = ""

    @property
    def dicke_text(self):
        return fmt_mm(self.dicke)


class Katalog:
    def __init__(self, stp=None, stp_pfad="", stuecklisten=None):
        self.stp = list(stp or [])                  # [stp.Teil]
        self.stp_pfad = stp_pfad
        self.stuecklisten = dict(stuecklisten or {})   # Zeichnungsnr -> [stueckliste.Zeile]
        self._wahlen = None

    def leer(self):
        return not self.stp and not self.stuecklisten

    # -- Aufbau
    def stp_setzen(self, teile, pfad=""):
        self.stp, self.stp_pfad, self._wahlen = list(teile), pfad, None

    def stueckliste_hinzu(self, zeichnung, zeilen):
        self.stuecklisten[norm(zeichnung)] = list(zeilen)
        self._wahlen = None

    # -- Abfrage
    def _stp_nach_tnr(self):
        d = {}
        for t in self.stp:
            d.setdefault(norm(t.teilenummer), t)
        return d

    def _wahl_aus_zeile(self, key, label_kopf, z, stp_nach):
        t = stp_nach.get(norm(z.teilenummer))
        if z.eigene_stkl:
            return Wahl(key, f"{label_kopf}{z.teilenummer} {z.benennung} (Baugruppe)", None, FEHLT, "Baugruppe mit eigener Stückliste")
        if t is not None and t.dicke is not None:
            return Wahl(key, f"{label_kopf}{z.teilenummer} {z.benennung} · {fmt_mm(t.dicke)} mm" + (" (?)" if t.status != OK else ""),
                        t.dicke, t.status, t.hinweis)
        h = dicke_aus_halbzeugnummer(z.teilenummer)
        if h is not None:
            return Wahl(key, f"{label_kopf}{z.teilenummer} {z.benennung} · {fmt_mm(h)} mm", h, OK, "aus der Teilenummer des Halbzeugs")
        return Wahl(key, f"{label_kopf}{z.teilenummer} {z.benennung} · Dicke fehlt", None, FEHLT,
                    "nicht im STP gefunden" if self.stp else "kein STP geladen")

    def wahlen(self, zeichnung=""):
        """Auswahlliste für die Naht-Maske. Zuerst die Positionen der Stückliste dieser Zeichnung, dann alle übrigen Teile
        (je Teilenummer einmal), dann STP-Teile ohne Stücklisteneintrag (meist nur mit SAP-Nummer benannt)."""
        stp_nach = self._stp_nach_tnr()
        out, gesehen, stp_benutzt = [], set(), set()
        dn = norm(zeichnung)
        for zng, zeilen in self.stuecklisten.items():
            for z in zeilen:
                t = stp_nach.get(norm(z.teilenummer))
                if t is not None:
                    stp_benutzt.add(t.name)
        if dn in self.stuecklisten:
            for z in self.stuecklisten[dn]:
                w = self._wahl_aus_zeile(f"pos:{dn}:{z.pos}", f"Pos {z.pos}: ", z, stp_nach)
                out.append(w)
                gesehen.add(norm(z.teilenummer))
        for zng, zeilen in self.stuecklisten.items():
            if zng == dn:
                continue
            for z in zeilen:
                if z.eigene_stkl or norm(z.teilenummer) in gesehen:
                    continue
                gesehen.add(norm(z.teilenummer))
                out.append(self._wahl_aus_zeile(f"tnr:{norm(z.teilenummer)}", "", z, stp_nach))
        for t in self.stp:
            if t.name in stp_benutzt or norm(t.teilenummer) in gesehen or "kehlnaht" in t.name.lower():
                continue          # modellierte Nahtkörper sind keine Bauteile
            kopf = f"{t.name}" + (f" ({t.benennung})" if t.benennung and t.benennung not in t.name else "")
            out.append(Wahl(f"stp:{t.name}", f"{kopf} · " + (f"{fmt_mm(t.dicke)} mm" + (" (?)" if t.status != OK else "") if t.dicke is not None else "Dicke fehlt"),
                            t.dicke, t.status, t.hinweis))
        return out

    # -- Speichern
    def to_dict(self):
        return dict(stp_pfad=self.stp_pfad, stp=[t.to_dict() for t in self.stp],
                    stuecklisten={k: [z.to_dict() for z in v] for k, v in self.stuecklisten.items()})

    @classmethod
    def from_dict(cls, d):
        if not d:
            return None
        return cls([Teil.from_dict(t) for t in d.get("stp", [])], d.get("stp_pfad", ""),
                   {k: [Zeile.from_dict(z) for z in v] for k, v in d.get("stuecklisten", {}).items()})

    def kurzinfo(self):
        n_s = len(self.stuecklisten)
        return f"{len(self.stp)} STP-Teile, {n_s} Stückliste(n)"
