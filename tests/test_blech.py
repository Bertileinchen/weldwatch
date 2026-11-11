import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import openpyxl
from weldwatch import output, stp, stueckliste, teile
from weldwatch import projekt as P
from weldwatch.stp import Teil
from weldwatch.stueckliste import Zeile
from tests.test_projekt import beispiel_zeichnung


def n(x, y, z):
    return (float(x), float(y), float(z))


class StpHilfenTests(unittest.TestCase):
    def test_teilname(self):
        self.assertEqual(stp.teilname_zerlegen("WN401-00001-2_20__BLECH"), ("WN401-00001-2", "20", "WN401-00001-2.20", "BLECH"))
        self.assertEqual(stp.teilname_zerlegen("WN401-00009-7_8_1__BLECH"), ("WN401-00009-7", "8.1", "WN401-00009-7.8.1", "BLECH"))
        self.assertEqual(stp.teilname_zerlegen("WN-BL-265X80X3-01__BLECH")[2:], ("WN-BL-265X80X3-01", "BLECH"))
        self.assertEqual(stp.teilname_zerlegen("10001588312sep000")[2:], ("10001588312sep000", ""))

    def test_dicke_blech_zwei_grosse_flaechen(self):
        planes = [(n(0, 0, 1), 10.0, 5000.0), (n(0, 0, -1), 0.0, 5000.0), (n(1, 0, 0), 100.0, 90.0), (n(-1, 0, 0), 0.0, 90.0)]
        self.assertEqual(stp._wert_dicke(planes), 10.0)

    def test_dicke_formrohr_kleinster_abstand(self):
        # Rechteckrohr 60x80, Wand 6: außen Abstand 60 und 80, innen 48 und 68, Wand = 6
        planes = [(n(1, 0, 0), 60, 400), (n(-1, 0, 0), 0, 400), (n(1, 0, 0), 6, 380), (n(-1, 0, 0), -54, 380),   # x: außen und innen
                  (n(0, 1, 0), 80, 400), (n(0, -1, 0), 0, 400)]
        self.assertEqual(stp._wert_dicke(planes), 6.0)

    def test_dicke_rundrohr_aus_zylindern(self):
        cyl = [(n(0, 0, 0), n(1, 0, 0), 41.25), (n(0, 0, 0), n(1, 0, 0), 30.5)]
        self.assertEqual(stp._wert_rohr(cyl), 10.75)
        self.assertIsNone(stp._wert_rohr([(n(0, 0, 0), n(1, 0, 0), 5.0)]))

    def test_bewertung(self):
        self.assertEqual(stp._bewerten("X__BLECH", 10.0)[1], stp.OK)
        self.assertEqual(stp._bewerten("X__BLECH", 598.0)[1], stp.UNSICHER)
        self.assertEqual(stp._bewerten("X__BLECH", None)[1], stp.FEHLT)
        self.assertEqual(stp._bewerten("WN121-M8_30_15-1__GEWINDEBUTZEN", 15.0)[1], stp.UNSICHER)


class StuecklisteTests(unittest.TestCase):
    TEXT = ("abgerufen am 26.03.2026 06:10\n"
            "1 2531304 WN401-00014-2.1 A0 BLECH 1 32,827 __\n"
            "2 2147988 WN401-00001-2.3 A3 WINKEL 2 0,890 16\n"
            "3 2382717 WN401-00009-1 A0 BODENRAHMEN 1 eigene Stkl. 361,893 16\n"
            "4 2179827 M5-SENKKOPF-STAHL BLINDNIETMUTTER 4 Art-Nr: 34358050020/01 0,003 21\n"
            "9\n"
            "Pos. EDV-Pos. Zeichnungsnummer / Teilenummer Format Benennung Stück\n")

    def test_zeilen(self):
        z = stueckliste.zeilen_aus_text(self.TEXT)
        self.assertEqual([(x.pos, x.teilenummer, x.benennung, x.stueck) for x in z],
                         [(1, "WN401-00014-2.1", "BLECH", 1), (2, "WN401-00001-2.3", "WINKEL", 2),
                          (3, "WN401-00009-1", "BODENRAHMEN", 1), (4, "M5-SENKKOPF-STAHL", "BLINDNIETMUTTER", 4)])
        self.assertTrue(z[2].eigene_stkl)
        self.assertFalse(z[0].eigene_stkl)
        self.assertEqual(z[3].bemerkung, "Art-Nr: 34358050020/01")
        self.assertAlmostEqual(z[0].gewicht, 32.827)

    def test_zeichnungsnr_aus_dateiname(self):
        f = stueckliste.zeichnungsnr_aus_dateiname
        self.assertEqual(f("2526201__V1__WN401-00014-2__FRONTWAND__STKL.pdf"), "WN401-00014-2")
        self.assertEqual(f("d5955cec-2526201__V1__WN401-00014-2__FRONTWAND__STKL.pdf"), "WN401-00014-2")   # Upload-Präfix
        self.assertEqual(f("2148008__V2__WN401-00001-2_12__RAHMEN WGEZ__STKL.pdf"), "WN401-00001-2.12")
        self.assertEqual(f("irgendwas.pdf"), "")


