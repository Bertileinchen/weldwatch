"""Stücklisten-PDF (Druckversion aus dem PLM) lesen: Pos., EDV-Pos., Teilenummer, Benennung, Stück, Bemerkung.

Die Stücklisten enthalten keine Blechdicken (Spalte "Abmessungen / Bemerkung" ist leer oder nennt nur "eigene Stkl.").
Sie liefern die Teilestruktur: Welche Pos. einer Zeichnung gehört zu welcher Teilenummer, und wo eine Unterbaugruppe
mit eigener Stückliste steht.
"""
import os, re
from dataclasses import dataclass

# 1  2531304  WN401-00014-2.1  A0  BLECH  1  [Bemerkung]  32,827  __
_ZEILE = re.compile(r"^(?P<pos>\d+)\s+(?P<edv>\d{6,8})\s+(?P<tnr>\S+)\s+(?:(?P<fmt>A[0-4])\s+)?(?P<ben>.+?)\s+"
                    r"(?P<stk>\d+)\s+(?:(?P<bem>.*?)\s+)?(?P<gew>\d+,\d{1,3})(?:\s+\S+)?$")


@dataclass
class Zeile:
    pos: int
    edv: str
    teilenummer: str
    benennung: str
    stueck: int = 1
    bemerkung: str = ""
    gewicht: float = 0.0

    @property
    def eigene_stkl(self):
        return "eigene Stkl" in self.bemerkung

    def to_dict(self):
        return dict(pos=self.pos, edv=self.edv, teilenummer=self.teilenummer, benennung=self.benennung,
                    stueck=self.stueck, bemerkung=self.bemerkung, gewicht=self.gewicht)

    @classmethod
    def from_dict(cls, d):
        return cls(int(d.get("pos", 0)), d.get("edv", ""), d.get("teilenummer", ""), d.get("benennung", ""),
                   int(d.get("stueck", 1)), d.get("bemerkung", ""), float(d.get("gewicht", 0.0)))


def zeichnungsnr_aus_dateiname(datei):
    """'2526201__V1__WN401-00014-2__FRONTWAND__STKL.pdf' -> 'WN401-00014-2'; 'WN401-00001-2_12' -> 'WN401-00001-2.12'"""
    teile = os.path.splitext(os.path.basename(datei))[0].split("__")
    for i, t in enumerate(teile[:-1]):
        if re.fullmatch(r"V\d+", t) and i + 1 < len(teile):     # EDV-Pos__Version__Zeichnungsnr__Benennung__...
            return teile[i + 1].replace("_", ".")
    return ""


def zeilen_aus_text(text):
    """Text einer Stücklistenseite -> Liste Zeile (Zeilen ohne Teilenummer, z. B. leere Positionen, entfallen)."""
    out = []
    for z in text.split("\n"):
        m = _ZEILE.match(z.strip())
        if not m:
            continue
        out.append(Zeile(int(m.group("pos")), m.group("edv"), m.group("tnr"), m.group("ben").strip(),
                         int(m.group("stk")), (m.group("bem") or "").strip(),
                         float(m.group("gew").replace(",", "."))))
    return out


def lese_stueckliste(pfad):
    """Stücklisten-PDF -> (Zeichnungsnummer, [Zeile]). Die Zeichnungsnummer kommt aus dem Dateinamen."""
    import pdfplumber
    zeilen = []
    with pdfplumber.open(pfad) as pdf:
        for seite in pdf.pages:
            zeilen += zeilen_aus_text(seite.extract_text() or "")
    return zeichnungsnr_aus_dateiname(pfad), zeilen
