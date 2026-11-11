import os, sys, tempfile, unittest
from types import SimpleNamespace
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import openpyxl
from weldwatch import auswertung, config, output, projekt, stoss, symbols


def wort(text, x=100.0, y=300.0):
    return SimpleNamespace(text=text, x0=x, x1=x + 40, y0=y - 4, y1=y + 4, cx=x + 20, cy=y)


def lauf(*texte):
    ws = [wort(t, y=300 + 30 * i) for i, t in enumerate(texte)]
    pt = symbols.find_pt_labels(ws, [])
    return auswertung.build_entries([], pt, None, None, config.DEFAULTS)


class TabelleTests(unittest.TestCase):
    def test_anzahl(self):
        self.assertEqual({k: len(v) for k, v in stoss.TABELLE.items()},
                         {"L": 10, "VH": 20, "VK": 25, "YH": 22, "YK": 45})

    def test_zusatz(self):
        self.assertEqual(stoss.zusatz("YH", "125"), ("T-Stoß", "T90"))
        self.assertEqual(stoss.zusatz("VH", 24), ("T-Stoß", "T135"))
        self.assertEqual(stoss.zusatz("L", 60), ("", "45°"))          # Kehlnaht: Winkel ja, T-Stoß nie
        self.assertEqual(stoss.zusatz("L", 102), ("", "135°"))
        self.assertEqual(stoss.zusatz("VH", 100), ("", ""))           # nicht in der Liste
        self.assertEqual(stoss.zusatz("V", 20), ("", ""))             # Nr. 20 nur mit passender Nahtform
        self.assertEqual(stoss.zusatz(None, None), ("", ""))


class ErkennungTests(unittest.TestCase):
    def test_hy_t_stoss(self):
        e, = lauf("YH5-125")
        self.assertEqual((e.art, e.angabe, e.stoss, e.wps), ("HY-Naht", "HY5", "T-Stoß", "Auswahlhilfe: T90"))

    def test_kehlnaht_nie_t_stoss_aber_winkel(self):
        e, = lauf("L3-67")
        self.assertEqual((e.art, e.stoss, e.wps), ("Kehlnaht", "", "Auswahlhilfe: 135°"))

    def test_nicht_gelistet(self):
        e, = lauf("L3-1")
        self.assertEqual((e.stoss, e.wps), ("", ""))

    def test_beidseitig_gleich(self):
        pt = symbols.find_pt_labels([wort("YH5-125", y=300), wort("YH5-125", y=309)], [], pair=True)
        e, = auswertung.build_entries([], pt, None, None, config.DEFAULTS)
        self.assertEqual((e.art, e.stoss, e.wps), ("DHY-Naht", "T-Stoß", "Auswahlhilfe: T90"))


class ProjektTests(unittest.TestCase):
    def test_rundlauf_und_alte_projektdatei(self):
        e, = lauf("VK4-60")
        n = projekt.Naht.aus_entry(e)
        n2 = projekt.Naht.from_dict(n.to_dict())
        self.assertEqual((n2.stoss, n2.wps), ("T-Stoß", "Auswahlhilfe: T90"))
        self.assertEqual((n2.zu_entry().stoss, n2.zu_entry().wps), ("T-Stoß", "Auswahlhilfe: T90"))
        d = n.to_dict(); d.pop("stoss"); d.pop("wps")          # Projektdatei aus 0.5.x
        alt = projekt.Naht.from_dict(d)
        self.assertEqual((alt.stoss, alt.wps), ("", ""))


class ExcelTests(unittest.TestCase):
    def vorlage(self, pfad, mit_wps=True):
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SNP"
        ws["C3"] = "Titel"
        for c, t in enumerate(["Zeichnung", "Quadrat", "Nahtart", "Dicke", "Angabe", "", "", "Grundwerkstoff",
                               "WPS" if mit_wps else "x", "WPQR"], 1):
            ws.cell(6, c).value = t
        wb.save(pfad)

    def schreiben(self, mit_wps):
        with tempfile.TemporaryDirectory() as d:
            v, o = os.path.join(d, "v.xlsx"), os.path.join(d, "o.xlsx")
            self.vorlage(v, mit_wps)
            es = lauf("YH5-125", "L3-60", "L3-1")
            output.write_excel(v, o, [dict(dn="PF60.101", title="T", source="a.pdf", entries=es, notes=[])])
            wb = openpyxl.load_workbook(o)
            return wb["SNP"], wb["Protokoll"]

    def test_zusatz_und_wps_in_spalten(self):
        ws, _ = self.schreiben(True)
        self.assertEqual([ws.cell(7 + i, 3).value for i in range(3)], ["HY-Naht\nT-Stoß", "Kehlnaht", "Kehlnaht"])
        self.assertEqual([ws.cell(7 + i, 9).value for i in range(3)], ["Auswahlhilfe: T90", "Auswahlhilfe: 45°", None])
        self.assertTrue(ws.cell(7, 3).alignment.wrap_text)

    def test_ohne_wps_ueberschrift_kein_absturz(self):
        ws, wp = self.schreiben(False)
        self.assertEqual(ws.cell(7, 3).value, "HY-Naht\nT-Stoß")
        self.assertTrue(any("nicht gefunden" in str(r[1]) for r in wp.iter_rows(values_only=True) if r[0] == "Hinweis"))


if __name__ == "__main__":
    unittest.main()