def katalog():
    k = teile.Katalog()
    k.stp_setzen([Teil("WN401-00001-2_3__WINKEL", "WN401-00001-2", "3", "WN401-00001-2.3", "WINKEL", 2.0, stp.OK),
                  Teil("WN401-00014-2_9__BLECH", "WN401-00014-2", "9", "WN401-00014-2.9", "BLECH", 598.0, stp.UNSICHER, "unplausibel"),
                  Teil("10001588312sep000", "", "", "10001588312sep000", "", 10.0, stp.OK),
                  Teil("Kehlnaht_1_oa_4", "", "", "Kehlnaht_1_oa_4", "", None, stp.UNSICHER)], "x.stp")
    k.stueckliste_hinzu("WN401-00014-2", [Zeile(1, "1", "WN401-00014-2.1", "BLECH"), Zeile(3, "3", "WN401-00001-2.3", "WINKEL", 2),
                                          Zeile(5, "5", "WN-BL-452X140X5-01", "BLECH"), Zeile(6, "6", "WN401-00001-2.12", "RAHMEN", 1, "eigene Stkl."),
                                          Zeile(9, "9", "WN401-00014-2.9", "BLECH")])
    k.stueckliste_hinzu("WN401-00009-1", [Zeile(1, "1", "WN401-00009-1.1", "BLECH")])
    return k


class KatalogTests(unittest.TestCase):
    def test_hilfen(self):
        self.assertEqual(teile.fmt_mm(5.0), "5")
        self.assertEqual(teile.fmt_mm(3.6), "3,6")
        self.assertEqual(teile.fmt_mm(10.75), "10,75")
        self.assertEqual(teile.zahl("3,6 mm"), 3.6)
        self.assertIsNone(teile.zahl("abc"))
        self.assertEqual(teile.blech_text("5", "10"), "5mm / 10mm")
        self.assertEqual(teile.blech_text("3,6", ""), "3,6mm / ?")
        self.assertEqual(teile.blech_text("", ""), "")
        self.assertEqual(teile.dicke_aus_halbzeugnummer("WN-BL-452X140X5-01"), 5.0)
        self.assertEqual(teile.dicke_aus_halbzeugnummer("WN-FL-60X5-973-01"), 5.0)
        self.assertEqual(teile.dicke_aus_halbzeugnummer("WN-FR-120X40X3-146-05"), 3.0)
        self.assertEqual(teile.dicke_aus_halbzeugnummer("WN-ROHR-25X2-39-19"), 2.0)
        self.assertIsNone(teile.dicke_aus_halbzeugnummer("WN401-00001-2.3"))

    def test_wahlen_reihenfolge_und_dicken(self):
        w = {x.key: x for x in katalog().wahlen("WN401-00014-2")}
        keys = list(w)
        self.assertEqual(keys[:5], ["pos:WN401-00014-2:1", "pos:WN401-00014-2:3", "pos:WN401-00014-2:5", "pos:WN401-00014-2:6", "pos:WN401-00014-2:9"])
        self.assertEqual(w["pos:WN401-00014-2:3"].dicke, 2.0)                  # über Teilenummer im STP
        self.assertEqual(w["pos:WN401-00014-2:5"].dicke, 5.0)                  # aus dem Halbzeugnamen
        self.assertIsNone(w["pos:WN401-00014-2:1"].dicke)                      # nicht im STP -> fehlt
        self.assertIsNone(w["pos:WN401-00014-2:6"].dicke)                      # Baugruppe
        self.assertIn("Baugruppe", w["pos:WN401-00014-2:6"].label)
        self.assertEqual(w["pos:WN401-00014-2:9"].status, stp.UNSICHER)
        self.assertIn("(?)", w["pos:WN401-00014-2:9"].label)
        self.assertIn("tnr:WN401-00009-1.1", w)                                # Teil einer anderen Stückliste
        self.assertIn("stp:10001588312sep000", w)                              # STP-Teil ohne Stücklisteneintrag
        self.assertFalse([k for k in w if "kehlnaht" in k.lower()])           # modellierte Nähte sind keine Bauteile

    def test_ohne_katalog_und_speichern(self):
        self.assertEqual(teile.Katalog().wahlen("X"), [])
        k2 = teile.Katalog.from_dict(katalog().to_dict())
        self.assertEqual([x.key for x in k2.wahlen("WN401-00014-2")], [x.key for x in katalog().wahlen("WN401-00014-2")])
        self.assertIsNone(teile.Katalog.from_dict(None))


