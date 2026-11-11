"""Rauchtest des Prüf-Fensters: baut das Fenster, geht den ganzen Prüfablauf durch und erstellt die Excel-Liste.
Läuft in GitHub Actions auf Windows mit echtem Tk (python tests/gui_smoke.py). Dialoge werden durch feste Antworten ersetzt."""
import os, sys, tempfile, time, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import openpyxl
from PIL import Image, ImageDraw
from weldwatch import gui, lauf, projekt as P
from tests.test_projekt import beispiel_zeichnung
from tests.test_speichern import vorlage_machen, PruefklassenTests

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
        vorlage_machen(vorlage)
        os.makedirs(os.path.join(d, "proj"))
        ziel = os.path.join(d, "proj", "out.xlsx")
        speicher_ziel = os.path.join(d, "proj", "t.wwp")
        dialoge = []

        def save_dialog(*a, **k):
            if k.get("defaultextension") == ".xlsx":
                return ziel
            dialoge.append(1)
            return speicher_ziel
        gui.filedialog.asksaveasfilename = save_dialog
        gui.filedialog.askopenfilename = lambda *a, **k: vorlage
        p = P.Projekt(basis="Rauchtest", zeichnungen=[z], pfad="", vorlage=vorlage, eingabe=pdf)

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
        pruefe(p.pfad == "" and os.path.exists(lauf.sicherung_pfad("Rauchtest")),
               "vor dem ersten Speichern gibt es nur eine Sicherungsdatei")
        pruefe(len(app.extra_vars) >= 6 and "G" not in app.extra_vars and "I" in app.extra_vars,
               "Eingabefelder für die weiteren Excel-Spalten (ohne WPS-Spalte)")
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

        # Erstes Speichern: Dialog, PDFs ins Projekt, danach nur noch überspeichern
        app.speichern()
        pruefe(len(dialoge) == 1 and p.pfad == speicher_ziel and os.path.exists(speicher_ziel), "erstes Speichern fragt nach dem Speicherort")
        pruefe(p.pdfs_kopiert and z.pfad.startswith(os.path.join(d, "proj", "Zeichnungen")) and os.path.exists(z.pfad),
               "Zeichnung wurde ins Projekt kopiert")
        pruefe(not os.path.exists(lauf.sicherung_pfad("Rauchtest")), "Sicherungsdatei entfernt")
        pruefe(app.seite is not None, "PDF nach dem Kopieren wieder geöffnet")
        pruefe(lauf.finde_projekt(pdf) == speicher_ziel, "Speicherort ist für den nächsten Start gemerkt")
        app.speichern()
        pruefe(len(dialoge) == 1, "zweites Speichern ohne Dialog")
        q = P.Projekt.laden(p.pfad)
        pruefe([n.to_dict() for n in q.zeichnungen[0].naehte] == [n.to_dict() for n in z.naehte], "Projektdatei enthält den Prüfstand")

        # weitere Excel-Spalten: ändern den Status nicht, "alle" füllt die Zeichnung
        erste = min(z.aktive(), key=lambda m: m.nr)
        app.waehle(erste.id)
        status_vorher = erste.status
        app.extra_vars["I"].set("WPQR-7"); app.extra_vars["L"].set("100 % VT")
        app.waehle(z.aktive()[-1].id)
        pruefe(erste.extra == {"I": "WPQR-7", "L": "100 % VT"} and erste.status == status_vorher,
               "weitere Spalten übernommen, Status unverändert")
        app.extra_vars["J"].set("AP-1"); app.extra_fuer_alle("J")
        pruefe(all(n.extra.get("J") == "AP-1" for n in z.aktive()), "'alle'-Knopf trägt bei allen Nähten ein")
        app.waehle(erste.id)
        pruefe(app.extra_vars["I"].get() == "WPQR-7" and app.extra_vars["J"].get() == "AP-1", "Felder zeigen die gespeicherten Werte")

        # Excel jetzt
        pruefe(p.vollstaendig_geprueft(), "alles geprüft")
        meldungen.clear()
        app.excel_exportieren()
        pruefe(os.path.exists(ziel), "Excel-Datei erstellt (im Projektordner)")
        ws = openpyxl.load_workbook(ziel)["SNP"]
        pruefe(ws.cell(7, 1).value == "PF60.100" and ws.cell(10, 1).value is not None and ws.cell(11, 1).value is None,
               "Excel enthält 4 Nähte")
        pruefe(ws["I7"].value == "WPQR-7" and ws["L7"].value == "100 % VT" and ws["J7"].value == "AP-1" and ws["J10"].value == "AP-1",
               "weitere Spalten stehen in der Excel-Datei")
        t0 = time.time()
        while app.busy and time.time() - t0 < 120:
            root.update(); time.sleep(0.1)
        pdf_ordner = os.path.join(d, "proj", "out_Pruef-PDFs")
        pruefe(not app.busy and os.path.isfile(os.path.join(pdf_ordner, "zeichnung_Pruefung.pdf")), "Prüf-PDFs im Unterordner exportiert")

        # Zeichnung umschalten, auch wenn die aktuelle nicht fertig ist
        pdf2 = os.path.join(d, "zweite.pdf")
        Image.new("RGB", (1200, 1200), "white").save(pdf2, "PDF", resolution=72)
        z2 = beispiel_zeichnung(pdf2)
        p.zeichnungen.append(z2)
        app._combo_aktualisieren()
        pruefe(len(app.tab_btns) == 2, "Reiter für beide Zeichnungen")
        app.zeichnung_weiter(1)
        pruefe(app.z is z2 and app.sel is not None, "weiter zur nächsten Zeichnung")
        app.zeichnung_weiter(1)
        pruefe(app.z is z, "wieder zurück (Umlauf), obwohl die zweite nicht fertig war")
        app.zeichnung_nr(1); app.zeichnung_weiter(-1)
        pruefe(app.z is z, "Umschalten per Nummer und rückwärts")
        p.zeichnungen.remove(z2)
        app._combo_aktualisieren()

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
        # Güte-/Prüfklasse: Standard, Auswahl bestimmt Prüfklasse und Prüfumfang
        v2 = os.path.join(d, "v2.xlsx"); PruefklassenTests().vorlage(v2)
        for n in z.naehte:
            n.extra.clear()
        p.vorlage = v2; app._extras_aufbauen()
        app.waehle(next(n for n in z.aktive() if "I" not in n.extra).id)
        cp, ct = app._spalte("cp"), app._spalte("ct")
        pruefe(app.extra_vars[cp].get() == "CP C2" and app.extra_vars[ct].get() == "CT 3" and app.x_umfang["ut"].get() == "-",
               "Standard CP C2 / CT 3 mit Prüfumfang")
        app.extra_vars[cp].set("CP A"); app._klasse_gewaehlt("cp")
        pruefe(app.extra_vars[ct].get() == "CT 1" and app.x_umfang["mt"].get() == "100%", "Güteklasse bestimmt Prüfklasse und Prüfumfang")
        app.extra_fuer_alle(cp)
        pruefe(all(n.extra.get(cp) == "CP A" and n.extra.get(ct) == "CT 1" for n in z.aktive()), "Güteklasse für alle Nähte")


        # Filter: "alle"-Knöpfe wirken nur auf angezeigte Nähte
        for n in z.naehte:
            n.extra.clear()
        app._form_fuellen(app._naht())
        art0 = z.aktive()[0].art
        app.filter_vars["art"].set(art0); app._filter_geaendert()
        angez = [n for n in z.aktive() if n.art == art0]
        pruefe(0 < len(angez) < len(z.aktive()) and {n.id for n in app._gefiltert()} == {n.id for n in angez}, "Filter blendet Nähte aus")
        werte = [str(w) for w in app.filter_cbs["art"].cget("values")]
        pruefe(art0 in werte and gui.ALLE in werte, "Filterliste enthält die Werte")
        app.waehle(angez[0].id)
        app.extra_vars[cp].set("CP A"); app._klasse_gewaehlt("cp"); app.extra_fuer_alle(cp)
        pruefe(all(n.extra.get(cp) == "CP A" and n.extra.get(ct) == "CT 1" for n in angez), "'alle' trägt bei den angezeigten Nähten ein")
        pruefe(all(cp not in n.extra for n in z.aktive() if n not in angez), "'alle' lässt ausgeblendete Nähte unberührt")
        for n in z.aktive():
            n.status = P.OFFEN
        app._liste_fuellen()
        app.alle_bestaetigen()
        pruefe(all(n.status == P.BESTAETIGT for n in angez) and all(n.status == P.OFFEN for n in z.aktive() if n not in angez),
               "'Alle bestätigen' nur für angezeigte Nähte")
        app._filter_loeschen()
        pruefe(len(app._gefiltert()) == len(z.aktive()), "Filter löschen")

        # stabile Nummern: neue Naht bekommt die nächste Nummer, nichts wird neu nummeriert
        vor = {n.id: n.nr for n in z.aktive()}
        mn = P.neue_naht(z, 50, 50)
        pruefe(mn.nr == max(vor.values()) + 1 and all(n.nr == vor[n.id] for n in z.aktive() if n.id in vor), "von Hand gesetzte Naht: nächste Nummer, andere unverändert")
        P.loeschen(z, mn)

        # Zeichnungen hinzufügen (Ordner) und entfernen
        zus = os.path.join(d, "zusatz"); os.makedirs(zus)
        Image.new("RGB", (1200, 1200), "white").save(os.path.join(zus, "dritte.pdf"), "PDF", resolution=72)
        gui.filedialog.askdirectory = lambda *a, **k: zus
        anz0 = len(p.zeichnungen)
        app.ordner_hinzufuegen()
        t0 = time.time()
        while app.busy and time.time() - t0 < 180:
            root.update(); time.sleep(0.1)
        pruefe(len(p.zeichnungen) == anz0 + 1, "Ordner zum Projekt hinzugefügt")
        app.zeichnung_nr(len(p.zeichnungen) - 1)
        app.zeichnung_entfernen()
        pruefe(len(p.zeichnungen) == anz0 and app.z in p.zeichnungen, "Zeichnung entfernt")
        app.hilfe_zeigen(); app.changelog_zeigen()
        pruefe(True, "Hilfe und Changelog öffnen")

        # Beenden: ungespeichertes Projekt fragt nach
        ende = []
        orig = root.destroy
        root.destroy = lambda: (ende.append(1), orig())
        p.pfad = ""
        gui.messagebox.askyesnocancel = lambda *a, **k: None
        app.beenden()
        pruefe(not ende, "Abbrechen beim Beenden lässt das Fenster offen")
        gui.messagebox.askyesnocancel = lambda *a, **k: False
        app.beenden()
        pruefe(ende, "Beenden ohne Speichern")
    print("\nFehler:", len(FALSCH))
    return 1 if FALSCH else 0


if __name__ == "__main__":
    sys.exit(main())
