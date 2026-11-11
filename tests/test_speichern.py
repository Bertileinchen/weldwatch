import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import openpyxl
from PIL import Image
from weldwatch import lauf, output, projekt as P
from tests.test_projekt import beispiel_zeichnung


def pdf_machen(pfad, groesse=(1200, 1200)):
    Image.new("RGB", groesse, "white").save(pfad, "PDF", resolution=72)


def vorlage_machen(pfad):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SNP"
    kopf = {"A": "Zeichnung", "B": "Planquadrat", "C": "Nahtart", "D": "Dicke", "E": "Angabe", "F": "Stoßart", "G": "WPS",
            "H": "Grundwerkstoff", "I": "WPQR", "J": "Arbeitsprobe", "K": "Klasse", "L": "Prüfumfang", "M": "Prüfart", "N": "Datum", "O": "Bemerkung"}
    for b, t in kopf.items():
        ws[f"{b}6"] = t
    ws["L5"] = "Prüfung"; ws.merge_cells("L5:M5")      # Gruppenüberschrift darüber darf die Einzelüberschrift nicht verdrängen
    for c in range(1, 16):
        ws.cell(7, c).value = "Muster"
    wb.save(pfad)


class SpaltenTests(unittest.TestCase):
    def test_vorlage_spalten(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.xlsx"); vorlage_machen(v)
            labels, wps = output.vorlage_spalten(v)
            self.assertEqual((labels["I"], labels["L"], labels["M"], wps), ("WPQR", "Prüfumfang", "Prüfart", "G"))
            self.assertEqual([b for b, _ in output.zusatz_spalten(labels, wps)], ["F", "I", "J", "K", "L", "M", "N"])

    def test_fehlende_ueberschrift_hat_ersatztext(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.xlsx")
            wb = openpyxl.Workbook(); wb.active.title = "SNP"; wb.save(v)
            labels, wps = output.vorlage_spalten(v)
            self.assertEqual((labels["I"], wps), ("Spalte I", None))

    def test_extras_aendern_status_nicht_und_gehen_in_excel(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.xlsx"); vorlage_machen(v)
            z = beispiel_zeichnung()
            n = z.naehte[0]
            P.extras_setzen(n, {"I": "WPQR-12", "J": "AP-3", "L": " 100% VT ", "K": ""})
            self.assertEqual(n.status, P.OFFEN)
            self.assertEqual(n.extra, {"I": "WPQR-12", "J": "AP-3", "L": "100% VT"})
            n.wps = "Winkel 60°"
            self.assertEqual(P.extra_fuer_alle(z, "M", "VT"), 3)
            for m in z.naehte:
                P.bestaetigen(m)
            p = P.Projekt(basis="T", zeichnungen=[z])
            ziel = os.path.join(d, "o.xlsx")
            P.excel_schreiben(p, v, ziel)
            ws = openpyxl.load_workbook(ziel)["SNP"]
            self.assertEqual([ws["I7"].value, ws["J7"].value, ws["L7"].value, ws["M7"].value, ws["G7"].value],
                             ["WPQR-12", "AP-3", "100% VT", "VT", "Winkel 60°"])
            self.assertIsNone(ws["I8"].value)                 # andere Nähte ohne Eintrag
            self.assertEqual(ws["M9"].value, "VT")

    def test_extras_ueberleben_speichern_und_neulauf(self):
        with tempfile.TemporaryDirectory() as d:
            z = beispiel_zeichnung()
            P.extras_setzen(z.naehte[0], {"I": "X1"})
            p = P.Projekt(zeichnungen=[z]); p.speichern(os.path.join(d, "t.wwp"))
            q = P.Projekt.laden(os.path.join(d, "t.wwp"))
            self.assertEqual(q.zeichnungen[0].naehte[0].extra, {"I": "X1"})
            neu = beispiel_zeichnung()
            P.zusammenfuehren(q.zeichnungen[0], neu)          # offene Naht wird durch Neuerkennung ersetzt, Eingaben bleiben
            self.assertEqual(q.zeichnungen[0].naehte[0].extra, {"I": "X1"})


class PruefklassenTests(unittest.TestCase):
    def vorlage(self, pfad):
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SNP"
        kopf = {"A": "Zeichnung", "B": "Planquadrat", "C": "Nahtart", "D": "Dicke", "E": "Angabe", "G": "WPS", "H": "Grundwerkstoff",
                "I": "Schweißnahtgüteklasse", "J": "Schweißnahtprüfklasse", "K": "Volumetrische Prüfungen UT",
                "L": "Oberflächenprüfungen MT", "M": "Sichtprüfung VT", "O": "Bemerkung"}
        for b, t in kopf.items():
            ws[f"{b}6"] = t
        ws["I5"] = "Prüfumfang"
        wb.save(pfad)

    def test_tabelle(self):
        from weldwatch import pruefklassen as K
        self.assertEqual(K.umfang("CT 1"), ("100%", "100%", "100%"))
        self.assertEqual(K.umfang("CT 2"), ("10%", "10%", "100%"))
        self.assertEqual(K.umfang("CT 4"), ("-", "-", "100%"))
        self.assertEqual((K.CP_ZU_CT["CP B1"], K.CP_ZU_CT["CP D"]), ("CT 2", "CT 4"))
        self.assertEqual(K.umfang("irgendwas"), ("", "", ""))

    def test_excel_standard_und_auswahl(self):
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "v.xlsx"); self.vorlage(v)
            z = beispiel_zeichnung()
            P.extras_setzen(z.naehte[1], {"I": "CP A", "J": "CT 1"})
            P.extras_setzen(z.naehte[2], {"I": "CP B2", "J": "CT 2"})
            z.naehte[0].bemerkung = ["beidseitig", "interne Bezeichnung VH20-100 / VH20-100"]
            for n in z.naehte:
                P.bestaetigen(n)
            ziel = os.path.join(d, "o.xlsx")
            P.excel_schreiben(P.Projekt(basis="T", zeichnungen=[z]), v, ziel)
            ws = openpyxl.load_workbook(ziel)["SNP"]
            zeile = lambda r: [ws.cell(r, c).value for c in range(9, 14)]
            self.assertEqual(zeile(7), ["CP C2", "CT 3", "-", "-", "100%"])          # Standard
            self.assertEqual(zeile(8), ["CP A", "CT 1", "100%", "100%", "100%"])
            self.assertEqual(zeile(9), ["CP B2", "CT 2", "10%", "10%", "100%"])
            self.assertEqual(ws["O7"].value, "beidseitig;\ninterne Bezeichnung VH20-100 / VH20-100")
            self.assertTrue(ws["O7"].alignment.wrap_text)


class SpeichernTests(unittest.TestCase):
    def test_sicherung_setzt_speicherort_nicht(self):
        with tempfile.TemporaryDirectory() as d:
            p = P.Projekt(zeichnungen=[beispiel_zeichnung()])
            p.speichern(os.path.join(d, "s", "sicherung.wwp"), merke=False)
            self.assertEqual(p.pfad, "")
            p.speichern(os.path.join(d, "t.wwp"))
            self.assertEqual(p.pfad, os.path.join(d, "t.wwp"))

    def test_pdfs_kopieren(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "a")); os.makedirs(os.path.join(d, "b")); os.makedirs(os.path.join(d, "proj"))
            pa, pb = os.path.join(d, "a", "x.pdf"), os.path.join(d, "b", "x.pdf")
            pdf_machen(pa); pdf_machen(pb, (600, 600))
            z1, z2 = beispiel_zeichnung(pa), beispiel_zeichnung(pb)
            z3 = beispiel_zeichnung(os.path.join(d, "fehlt.pdf"))
            p = P.Projekt(basis="T", zeichnungen=[z1, z2, z3])
            kopiert, fehlt = P.pdfs_kopieren(p, os.path.join(d, "proj"))
            self.assertEqual(sorted(kopiert), ["x.pdf", "x_2.pdf"])
            self.assertEqual(fehlt, ["fehlt.pdf"])
            self.assertTrue(p.pdfs_kopiert)
            self.assertEqual(z1.original, pa)
            self.assertTrue(z1.pfad.startswith(os.path.join(d, "proj", "Zeichnungen")))
            os.remove(pa); os.remove(pb)                            # Originale weg -> Projekt trotzdem vollständig
            p.speichern(os.path.join(d, "proj", "t.wwp"))
            q = P.Projekt.laden(os.path.join(d, "proj", "t.wwp"))
            self.assertTrue(os.path.exists(q.zeichnungen[0].pfad) and os.path.exists(q.zeichnungen[1].pfad))
            self.assertIs(q.zeichnung_zu_pfad(pa), q.zeichnungen[0])  # Originalpfad findet weiter die Zeichnung
            self.assertEqual(P.pdfs_kopieren(q, os.path.join(d, "proj"))[0], [])   # zweites Mal: nichts mehr zu tun

    def test_projektordner_verschieben(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "alt"))
            pdf_machen(os.path.join(d, "alt", "x.pdf"))
            p = P.Projekt(basis="T", zeichnungen=[beispiel_zeichnung(os.path.join(d, "alt", "x.pdf"))])
            P.pdfs_kopieren(p, os.path.join(d, "alt")); p.speichern(os.path.join(d, "alt", "t.wwp"))
            os.rename(os.path.join(d, "alt"), os.path.join(d, "neu"))
            q = P.Projekt.laden(os.path.join(d, "neu", "t.wwp"))
            self.assertTrue(os.path.exists(q.zeichnungen[0].pfad), q.zeichnungen[0].pfad)

    def test_pruef_pdfs(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, "x.pdf"); pdf_machen(pdf)
            z = beispiel_zeichnung(pdf)
            for n in z.naehte:
                P.bestaetigen(n)
            P.loeschen(z, z.naehte[2])
            p = P.Projekt(basis="T", zeichnungen=[z, beispiel_zeichnung(os.path.join(d, "fehlt.pdf"))])
            a = P.pruef_auftraege(p)
            self.assertEqual([len(x["items"]) for x in a], [2, 3])      # gelöschte Naht erscheint nicht
            out = os.path.join(d, "T_Pruef-PDFs")
            ok, fehler = P.pruef_pdfs_schreiben(a, out, scale=0.5)
            self.assertEqual([os.path.basename(f) for f in ok], ["x_Pruefung.pdf"])
            self.assertEqual(len(fehler), 1)
            self.assertGreater(os.path.getsize(ok[0]), 500)

    def test_merkliste(self):
        with tempfile.TemporaryDirectory() as d:
            alt = lauf.ausgabe_ordner
            lauf.ausgabe_ordner = lambda: d
            try:
                eingabe = os.path.join(d, "Rahmen")
                self.assertIsNone(lauf.finde_projekt(eingabe))
                s = lauf.sicherung_pfad("Rahmen")
                os.makedirs(os.path.dirname(s)); open(s, "w").close()
                self.assertEqual(lauf.finde_projekt(eingabe), s)           # Sicherung wird gefunden
                ziel = os.path.join(d, "mein", "projekt.wwp")
                os.makedirs(os.path.dirname(ziel)); open(ziel, "w").close()
                lauf.merke_projekt(eingabe, ziel)
                self.assertEqual(lauf.finde_projekt(eingabe), ziel)        # gespeichertes Projekt hat Vorrang
                os.remove(ziel)
                self.assertEqual(lauf.finde_projekt(eingabe), s)
            finally:
                lauf.ausgabe_ordner = alt


if __name__ == "__main__":
    unittest.main()
