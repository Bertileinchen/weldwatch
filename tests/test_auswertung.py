import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from weldwatch import auswertung, config
from weldwatch.symbols import Found


def seite(kind, size):
    return dict(kind=kind, size=size, segs=[])


class BeidseitigTests(unittest.TestCase):
    def lauf(self, up, down):
        f = Found(x0=100, x1=160, y=300, sides={"up": up, "down": down})
        return auswertung.build_entries([f], [], None, None, config.DEFAULTS)

    def test_gleiche_seiten_eine_zeile(self):
        e = self.lauf(seite("Kehlnaht", "a3"), seite("Kehlnaht", "a3"))
        self.assertEqual(len(e), 1)
        self.assertEqual((e[0].art, e[0].angabe), ("Kehlnaht", "a3\na3"))
        self.assertIn("beidseitig", e[0].bemerkung)

    def test_verschiedene_naht_getrennt(self):
        e = self.lauf(seite("HY-Naht", "15"), seite("Kehlnaht", "a3"))
        self.assertEqual([(x.art, x.angabe) for x in e], [("HY-Naht", "HY15"), ("Kehlnaht", "a3")])
        self.assertTrue(all("beidseitig" not in x.bemerkung for x in e))
        self.assertEqual([x.nr for x in e], [1, 2])

    def test_gleiche_art_anderes_mass_getrennt(self):
        e = self.lauf(seite("Kehlnaht", "a3"), seite("Kehlnaht", "a4"))
        self.assertEqual([x.angabe for x in e], ["a3", "a4"])

    def test_einseitig_unveraendert(self):
        f = Found(x0=100, x1=160, y=300, sides={"up": seite("V-Naht", "20")})
        e = auswertung.build_entries([f], [], None, None, config.DEFAULTS)
        self.assertEqual((len(e), e[0].angabe, e[0].dicke, e[0].bemerkung), (1, "V20", "", []))


if __name__ == "__main__":
    unittest.main()
