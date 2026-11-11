import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import openpyxl
from PIL import Image
from weldwatch import projekt as P
from weldwatch.grid import Grid
from weldwatch.pdfansicht import Ansicht, PdfSeite


def beispiel_grid():
    cols = [(i, 100 + 200 * (i - 1)) for i in range(1, 7)]
    rows = [(c, 100 + 200 * i) for i, c in enumerate("ABCDEF")]
    return Grid(cols, rows, 1200, 1200)


def beispiel_zeichnung(pfad="x.pdf"):
    z = P.Zeichnung(pfad=pfad, datei=os.path.basename(pfad), dn="PF60.100", title="Rahmen", seite=(1200.0, 1200.0),
                    grid=beispiel_grid(), ex=(10, 10, 100, 100))
    z.naehte = [
        P.Naht(square="B03", x=500, y=300, art="Kehlnaht", angabe="a3", gruppe="Gr.1", box=(465, 286, 535, 314), ok=True),
        P.Naht(square="A01", x=100, y=100, art="HY-Naht", angabe="HY15", dicke="s15", gruppe="Gr.22/23",
               box=(65, 86, 135, 114), ok=False, bemerkung=["Maß nicht gelesen - prüfen"]),
        P.Naht(square="C05", x=900, y=500, art="V-Naht", angabe="V20", gruppe="Gr.1", box=(865, 486, 935, 514)),
    ]
    P.neu_nummerieren(z)
    return z


