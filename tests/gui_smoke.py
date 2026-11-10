"""Rauchtest des Prüf-Fensters: baut das Fenster, geht den ganzen Prüfablauf durch und erstellt die Excel-Liste.
Läuft in GitHub Actions auf Windows mit echtem Tk (python tests/gui_smoke.py). Dialoge werden durch feste Antworten ersetzt."""
import os, sys, tempfile, time, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import openpyxl
from PIL import Image, ImageDraw
from weldwatch import gui, lauf, projekt as P
from tests.test_projekt import beispiel_zeichnung

FALSCH = []


def pruefe(bed, text):
    print(("ok    " if bed else "FEHLER"), text)
    if not bed:
        FALSCH.append(text)


def ev(x, y, **kw):
    return types.SimpleNamespace(x=x, y=y, num=kw.get("num", 1), delta=kw.get("delta", 0))


def main():
    meldungen = []
    gui.messagebox.showinfo = lambda *a, **k: meldungen.append(("info", a))
    gui.messagebox.showwarning = lambda *a, **k: meldungen.append(("warn", a))
    gui.messagebox.showerror = lambda *a, **k: meldungen.append(("fehler", a))
    gui.messagebox.askyesno = lambda *a, **k: True
    gui.messagebox.askyesnocancel = lambda *a, **k: False
    with tempfile.TemporaryDirectory() as d:
        lauf.ausgabe_ordner = lambda: d
        pdf = os.path.join(d, "zeichnung.pdf")
        img = Image.new("RGB", (1200, 1200), "white")
        dr = ImageDraw.Draw(img)
        z = beispiel_zeichnung(pdf)
        for n in z.naehte:
            dr.rectangle(n.box, outline="black")
        img.save(pdf, "PDF", resolution=72)
        z.seite = (1200.0, 1200.0)
        vorlage = os.path.join(d, "vorlage.xlsx")
        wb = openpyxl.Workbook(); wb.active.title = "SNP"
        for c in range(1, 16):
            wb.active.cell(7, c).value = "Muster"
        wb.save(vorlage)
        p = P.Projekt(basis="Rauchtest", zeichnungen=[z], pfad=os.path.join(d, "t.wwp"), vorlage=vorlage)

        root = gui.neues_fenster()
        app = gui.App(root)
        root.update()
        app.projekt_setzen(p)
        root.update()
        pruefe(app.seite is not None, "PDF-Seite geöffnet")
        pruefe(len(app.canvas.find_withtag("bg")) >= 1, "Zeichnung wird angezeigt")
        pruefe(len(app.canvas.find_withtag("ov")) > 0, "Markierungen werden gezeichnet")
        pruefe(app.sel is not None and app._naht().nr == 1, "erste offene Naht ist gewählt")
        pruefe(len(app.tree.get_children()) == 3, "Liste zeigt 3 Nähte")

        # Zoom, Verschieben, Klick auf eine Markierung
        app.ganze_seite(); app.zoom_schritt(1.4)
        app._rad(ev(300, 300, delta=120)); root.update()
        app._zeichnen_alles()
        zweite = z.naehte[1]
        app.ansicht.zentrieren((zweite.box[0] + zweite.box[2]) / 2, (zweite.box[1] + zweite.box[3]) / 2, min_scale=1.0)
        app._zeichnen_alles()
        px, py = app.ansicht.zu_px(zweite.x, zweite.y)
        app._druck(ev(px, py)); app._los(ev(px, py))
        pruefe(app.sel == zweite.id, "Klick auf Markierung wählt die Naht")
        app._druck(ev(5, 5)); app._zug(ev(40, 40)); app._los(ev(40, 40))
        pruefe(True, "Verschieben läuft durch")

        # Bestätigen -> nächste offene
        erste = z.naehte[0]
        app.waehle(erste.id)
        app.naht_bestaetigen()
        pruefe(erste.status == P.BESTAETIGT, "bestätigt")
        pruefe(app.sel == z.naehte[1].id, "springt zur nächsten offenen Naht")

        # Ändern durch Wechsel der Auswahl
        app.v["art"].set("V-Naht")
        app.t_angabe.delete("1.0", "end"); app.t_angabe.insert("1.0", "V16")
        app.waehle(z.naehte[2].id)
        pruefe(z.naehte[1].status == P.GEAENDERT and z.naehte[1].angabe == "V16" and z.naehte[1].art == "V-Naht",
               "Änderung wird beim Wechsel übernommen (geändert)")

        # Excel erst nach vollständiger Prüfung
        ziel = os.path.join(d, "out.xlsx")
        gui.filedialog.asksaveasfilename = lambda *a, **k: ziel
        gui.filedialog.askopenfilename = lambda *a, **k: vorlage
        meldungen.clear()
        app.excel_exportieren()
        pruefe(not os.path.exists(ziel) and any(m[0] == "warn" for m in meldungen), "Excel wird bei offenen Nähten verweigert")

        # Löschen, Neue Naht von Hand, Wiederherstellen
        app.waehle(z.naehte[2].id)
        app.naht_loeschen()
        geloescht = [n for n in z.naehte if n.status == P.GELOESCHT]
        pruefe(len(geloescht) == 1, "Naht gelöscht")
        app.neu_modus_umschalten()
        px, py = app.ansicht.zu_px(700, 700)
        app._druck(ev(px, py)); app._los(ev(px, py))
        neu = [n for n in z.naehte if n.status == P.MANUELL]
        pruefe(len(neu) == 1 and app.sel == neu[0].id, "neue Naht per Klick angelegt")
        meldungen.clear()
        app.excel_exportieren()
        pruefe(not os.path.exists(ziel), "leere neue Naht blockiert den Export")
        app.v["art"].set("Kehlnaht"); app.v["gruppe"].set("Gr.22/23")
        app.t_angabe.delete("1.0", "end"); app.t_angabe.insert("1.0", "a4")
        app.naht_bestaetigen()
        pruefe(not neu[0].offen, "neue Naht vollständig")
        app.neu_modus_umschalten()
        app._druck(ev(100, 100)); app._zug(ev(200, 180)); app._los(ev(200, 180))
        pruefe(len([n for n in z.naehte if n.status == P.MANUELL]) == 2, "neue Naht per aufgezogenem Rahmen")
        app.naht_loeschen()      # von Hand gesetzte, leere Naht wieder weg
        pruefe(len([n for n in z.naehte if n.status == P.MANUELL]) == 1, "manuelle Naht ganz entfernt")
        app.var_geloescht.set(True); app._geloescht_umschalten()
        app.waehle(geloescht[0].id)
        app.naht_loeschen()
        pruefe(geloescht[0].status == P.OFFEN, "gelöschte Naht wiederhergestellt")
        app.var_geloescht.set(False)
        app.waehle(geloescht[0].id); app.naht_bestaetigen()

        # Speichern/Laden
        app.speichern()
        q = P.Projekt.laden(p.pfad)
        pruefe([n.to_dict() for n in q.zeichnungen[0].naehte] == [n.to_dict() for n in z.naehte], "Projektdatei enthält den Prüfstand")

        # Excel jetzt
        pruefe(p.vollstaendig_geprueft(), "alles geprüft")
        meldungen.clear()
        app.excel_exportieren()
        pruefe(os.path.exists(ziel), "Excel-Datei erstellt")
        ws = openpyxl.load_workbook(ziel)["SNP"]
        pruefe(ws.cell(7, 1).value == "PF60.100" and ws.cell(10, 1).value is not None and ws.cell(11, 1).value is None,
               "Excel enthält 4 Nähte")

        # Erkennungslauf im Hintergrund (Rasterbild ohne Nähte) und Wiedereinlesen ohne Verlust
        vorher = [(n.id, n.status) for n in z.naehte]
        app._starte_lauf([pdf], ziel_projekt=p)
        t0 = time.time()
        while app.busy and time.time() - t0 < 180:
            root.update(); time.sleep(0.1)
        pruefe(not app.busy, "Erkennungslauf beendet")
        pruefe(p.zeichnungen[0].status == "ok", "Neulauf liefert Ergebnis")
        pruefe(sorted(vorher) == sorted((n.id, n.status) for n in p.zeichnungen[0].naehte),
               "Neulauf ändert weder Prüfstatus noch Nähte (geprüfte/manuelle bleiben)")
        app.beenden()
    print("\nFehler:", len(FALSCH))
    return 1 if FALSCH else 0


if __name__ == "__main__":
    sys.exit(main())
