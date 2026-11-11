import os
import tempfile
import unittest

from weldwatch import abbruch, lauf
from weldwatch.projekt import Projekt, Zeichnung, excel_schreiben


class ScanTests(unittest.TestCase):
    def test_erkannt_roundtrip_und_ungescannt(self):
        z = Zeichnung(pfad="a.pdf", datei="a.pdf", erkannt=False)
        self.assertFalse(Zeichnung.from_dict(z.to_dict()).erkannt)
        alt = z.to_dict(); alt.pop("erkannt")
        self.assertTrue(Zeichnung.from_dict(alt).erkannt)
        p = Projekt()
        p.zeichnungen.append(z)
        self.assertEqual(p.ungescannt(), [z])
        self.assertFalse(p.vollstaendig_geprueft())
        with self.assertRaises(ValueError):
            excel_schreiben(p, "nicht_vorhanden.xlsx", "x.xlsx")

    def test_leere_zeichnung(self):
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "t.pdf")
            open(pf, "wb").write(b"%PDF-1.4\n")
            z = lauf.leere_zeichnung(pf)
            self.assertFalse(z.erkannt)
            self.assertEqual(z.naehte, [])
            self.assertTrue(z.pruefsumme)

    def test_abbruch_flag(self):
        abbruch.zuruecksetzen()
        abbruch.pruefen()
        abbruch.anfordern()
        self.assertTrue(abbruch.gesetzt())
        with self.assertRaises(abbruch.Abgebrochen):
            abbruch.pruefen()
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "t.pdf")
            open(pf, "wb").write(b"%PDF-1.4\n")
            self.assertEqual(lauf.erkennen([pf]), [])
        abbruch.zuruecksetzen()


if __name__ == "__main__":
    unittest.main()