class ProjektTests(unittest.TestCase):
    def test_nummerierung(self):
        z = beispiel_zeichnung()
        self.assertEqual([(n.square, n.nr) for n in z.naehte], [("A01", 1), ("B03", 2), ("C05", 3)])

    def test_speichern_laden(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, "x.pdf")
            Image.new("RGB", (60, 60), "white").save(pdf)
            z = beispiel_zeichnung(pdf)
            z.pruefsumme = P.datei_pruefsumme(pdf)
            p = P.Projekt(basis="Test", zeichnungen=[z])
            P.bestaetigen(z.naehte[0])
            P.aendern(z, z.naehte[1], angabe="HY16", bemerkung="geändert; zweiter Vermerk")
            ziel = os.path.join(d, "u", "t.wwp")
            p.speichern(ziel)
            q = P.Projekt.laden(ziel)
            z2 = q.zeichnungen[0]
            self.assertEqual([n.to_dict() for n in z.naehte], [n.to_dict() for n in z2.naehte])
            self.assertEqual(z2.grid.square(500, 300), "B03")
            self.assertEqual(z2.ex, (10, 10, 100, 100))
            self.assertFalse(z2.pdf_geaendert())
            self.assertEqual(z2.naehte[1].bemerkung, ["geändert", "zweiter Vermerk"])

    def test_pfad_wird_nach_verschieben_gefunden(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "alt")); os.makedirs(os.path.join(d, "neu"))
            pdf = os.path.join(d, "alt", "x.pdf")
            Image.new("RGB", (60, 60), "white").save(pdf)
            p = P.Projekt(zeichnungen=[beispiel_zeichnung(pdf)])
            p.speichern(os.path.join(d, "alt", "t.wwp"))
            os.rename(pdf, os.path.join(d, "neu", "x.pdf"))
            os.rename(os.path.join(d, "alt", "t.wwp"), os.path.join(d, "neu", "t.wwp"))
            q = P.Projekt.laden(os.path.join(d, "neu", "t.wwp"))
            self.assertTrue(os.path.exists(q.zeichnungen[0].pfad))

    def test_status_logik(self):
        z = beispiel_zeichnung()
        a, b, c = z.naehte
        P.aendern(z, a)                                   # unverändert -> bestätigt
        self.assertEqual(a.status, P.BESTAETIGT)
        self.assertTrue(P.aendern(z, b, angabe="HY16"))   # verändert -> geändert
        self.assertEqual(b.status, P.GEAENDERT)
        P.loeschen(z, c)
        self.assertEqual((c.status, c.nr), (P.GELOESCHT, 3))
        self.assertEqual([n.nr for n in z.aktive()], [1, 2])
        self.assertEqual(z.naehte[-1].id, c.id)           # gelöschte stehen hinten
        P.wiederherstellen(z, c)
        self.assertEqual(c.status, P.OFFEN)
        n = P.neue_naht(z, 700, 700)
        self.assertEqual((n.status, n.square, n.quelle), (P.MANUELL, "D04", "manuell"))
        self.assertTrue(n.offen)                       # leer = noch zu tun
        P.aendern(z, n, art="Kehlnaht", angabe="a4")
        self.assertEqual(n.status, P.MANUELL)
        self.assertFalse(n.offen)
        P.loeschen(z, n)                               # Manuelle werden ganz entfernt, nicht als "gelöscht" geführt
        self.assertNotIn(n, z.naehte)

    def test_neue_naht_mit_rahmen(self):
        z = beispiel_zeichnung()
        n = P.neue_naht(z, 0, 0, box=(300, 300, 200, 250))
        self.assertEqual(n.box, (200, 250, 300, 300))
        self.assertEqual((n.x, n.y), (250, 275))

    def test_gruppen(self):
        for ok in ("Gr.1", "Gr.22/23", "Gr.11", "Gr.1 + Gr.8", "Gr.26"):
            self.assertTrue(P.gruppe_gueltig(ok), ok)
        for schlecht in ("", "Gr.12", "Gr.0", "1", "Gr.22", "Gr.1/8", "Gr.27"):
            self.assertFalse(P.gruppe_gueltig(schlecht), schlecht)

    def test_zusammenfuehren_behaelt_pruefung(self):
        alt = beispiel_zeichnung()
        a, b, c = alt.naehte
        P.aendern(alt, b, angabe="HY16", gruppe="Gr.22/23")      # Person hat korrigiert
        P.loeschen(alt, c)                                          # Person hat verworfen
        man = P.neue_naht(alt, 1000, 1000)                          # Person hat ergänzt
        P.aendern(alt, man, art="Kehlnaht", angabe="a4")
        neu = beispiel_zeichnung()                                  # Neulauf: findet a, b, c wieder (leicht verschoben) + eine neue
        for n in neu.naehte:
            n.x += 3; n.y -= 2
        neu.naehte[1].angabe = "HY15 (Neulauf)"
        neu.naehte.append(P.Naht(square="E02", x=300, y=900, art="Kehlnaht", angabe="a5", box=(265, 886, 335, 914)))
        hinzu, entfernt, behalten = P.zusammenfuehren(alt, neu)
        self.assertEqual((hinzu, entfernt, behalten), (1, 0, 3 + 1 - 1))   # b, c(gelöscht), man bleiben; a wird ersetzt (offen)
        nach_id = {n.id: n for n in alt.naehte}
        self.assertEqual(nach_id[b.id].angabe, "HY16")             # Änderung nicht überschrieben
        self.assertEqual(nach_id[c.id].status, P.GELOESCHT)       # Gelöschtes kommt nicht zurück
        self.assertEqual(sum(1 for n in alt.naehte if n.square == "C05"), 1)   # kein Duplikat der gelöschten
        self.assertIn(man.id, nach_id)
        self.assertEqual(sum(1 for n in alt.naehte if n.angabe == "a5" and n.status == P.OFFEN), 1)

    def test_zusammenfuehren_entfernt_nicht_mehr_gefundene_offene(self):
        alt = beispiel_zeichnung()
        neu = beispiel_zeichnung()
        neu.naehte = neu.naehte[:2]
        hinzu, entfernt, behalten = P.zusammenfuehren(alt, neu)
        self.assertEqual((hinzu, entfernt), (0, 1))
        self.assertEqual(len(alt.naehte), 2)

    def _vorlage(self, d):
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SNP"
        for c in range(1, 16):
            ws.cell(7, c).value = "Muster"
        pfad = os.path.join(d, "vorlage.xlsx"); wb.save(pfad)
        return pfad

    def test_excel_erst_nach_vollstaendiger_pruefung(self):
        with tempfile.TemporaryDirectory() as d:
            vorlage = self._vorlage(d)
            z = beispiel_zeichnung()
            p = P.Projekt(basis="T", zeichnungen=[z])
            ziel = os.path.join(d, "out.xlsx")
            with self.assertRaises(ValueError) as cm:
                P.excel_schreiben(p, vorlage, ziel)
            self.assertIn("3", str(cm.exception))
            self.assertFalse(os.path.exists(ziel))
            P.bestaetigen(z.naehte[0]); P.aendern(z, z.naehte[1], angabe="HY16"); P.loeschen(z, z.naehte[2])
            man = P.neue_naht(z, 700, 700); P.aendern(z, man, art="Kehlnaht", angabe="a4", gruppe="Gr.22/23")
            self.assertTrue(p.vollstaendig_geprueft())
            self.assertEqual(P.excel_schreiben(p, vorlage, ziel), 3)
            ws = openpyxl.load_workbook(ziel)["SNP"]
            zeilen = [[ws.cell(r, c).value for c in (1, 2, 3, 5, 8, 15)] for r in range(7, 12)]
            self.assertEqual(zeilen[0][:5], ["PF60.100", "A01\n(1)", "HY-Naht", "HY15", "Gr.22/23"])
            self.assertEqual(zeilen[1][:4], ["PF60.100", "B03\n(2)", "Kehlnaht", "HY16"])
            self.assertEqual(zeilen[2][:5], ["PF60.100", "D04\n(4)", "Kehlnaht", "a4", "Gr.22/23"])
            self.assertIn("manuell ergänzt", zeilen[2][5])
            self.assertIsNone(zeilen[3][0])                       # gelöschte Naht fehlt, keine vierte Zeile
            self.assertNotIn("V20", [z_[3] for z_ in zeilen])