class NahtBlechTests(unittest.TestCase):
    def test_felder_speichern_laden(self):
        with tempfile.TemporaryDirectory() as d:
            z = beispiel_zeichnung()
            z.naehte[0].teil_a, z.naehte[0].dicke_a, z.naehte[0].dicke_b = "pos:X:3", "5", "10"
            p = P.Projekt(basis="T", zeichnungen=[z], katalog=katalog())
            pfad = os.path.join(d, "p.wwp")
            p.speichern(pfad)
            q = P.Projekt.laden(pfad)
            n0 = q.zeichnungen[0].naehte[0]
            self.assertEqual((n0.teil_a, n0.dicke_a, n0.dicke_b, n0.blech), ("pos:X:3", "5", "10", "5mm / 10mm"))
            self.assertEqual(q.katalog.stp_pfad, "x.stp")
            self.assertEqual(len(q.katalog.stp), 4)
            self.assertEqual(q.anzahl_ohne_blech(), 2)            # nur die erste Naht hat beide Stärken

    def test_alte_projektdatei_ohne_katalog(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "p.wwp")
            P.Projekt(basis="T", zeichnungen=[beispiel_zeichnung()]).speichern(pfad)
            q = P.Projekt.laden(pfad)
            self.assertIsNone(q.katalog)
            self.assertEqual(q.zeichnungen[0].naehte[0].blech, "")


def vorlage(pfad, kopf):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SNP"
    for b, t in kopf.items():
        ws[f"{b}6"] = t
    for c in range(1, 16):
        ws.cell(7, c).value = "Muster"
    wb.save(pfad)


KOPF = {"A": "Zeichnung", "B": "Planquadrat", "C": "Nahtart", "D": "Dicke", "E": "Angabe", "F": "Blechdicke t1 / t2", "G": "WPS",
        "H": "Grundwerkstoff", "I": "WPQR", "O": "Bemerkung"}


class ExcelBlechTests(unittest.TestCase):
    def test_excel_schreibt_blech_in_spalte_d(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.xlsx"); vorlage(v, KOPF)
            z = beispiel_zeichnung()
            z.naehte[0].dicke_a, z.naehte[0].dicke_b = "5", "10"
            z.naehte[1].dicke_a = "3,6"
            for x in z.naehte:
                P.bestaetigen(x)
            ziel = os.path.join(d, "o.xlsx")
            P.excel_schreiben(P.Projekt(basis="T", zeichnungen=[z]), v, ziel)
            wb = openpyxl.load_workbook(ziel)
            ws = wb["SNP"]
            self.assertEqual([ws["D7"].value, ws["D8"].value, ws["D9"].value], ["5mm / 10mm", "3,6mm / ?", None])
            texte = [str(c.value) for row in wb["Protokoll"].iter_rows() for c in row if c.value]
            self.assertIn("5mm / 10mm", texte)


@unittest.skipUnless(os.environ.get("WELDWATCH_TEST_STP") and os.path.exists(os.environ.get("WELDWATCH_TEST_STP", "")),
                     "echte STP-Datei nicht vorhanden (Umgebungsvariable WELDWATCH_TEST_STP)")
class EchtesStpTests(unittest.TestCase):
    def test_kabinenrahmen(self):
        t = {x.name: x for x in stp.lese_stp(os.environ["WELDWATCH_TEST_STP"])}
        self.assertGreater(len(t), 200)
        self.assertEqual(t["WN401-00001-1_2__BLECH"].dicke, 10.0)
        self.assertEqual(t["WN401-00001-1_11__FORMROHR"].dicke, 6.0)
        self.assertEqual(t["WN-ROHR-25X2-39-19__ROHR"].dicke, 2.0)


if __name__ == "__main__":
    unittest.main()