class AnsichtTests(unittest.TestCase):
    def test_zoom_um_punkt_bleibt_stehen(self):
        a = Ansicht((2000, 3000), (800, 600))
        px, py = 300, 200
        vor = a.zu_pt(px, py)
        a.zoom(2.0, px, py)
        nach = a.zu_pt(px, py)
        self.assertAlmostEqual(vor[0], nach[0], 6); self.assertAlmostEqual(vor[1], nach[1], 6)

    def test_grenzen_und_zentrieren(self):
        a = Ansicht((2000, 3000), (800, 600))
        for _ in range(30):
            a.zoom(2.0, 10, 10)
        self.assertLessEqual(a.scale, Ansicht.MAX_SCALE)
        for _ in range(60):
            a.zoom(0.5, 10, 10)
        self.assertGreaterEqual(a.scale, a.min_scale() - 1e-9)
        a.einpassen()
        a.zentrieren(500, 700, min_scale=1.5)
        self.assertGreaterEqual(a.scale, 1.5)
        self.assertTrue(a.sichtbar((480, 690, 520, 710)))

    def test_pdfseite_ausschnitt(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, "t.pdf")
            Image.new("RGB", (600, 800), "white").save(pdf, "PDF", resolution=72)
            s = PdfSeite(pdf)
            self.assertEqual((round(s.w), round(s.h)), (600, 800))
            img, (l, t) = s.bereich(-50, -50, 300, 200, 2.0)       # ragt über den Rand: wird gekürzt
            self.assertEqual((l, t), (0.0, 0.0)); self.assertEqual(img.size, (600, 400))
            self.assertEqual(s.bereich(700, 0, 800, 100, 1.0), (None, None))
            s.schliessen()


if __name__ == "__main__":
    unittest.main()
