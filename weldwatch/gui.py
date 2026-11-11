"""WeldWatch - Prüf-Fenster (Tkinter).

Zeichnung mit den erkannten Nähten anzeigen, Nähte anklicken und bearbeiten/löschen, fehlende Nähte von Hand setzen.
Die Excel-Liste gibt es erst, wenn alle Nähte geprüft sind. Alles wird laufend in der Projektdatei (.wwp) gesichert,
sodass die Erkennung nicht jedes Mal neu laufen muss. Ergebnisse der Erkennung sind Vorschläge zur Prüfung durch eine Person.
"""
import os, queue, sys, threading, time, traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox

from PIL import ImageTk

from . import lauf, output, pruefklassen
from . import projekt as P
from .pdfansicht import Ansicht, PdfSeite

try:   # Drag & Drop ist optional; ohne das Paket gibt es die Auswahl-Dialoge
    from tkinterdnd2 import TkinterDnD, DND_FILES
except Exception:   # pragma: no cover
    TkinterDnD = DND_FILES = None

ARTEN = ["Kehlnaht", "V-Naht", "HV-Naht", "Y-Naht", "HY-Naht", "I-Naht", "DV-Naht", "DHV-Naht", "DY-Naht", "DHY-Naht",
         "Symbol unbekannt"]
GRUPPEN = [f"Gr.{i}" for i in range(1, 12)] + ["Gr.21", "Gr.22/23", "Gr.24", "Gr.25", "Gr.26", "Gr.1 + Gr.8"]

FARBE_OFFEN = "#1e78d2"          # Vorschlag, Erkennung sicher
FARBE_PRUEFEN = "#ff8c00"        # Vorschlag, Erkennung unsicher
FARBE_STATUS = {P.BESTAETIGT: "#2e9e2e", P.GEAENDERT: "#00897b", P.MANUELL: "#8e24aa", P.GELOESCHT: "#9e9e9e"}
FARBE_AUSWAHL = "#e53935"
ZEILE_HINTERGRUND = {"offen": "#e3f0fc", "pruefen": "#ffe9cc", P.BESTAETIGT: "#e3f5e3", P.GEAENDERT: "#d9f2ef",
                     P.MANUELL: "#f1e0f5", P.GELOESCHT: "#f2f2f2"}

HILFE = """Farben der Markierungen
  blau      Vorschlag des Programms (noch ungeprüft)
  orange    Vorschlag, Erkennung unsicher - besonders genau prüfen
  grün      bestätigt
  türkis    von dir geändert
  violett   von dir selbst gesetzt
  grau      gelöscht (nur sichtbar mit "gelöschte zeigen")
  rot       aktuell gewählte Naht

Bedienung
  Mausrad = Zoom, linke Maustaste auf leerer Fläche ziehen (oder mittlere/rechte Taste) = Verschieben
  Naht anklicken = Daten rechts bearbeiten
  Strg+Enter (oder Enter in der Liste) = bestätigen und zur nächsten offenen Naht
  Entf = löschen   N = nächste offene   F = ganze Seite   A = neue Naht setzen (klicken oder Rahmen aufziehen)
  Strg+Bild auf / Bild ab = vorherige / nächste Zeichnung (oder Knöpfe / Reiter oben)
  Strg+S = speichern (beim ersten Mal mit 'Speichern unter'; danach wird die Projektdatei einfach aktualisiert)
  Reiter 'Weitere Excel-Spalten' = WPS, Arbeitsprobe, Prüfumfang usw. eintragen ('→ alle' = für die ganze Zeichnung)

Die Excel-Liste wird erst erstellt, wenn keine Naht mehr offen ist. Ergebnisse sind Vorschläge zur Prüfung durch eine Person."""


def farbe_naht(n):
    if n.status == P.OFFEN:
        return FARBE_OFFEN if n.ok else FARBE_PRUEFEN
    if n.unvollstaendig:
        return FARBE_PRUEFEN
    return FARBE_STATUS[n.status]


def zeilen_tag(n):
    if n.status == P.OFFEN or n.unvollstaendig:
        return "offen" if n.ok and not n.unvollstaendig else "pruefen"
    return n.status


class App:
    def __init__(self, root, projekt=None):
        self.root = root
        root.title("WeldWatch - Prüf-Fenster")
        root.geometry("1500x900")
        root.minsize(1000, 600)
        self.p = None                 # Projekt
        self.z = None                 # aktuelle Zeichnung
        self.sel = None               # id der gewählten Naht
        self.seite = None             # PdfSeite der aktuellen Zeichnung
        self.ansicht = Ansicht((1000.0, 1000.0), (800, 600))
        self.var_neu = tk.BooleanVar(value=False)
        self.var_nur_offen = tk.BooleanVar(value=False)
        self.var_geloescht = tk.BooleanVar(value=False)
        self.var_dn = tk.StringVar()
        self.var_status = tk.StringVar(value="Bereit.")
        self.var_zeichnung = tk.StringVar()
        self.busy = False
        self.q = queue.Queue()
        self._img = None
        self._job = None
        self._drag = None
        self._snap = None
        self._tree_sperre = False
        self._erst_fit = True
        self._lauf_ziel = None
        self._lauf_eingabe = None
        self._lauf_t0 = 0.0
        self._lauf_text = ""
        self._job_danach = None
        self._job_hinweis = ""
        self._job_titel = "Fehler"
        self.var_zi = tk.IntVar(value=0)
        self.tab_btns = []
        self.extra_vars = {}
        self.x_widgets = []
        self.x_rollen = {}
        self.x_umfang = {}
        self.wps_buchstabe = None
        self.f_fett = tkfont.nametofont("TkDefaultFont").copy()
        self.f_fett.configure(weight="bold")
        # Zeilenhöhe der Liste an die Schrift koppeln (bei skalierten Bildschirmen sonst überlagerte Zeilen)
        zeile = int(tkfont.nametofont("TkDefaultFont").metrics("linespace") * 1.45) + 2
        stil = ttk.Style(root)
        stil.configure("Treeview", rowheight=zeile)
        stil.configure("Treeview.Heading", padding=(2, 3))
        self._menue()
        self._aufbauen()
        self._tasten()
        self._dnd()
        root.protocol("WM_DELETE_WINDOW", self.beenden)
        self._zeichnen_alles()
        if projekt is not None:
            self.projekt_setzen(projekt)

    # ------------------------------------------------------------------------------------------------ Aufbau
    def _menue(self):
        m = tk.Menu(self.root)
        d = tk.Menu(m, tearoff=0)
        d.add_command(label="Öffnen (PDF oder Projekt) ...", command=self.dialog_oeffnen)
        d.add_command(label="Ordner mit Zeichnungen öffnen ...", command=self.dialog_ordner)
        d.add_command(label="Zeichnungen zum Projekt hinzufügen ...", command=self.zeichnungen_hinzufuegen)
        d.add_separator()
        d.add_command(label="Speichern", accelerator="Strg+S", command=self.speichern)
        d.add_command(label="Speichern unter ...", command=self.speichern_unter)
        d.add_separator()
        d.add_command(label="Excel-Prüfplan erstellen ...", command=self.excel_exportieren)
        d.add_command(label="Excel-Vorlage wählen ...", command=self.vorlage_waehlen)
        d.add_separator()
        d.add_command(label="Beenden", command=self.beenden)
        m.add_cascade(label="Datei", menu=d)
        b = tk.Menu(m, tearoff=0)
        b.add_command(label="Bestätigen und weiter", accelerator="Strg+Enter", command=self.naht_bestaetigen)
        b.add_command(label="Löschen / Wiederherstellen", accelerator="Entf", command=self.naht_loeschen)
        b.add_command(label="Neue Naht setzen", accelerator="A", command=self.neu_modus_umschalten)
        b.add_command(label="Nächste offene Naht", accelerator="N", command=self.naechste_offene)
        m.add_cascade(label="Bearbeiten", menu=b)
        a = tk.Menu(m, tearoff=0)
        a.add_command(label="Ganze Seite", accelerator="F", command=self.ganze_seite)
        a.add_command(label="Vergrößern", accelerator="+", command=lambda: self.zoom_schritt(1.4))
        a.add_command(label="Verkleinern", accelerator="-", command=lambda: self.zoom_schritt(1 / 1.4))
        a.add_separator()
        a.add_command(label="Vorherige Zeichnung", accelerator="Strg+Bild auf", command=lambda: self.zeichnung_weiter(-1))
        a.add_command(label="Nächste Zeichnung", accelerator="Strg+Bild ab", command=lambda: self.zeichnung_weiter(1))
        a.add_separator()
        a.add_command(label="Erkennung dieser Zeichnung wiederholen (Prüfung bleibt erhalten)", command=self.erkennung_wiederholen)
        m.add_cascade(label="Ansicht", menu=a)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Bedienung und Farben", command=lambda: messagebox.showinfo("Bedienung", HILFE, parent=self.root))
        m.add_cascade(label="Hilfe", menu=h)
        self.root.config(menu=m)

    def _aufbauen(self):
        tb = ttk.Frame(self.root, padding=(6, 4))
        tb.pack(side="top", fill="x")
        ttk.Button(tb, text="Öffnen ...", command=self.dialog_oeffnen).pack(side="left")
        ttk.Button(tb, text="Speichern", command=self.speichern).pack(side="left", padx=(4, 12))
        self.btn_neu = ttk.Checkbutton(tb, text="Neue Naht setzen (A)", variable=self.var_neu, command=self._neu_modus_geaendert,
                                       style="Toolbutton")
        self.btn_neu.pack(side="left")
        ttk.Button(tb, text="Nächste offene (N)", command=self.naechste_offene).pack(side="left", padx=4)
        ttk.Button(tb, text="Ganze Seite (F)", command=self.ganze_seite).pack(side="left")
        ttk.Button(tb, text="+", width=3, command=lambda: self.zoom_schritt(1.4)).pack(side="left", padx=(8, 0))
        ttk.Button(tb, text="-", width=3, command=lambda: self.zoom_schritt(1 / 1.4)).pack(side="left")
        ttk.Button(tb, text="◀ Zeichnung", command=lambda: self.zeichnung_weiter(-1)).pack(side="left", padx=(12, 0))
        ttk.Button(tb, text="Zeichnung ▶", command=lambda: self.zeichnung_weiter(1)).pack(side="left", padx=(2, 0))
        self.btn_excel = ttk.Button(tb, text="Excel-Prüfplan erstellen ...", command=self.excel_exportieren)
        self.btn_excel.pack(side="right")
        self.lbl_offen = ttk.Label(tb, text="", font=self.f_fett)
        self.lbl_offen.pack(side="right", padx=12)

        self.tabs = ttk.Frame(self.root, padding=(6, 0))
        self.tabs.pack(side="top", fill="x")

        sb = ttk.Frame(self.root, padding=(6, 2))
        sb.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(sb, mode="indeterminate", length=160)
        ttk.Label(sb, textvariable=self.var_status).pack(side="left")
        self.progress.pack(side="right")

        pw = ttk.PanedWindow(self.root, orient="horizontal")
        pw.pack(side="top", fill="both", expand=True)
        links = ttk.Frame(pw)
        rechts = ttk.Frame(pw, padding=6)
        pw.add(links, weight=4)
        pw.add(rechts, weight=1)

        self.canvas = tk.Canvas(links, bg="#cfcfcf", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        c = self.canvas
        c.bind("<Configure>", self._groesse)
        c.bind("<ButtonPress-1>", self._druck)
        c.bind("<B1-Motion>", self._zug)
        c.bind("<ButtonRelease-1>", self._los)
        for t in (2, 3):
            c.bind(f"<ButtonPress-{t}>", self._druck_pan)
            c.bind(f"<B{t}-Motion>", self._zug)
            c.bind(f"<ButtonRelease-{t}>", self._los)
        c.bind("<MouseWheel>", self._rad)
        c.bind("<Button-4>", self._rad)
        c.bind("<Button-5>", self._rad)

        rechts.columnconfigure(0, weight=1)
        r = 0
        ttk.Label(rechts, text="Zeichnung").grid(row=r, column=0, sticky="w")
        r += 1
        self.cb_zeichnung = ttk.Combobox(rechts, textvariable=self.var_zeichnung, state="readonly")
        self.cb_zeichnung.grid(row=r, column=0, sticky="ew")
        self.cb_zeichnung.bind("<<ComboboxSelected>>", self._zeichnung_gewaehlt)
        r += 1
        zn = ttk.Frame(rechts)
        zn.grid(row=r, column=0, sticky="ew", pady=(4, 0))
        zn.columnconfigure(1, weight=1)
        ttk.Label(zn, text="Zeichnungsnr. (Spalte A)").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.e_dn = ttk.Entry(zn, textvariable=self.var_dn)
        self.e_dn.grid(row=0, column=1, sticky="ew")
        self.e_dn.bind("<Return>", self._dn_uebernehmen)
        self.e_dn.bind("<FocusOut>", self._dn_uebernehmen)
        r += 1
        self.lbl_info = ttk.Label(rechts, text="", wraplength=420, foreground="#a05a00", justify="left")
        self.lbl_info.grid(row=r, column=0, sticky="ew", pady=(2, 2))
        r += 1
        fl = ttk.Frame(rechts)
        fl.grid(row=r, column=0, sticky="ew")
        ttk.Checkbutton(fl, text="nur offene", variable=self.var_nur_offen, command=self._liste_fuellen).pack(side="left")
        ttk.Checkbutton(fl, text="gelöschte zeigen", variable=self.var_geloescht, command=self._geloescht_umschalten).pack(side="left", padx=8)
        r += 1
        tf = ttk.Frame(rechts)
        tf.grid(row=r, column=0, sticky="nsew")
        rechts.rowconfigure(r, weight=1)
        spalten = (("nr", "Nr", 38), ("q", "Quadr.", 52), ("art", "Nahtart", 86), ("angabe", "Angabe", 110),
                   ("gr", "Gruppe", 64), ("status", "Status", 78))
        self.tree = ttk.Treeview(tf, columns=[s[0] for s in spalten], show="headings", selectmode="browse", height=12)
        for k, t, w in spalten:
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, minwidth=30, stretch=(k == "angabe"))
        sc = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sc.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")
        for tag, farbe in ZEILE_HINTERGRUND.items():
            self.tree.tag_configure(tag, background=farbe)
        self.tree.tag_configure(P.GELOESCHT, foreground="#8a8a8a")
        self.tree.bind("<<TreeviewSelect>>", self._tree_gewaehlt)

        r += 1
        self.nb = ttk.Notebook(rechts)
        self.nb.grid(row=r, column=0, sticky="ew", pady=(6, 0))
        form = ttk.Frame(self.nb, padding=6)
        form.columnconfigure(1, weight=1)
        self.nb.add(form, text="Naht")
        self.extra_tab = ttk.Frame(self.nb, padding=6)
        self.extra_tab.columnconfigure(1, weight=1)
        self.nb.add(self.extra_tab, text="Weitere Excel-Spalten")
        self.v = {k: tk.StringVar() for k in ("square", "art", "stoss", "dicke", "gruppe", "wps", "bem")}
        self.f_widgets = []
        zeile = 0

        def feld(text, widget):
            nonlocal zeile
            lbl = ttk.Label(form, text=text)
            lbl.grid(row=zeile, column=0, sticky="nw", padx=(0, 6), pady=1)
            widget._lbl = lbl
            widget.grid(row=zeile, column=1, sticky="ew", pady=1)
            self.f_widgets.append(widget)
            zeile += 1
            return widget

        self.e_square = feld("Planquadrat", ttk.Entry(form, textvariable=self.v["square"], width=8))
        self.c_art = feld("Nahtart", ttk.Combobox(form, textvariable=self.v["art"], values=ARTEN))
        self.c_stoss = feld("Zusatz Nahtart", ttk.Combobox(form, textvariable=self.v["stoss"], values=["", "T-Stoß"]))
        self.e_dicke = feld("Dicke (Sp. D)", ttk.Entry(form, textvariable=self.v["dicke"], width=8))
        self.t_angabe = feld("Zeichnungs-\nangabe", tk.Text(form, height=3, width=26, wrap="word", undo=True))
        self.c_gruppe = feld("Werkstoffgruppe", ttk.Combobox(form, textvariable=self.v["gruppe"], values=GRUPPEN))
        self.e_wps = feld("WPS\n(vorbelegt: Winkel)", ttk.Entry(form, textvariable=self.v["wps"], width=16))
        self.e_bem = feld("Bemerkung\n(mit ; trennen)", ttk.Entry(form, textvariable=self.v["bem"]))
        self.lbl_quelle = ttk.Label(form, text="", foreground="#555555", wraplength=330, justify="left")
        self.lbl_quelle.grid(row=zeile, column=0, columnspan=2, sticky="w", pady=(4, 0))
        for w in (self.e_square, self.c_art, self.c_stoss, self.e_dicke, self.c_gruppe, self.e_wps, self.e_bem):
            w.bind("<Return>", lambda e: (self.naht_bestaetigen(), "break")[1])
        self.t_angabe.bind("<Control-Return>", lambda e: (self.naht_bestaetigen(), "break")[1])

        r += 1
        bf = ttk.Frame(rechts)
        bf.grid(row=r, column=0, sticky="ew", pady=(6, 0))
        self.btn_ok = ttk.Button(bf, text="Bestätigen und weiter (Strg+Enter)", command=self.naht_bestaetigen)
        self.btn_ok.pack(side="left", fill="x", expand=True)
        self.btn_del = ttk.Button(bf, text="Löschen (Entf)", command=self.naht_loeschen)
        self.btn_del.pack(side="left", padx=(6, 0))
        self._extras_aufbauen()
        self._form_fuellen(None)

    def _tasten(self):
        r = self.root
        r.bind("<Control-s>", lambda e: self.speichern())
        r.bind("<Control-Prior>", lambda e: (self.zeichnung_weiter(-1), "break")[1])
        r.bind("<Control-Next>", lambda e: (self.zeichnung_weiter(1), "break")[1])
        r.bind("<Control-Return>", lambda e: (self.naht_bestaetigen(), "break")[1])
        r.bind("<Key>", self._taste)

    def _dnd(self):
        if DND_FILES is not None and hasattr(self.root, "drop_target_register"):
            try:
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind("<<Drop>>", self._drop)
            except Exception:   # pragma: no cover
                pass

    def _drop(self, e):
        teile = self.root.tk.splitlist(e.data)
        if teile:
            self.pfad_oeffnen(teile[0])

    def _tippt(self):
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox, tk.Spinbox))

    def _taste(self, e):
        if self._tippt():
            return
        k = e.keysym.lower()
        if k == "n":
            self.naechste_offene()
        elif k == "f":
            self.ganze_seite()
        elif k == "a":
            self.neu_modus_umschalten()
        elif k in ("plus", "equal", "kp_add"):
            self.zoom_schritt(1.4)
        elif k in ("minus", "kp_subtract"):
            self.zoom_schritt(1 / 1.4)
        elif k == "delete":
            self.naht_loeschen()
        elif k == "return":
            self.naht_bestaetigen()
        elif k == "escape":
            if self.var_neu.get():
                self.neu_modus_umschalten()

    # ------------------------------------------------------------------------------------------------ Weitere Excel-Spalten
    def _vorlage_pfad(self):
        v = (self.p.vorlage if self.p else "") or lauf.default_vorlage()
        return v if os.path.exists(v) else ""

    def _extras_aufbauen(self):
        """Eingabefelder für alle Spalten der Excel-Vorlage, die nicht erkannt werden (Überschriften aus der Vorlage)."""
        for w in self.extra_tab.winfo_children():
            w.destroy()
        self.extra_vars, self.x_widgets = {}, []
        labels, wps = {}, None
        v = self._vorlage_pfad()
        if v:
            try:
                labels, wps = output.vorlage_spalten(v)
            except Exception:
                labels = {}
        if not labels:
            labels = {b: f"Spalte {b}" for b in "ABCDEFGHIJKLMNO"}
        self.wps_buchstabe = wps
        self.e_wps._lbl.config(text=(f"WPS (Sp. {wps})\n(vorbelegt: Winkel)" if wps else "WPS\n(vorbelegt: Winkel)"))
        zeile = 0
        self.x_rollen = pruefklassen.rollen(labels)
        self.x_umfang = {}
        for b, t in output.zusatz_spalten(labels, wps):
            rolle = self.x_rollen.get(b)
            ttk.Label(self.extra_tab, text=f"{t}  (Sp. {b})", wraplength=170, justify="left").grid(row=zeile, column=0, sticky="w", padx=(0, 6), pady=1)
            if rolle in ("ut", "mt", "vt"):      # Prüfumfang: nur Anzeige, folgt aus der Prüfklasse
                var = tk.StringVar()
                ttk.Label(self.extra_tab, textvariable=var, font=self.f_fett).grid(row=zeile, column=1, sticky="w", pady=1)
                self.x_umfang[rolle] = var
                zeile += 1
                continue
            var = tk.StringVar()
            if rolle in ("cp", "ct"):
                e = ttk.Combobox(self.extra_tab, textvariable=var, state="readonly",
                                 values=pruefklassen.CP_LISTE if rolle == "cp" else pruefklassen.CT_LISTE)
                e.bind("<<ComboboxSelected>>", lambda ev, r=rolle: self._klasse_gewaehlt(r))
            else:
                e = ttk.Entry(self.extra_tab, textvariable=var)
                e.bind("<Return>", lambda ev: (self.naht_bestaetigen(), "break")[1])
            e.grid(row=zeile, column=1, sticky="ew", pady=1)
            btn = ttk.Button(self.extra_tab, text="→ alle", width=7, command=lambda b=b: self.extra_fuer_alle(b))
            btn.grid(row=zeile, column=2, padx=(4, 0), pady=1)
            self.extra_vars[b] = var
            self.x_widgets += [e, btn]
            zeile += 1
        ttk.Label(self.extra_tab, foreground="#555555", wraplength=330, justify="left",
                  text="Diese Angaben gehen unverändert in die Excel-Liste. '→ alle' trägt den Wert bei allen Nähten dieser "
                       "Zeichnung ein. Sie ändern den Prüfstatus nicht.").grid(row=zeile, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._form_fuellen(self._naht())

    def _spalte(self, rolle):
        return next((b for b, r in self.x_rollen.items() if r == rolle), None)

    def _klasse_gewaehlt(self, rolle):
        """Güteklasse gewählt -> passende Prüfklasse (Tabelle) setzen; danach Prüfumfang neu anzeigen."""
        if rolle == "cp" and self._spalte("ct") in self.extra_vars:
            cp = self.extra_vars[self._spalte("cp")].get()
            if cp in pruefklassen.CP_ZU_CT:
                self.extra_vars[self._spalte("ct")].set(pruefklassen.CP_ZU_CT[cp])
        self._umfang_anzeigen()

    def _umfang_anzeigen(self):
        sp = self._spalte("ct")
        ct = self.extra_vars[sp].get() if sp in self.extra_vars else pruefklassen.STANDARD_CT
        for r, w in zip(("ut", "mt", "vt"), pruefklassen.umfang(ct)):
            if r in self.x_umfang:
                self.x_umfang[r].set(w)

    def vorlage_waehlen(self):
        if self.p is None:
            messagebox.showinfo("Excel-Vorlage", "Es ist kein Projekt geöffnet.", parent=self.root)
            return
        v = filedialog.askopenfilename(parent=self.root, title="Excel-Vorlage Prüfplan wählen (Blatt SNP)",
                                       filetypes=[("Excel", "*.xlsx")])
        if v:
            self.p.vorlage = v
            self._extras_aufbauen()
            self._sichern()

    def extra_fuer_alle(self, b):
        if self.z is None or b not in self.extra_vars:
            return
        wert = self.extra_vars[b].get().strip()
        anz = len(self.z.aktive())
        text = (f"'{wert}' bei allen {anz} Nähten dieser Zeichnung eintragen?" if wert
                else f"Diese Spalte bei allen {anz} Nähten dieser Zeichnung leeren?")
        if not messagebox.askyesno("Für alle Nähte", text + "\nVorhandene Einträge in dieser Spalte werden überschrieben.", parent=self.root):
            return
        self._form_anwenden(False)
        P.extra_fuer_alle(self.z, b, wert)
        if self.x_rollen.get(b) == "cp" and self._spalte("ct") in self.extra_vars:    # Güteklasse bringt ihre Prüfklasse mit
            P.extra_fuer_alle(self.z, self._spalte("ct"), self.extra_vars[self._spalte("ct")].get().strip())
        self._form_fuellen(self._naht())
        self._sichern()
        self._status(f"Spalte {b}: bei {anz} Nähten eingetragen.")

    # ------------------------------------------------------------------------------------------------ Projekt
    def projekt_setzen(self, p):
        self.p = p
        self.sel = None
        arten = sorted({n.art for z in p.zeichnungen for n in z.naehte if n.art} - set(ARTEN))
        self.c_art.configure(values=ARTEN + arten)
        self._extras_aufbauen()
        self._pruefe_pdfs()
        erste = next((z for z in p.zeichnungen if z.offene()), p.zeichnungen[0] if p.zeichnungen else None)
        self._zeichnung_wechseln(erste)
        self._titel()
        self.root.update_idletasks()
        n = self._naechste_offene_naht()
        if n is not None:
            self.waehle(n[1].id, zeichnung=n[0], zentrieren=True)
        self._status("Projekt geladen.")

    def _pruefe_pdfs(self):
        fehlt, geaendert = [], []
        for z in self.p.zeichnungen:
            if not os.path.exists(z.pfad):
                fehlt.append(z.datei)
            elif z.pdf_geaendert():
                geaendert.append(z.datei)
        if fehlt:
            self._status("PDF nicht gefunden: " + ", ".join(fehlt) + " (wird beim Öffnen der Zeichnung abgefragt)")
        if geaendert:
            messagebox.showwarning(
                "Zeichnung geändert",
                "Diese PDF-Dateien wurden seit der Erkennung verändert:\n  " + "\n  ".join(geaendert) +
                "\n\nMarkierungen können dann falsch liegen. Mit Ansicht > 'Erkennung dieser Zeichnung wiederholen' "
                "wird neu erkannt; geprüfte und von Hand gesetzte Nähte bleiben erhalten.", parent=self.root)

    def _titel(self):
        if self.p:
            self.root.title(f"WeldWatch - {self.p.basis}   [{self.p.pfad or 'nicht gespeichert'}]")
        else:
            self.root.title("WeldWatch - Prüf-Fenster")

    def _zeichnung_wechseln(self, z):
        if self.seite is not None:
            if not self.busy:
                self.seite.schliessen()
            self.seite = None
        self.z = z
        self.sel = None
        if z is not None:
            if not os.path.exists(z.pfad):
                neu = filedialog.askopenfilename(parent=self.root, title=f"PDF suchen: {z.datei}",
                                                 initialfile=z.datei, filetypes=[("PDF", "*.pdf")])
                if neu:
                    z.pfad = neu
                    z.pruefsumme = z.pruefsumme or ""
            try:
                if self.busy:
                    raise RuntimeError("Erkennung läuft - Ansicht danach verfügbar")
                self.seite = PdfSeite(z.pfad)
                self.ansicht.setze_seite((self.seite.w, self.seite.h))
                if not z.seite or z.seite == (0.0, 0.0):
                    z.seite = (self.seite.w, self.seite.h)
            except Exception as ex:
                self.seite = None
                self._status(f"PDF kann nicht angezeigt werden: {ex}")
        self.var_dn.set(z.dn if z else "")
        self._combo_aktualisieren()
        self._info_aktualisieren()
        self._liste_fuellen()
        self._form_fuellen(None)
        self._fenster_abgleichen()
        self.ansicht.einpassen()
        self._zeichnen_alles()

    def _info_aktualisieren(self):
        z = self.z
        if z is None:
            self.lbl_info.config(text="")
            return
        teile = []
        if z.status != "ok":
            teile.append(f"Erkennung: {z.status}")
        teile += z.notes
        self.lbl_info.config(text="\n".join(teile))

    def _combo_aktualisieren(self):
        if not self.p:
            self.cb_zeichnung.configure(values=[])
            self.var_zeichnung.set("")
            self._tabs_aktualisieren()
            return
        texte = [f"{z.datei}  ({len(z.aktive())} Nähte, {len(z.offene())} offen)" for z in self.p.zeichnungen]
        self.cb_zeichnung.configure(values=texte)
        if self.z in self.p.zeichnungen:
            self.var_zeichnung.set(texte[self.p.zeichnungen.index(self.z)])
            self.var_zi.set(self.p.zeichnungen.index(self.z))
        self._tabs_aktualisieren()
        offen = self.p.anzahl_offen()
        self.lbl_offen.config(text=f"offen: {offen} von {self.p.anzahl_aktiv()}", foreground="#b25b00" if offen else "#2e7d32")

    def _tabs_aktualisieren(self):
        """Reiterleiste mit allen Zeichnungen (bis 8 Stück) zum direkten Umschalten, mit Anzahl offener Nähte."""
        zs = self.p.zeichnungen if self.p else []
        if len(zs) < 2 or len(zs) > 8:
            for b in self.tab_btns:
                b.destroy()
            self.tab_btns = []
            return
        if len(self.tab_btns) != len(zs):
            for b in self.tab_btns:
                b.destroy()
            self.tab_btns = []
            for i in range(len(zs)):
                b = ttk.Radiobutton(self.tabs, style="Toolbutton", variable=self.var_zi, value=i,
                                    command=lambda i=i: self.zeichnung_nr(i))
                b.pack(side="left", padx=(0, 3))
                self.tab_btns.append(b)
        for i, (b, z) in enumerate(zip(self.tab_btns, zs)):
            o = len(z.offene())
            name = z.datei if len(z.datei) <= 26 else z.datei[:23] + "..."
            b.config(text=f"{i + 1}. {name}  " + (f"({o} offen)" if o else "✓"))

    def zeichnung_nr(self, i):
        """Zur Zeichnung Nr. i (0-basiert) wechseln - ohne Bedingung, die vorige muss nicht fertig sein."""
        if self.busy or not self.p or not (0 <= i < len(self.p.zeichnungen)):
            return
        if self.p.zeichnungen[i] is self.z:
            return
        self._form_anwenden(False)
        z = self.p.zeichnungen[i]
        self._zeichnung_wechseln(z)
        akt = z.aktive()
        n = next((m for m in akt if m.offen), None) or (akt[0] if akt else None)
        if n is not None:
            self.waehle(n.id, zentrieren=True)

    def zeichnung_weiter(self, delta):
        if self.busy or not self.p or not self.p.zeichnungen:
            return
        i = self.p.zeichnungen.index(self.z) if self.z in self.p.zeichnungen else 0
        self.zeichnung_nr((i + delta) % len(self.p.zeichnungen))

    def _zeichnung_gewaehlt(self, _e=None):
        if self.busy or not self.p:
            return
        self.zeichnung_nr(self.cb_zeichnung.current())

    def _dn_uebernehmen(self, _e=None):
        if self.z is not None and self.var_dn.get().strip() != self.z.dn:
            self.z.dn = self.var_dn.get().strip()
            self._sichern()

    # ------------------------------------------------------------------------------------------------ Liste
    def _naht(self):
        return self.z.naht(self.sel) if (self.z is not None and self.sel) else None

    def _sichtbare_naehte(self):
        if self.z is None:
            return []
        out = []
        for n in self.z.naehte:
            if not n.aktiv and not self.var_geloescht.get():
                continue
            out.append(n)
        return out

    def _liste_fuellen(self):
        self._tree_sperre = True
        try:
            self.tree.delete(*self.tree.get_children())
            for n in self._sichtbare_naehte():
                if self.var_nur_offen.get() and not n.offen and n.id != self.sel:
                    continue
                status = n.status if not (n.status == P.OFFEN and not n.ok) else "prüfen!"
                if n.unvollstaendig and n.aktiv:
                    status = "unvollständig"
                self.tree.insert("", "end", iid=n.id, tags=(zeilen_tag(n),),
                                 values=(n.nr or "-", n.square, n.art, n.angabe.replace("\n", " / "), n.gruppe, status))
            if self.sel and self.tree.exists(self.sel):
                self.tree.selection_set(self.sel)
                self.tree.see(self.sel)
        finally:
            self._tree_sperre = False

    def _tree_markieren(self):
        self._tree_sperre = True
        try:
            if self.sel and self.tree.exists(self.sel):
                self.tree.selection_set(self.sel)
                self.tree.see(self.sel)
            elif self.tree.selection():
                self.tree.selection_remove(*self.tree.selection())
        finally:
            self._tree_sperre = False

    def _geloescht_umschalten(self):
        self._liste_fuellen()
        self._zeichne_overlay()

    def _tree_gewaehlt(self, _e=None):
        if self._tree_sperre:
            return
        s = self.tree.selection()
        if s and s[0] != self.sel:
            self.waehle(s[0], zentrieren=True)

    # ------------------------------------------------------------------------------------------------ Formular
    def _form_fuellen(self, n):
        for w in self.f_widgets:
            w.configure(state="normal")
        for w in self.x_widgets:
            w.configure(state="readonly" if isinstance(w, ttk.Combobox) else "normal")
        self.t_angabe.delete("1.0", "end")
        if n is None:
            for v in list(self.v.values()) + list(self.extra_vars.values()):
                v.set("")
            for v in self.x_umfang.values():
                v.set("")
            self._snap = None
            self.lbl_quelle.config(text="Keine Naht gewählt. Naht in der Zeichnung oder in der Liste anklicken.")
            for w in self.f_widgets + self.x_widgets:
                self._sperren(w)
            self.btn_ok.state(["disabled"])
            self.btn_del.state(["disabled"])
            return
        self.v["square"].set(n.square)
        self.v["art"].set(n.art)
        self.v["stoss"].set(n.stoss)
        self.v["dicke"].set(n.dicke)
        self.t_angabe.insert("1.0", n.angabe)
        self.v["gruppe"].set(n.gruppe)
        self.v["wps"].set(n.wps)
        self.v["bem"].set("; ".join(n.bemerkung))
        for b, var in self.extra_vars.items():
            standard = {"cp": pruefklassen.STANDARD_CP, "ct": pruefklassen.STANDARD_CT}.get(self.x_rollen.get(b), "")
            var.set(n.extra.get(b) or standard)
        self._umfang_anzeigen()
        hinweis = "" if n.ok or n.status != P.OFFEN else "  -  Erkennung unsicher, bitte genau prüfen"
        self.lbl_quelle.config(text=f"Nr. {n.nr or '-'}  |  Quelle: {n.quelle}  |  Status: {n.status}{hinweis}")
        self._snap = self._form_werte()
        self.btn_ok.state(["!disabled"])
        self.btn_del.state(["!disabled"])
        if n.aktiv:
            self.btn_del.config(text="Löschen (Entf)")
        else:
            self.btn_del.config(text="Wiederherstellen (Entf)")
            for w in self.f_widgets + self.x_widgets:
                self._sperren(w)
            self.btn_ok.state(["disabled"])

    @staticmethod
    def _sperren(w):
        w.configure(state="disabled")

    def _form_werte(self):
        return dict(square=self.v["square"].get().strip(), art=self.v["art"].get().strip(), stoss=self.v["stoss"].get().strip(),
                    dicke=self.v["dicke"].get().strip(), angabe=self.t_angabe.get("1.0", "end-1c").strip(),
                    gruppe=self.v["gruppe"].get().strip(), wps=self.v["wps"].get().strip(), bem=self.v["bem"].get().strip(),
                    x={b: v.get().strip() for b, v in self.extra_vars.items()})

    def _form_anwenden(self, bestaetigen):
        """Formularwerte in die Naht übernehmen. bestaetigen=True prüft zusätzlich auf Vollständigkeit.
        Rückgabe False = nicht übernommen (Nutzer soll nachbessern)."""
        n = self._naht()
        if n is None or not n.aktiv or self._snap is None:
            return True
        w = self._form_werte()
        if w == self._snap and not bestaetigen:
            return True
        if bestaetigen:
            if not w["art"] or not w["angabe"]:
                messagebox.showwarning("Unvollständig", "Nahtart und Zeichnungsangabe müssen ausgefüllt sein.", parent=self.root)
                return False
            if not P.gruppe_gueltig(w["gruppe"]):
                if not messagebox.askyesno(
                        "Werkstoffgruppe prüfen",
                        f"'{w['gruppe']}' passt nicht zum Schema (Gr.1-11, Gr.21-26 nur als Gr.22/23, Mischverbindung 'Gr.1 + Gr.8').\n\n"
                        "Trotzdem übernehmen?", parent=self.root):
                    return False
        erkannt = ("square", "art", "stoss", "dicke", "angabe", "gruppe", "bem")
        if bestaetigen or any(w[k] != self._snap[k] for k in erkannt):
            P.aendern(self.z, n, square=w["square"] or n.square, art=w["art"], stoss=w["stoss"], dicke=w["dicke"],
                      angabe=w["angabe"], gruppe=w["gruppe"], bemerkung=w["bem"])
        # WPS und weitere Excel-Spalten sind reine Eingabedaten: ändern den Prüfstatus nicht
        n.wps = w["wps"]
        P.extras_setzen(n, w["x"])
        self._snap = self._form_werte()
        self._nach_aenderung()
        return True

    def _nach_aenderung(self):
        self._liste_fuellen()
        self._combo_aktualisieren()
        self._zeichne_overlay()
        self._sichern()

    # ------------------------------------------------------------------------------------------------ Aktionen
    def waehle(self, nid, zentrieren=False, zeichnung=None):
        if not self._form_anwenden(False):
            return
        if zeichnung is not None and zeichnung is not self.z:
            self._zeichnung_wechseln(zeichnung)
        self.sel = nid
        n = self._naht()
        self._form_fuellen(n)
        if self.var_nur_offen.get():
            self._liste_fuellen()
        else:
            self._tree_markieren()
        if n is not None and (zentrieren or not self.ansicht.sichtbar(n.box)):
            self._anzeigen(n)
        else:
            self._zeichne_overlay()

    def _anzeigen(self, n):
        self.ansicht.zentrieren((n.box[0] + n.box[2]) / 2, (n.box[1] + n.box[3]) / 2, min_scale=1.2)
        self._zeichnen_alles()

    def naht_bestaetigen(self):
        if self._naht() is None:
            return
        if not self._form_anwenden(True):
            return
        self.naechste_offene()

    def naht_loeschen(self):
        n = self._naht()
        if n is None:
            return
        pos = self._position()
        if n.aktiv:
            P.loeschen(self.z, n)
            if n.status == P.MANUELL and n not in self.z.naehte:
                self.sel = None
        else:
            P.wiederherstellen(self.z, n)
        self._snap = None
        self._form_fuellen(self._naht())
        self._nach_aenderung()
        if self._naht() is None or not self._naht().aktiv:
            self.naechste_offene(pos)

    def _position(self):
        """(Index der Zeichnung, Nr der gewählten Naht) oder None"""
        cur = self._naht()
        if cur is not None and self.p and self.z in self.p.zeichnungen:
            return (self.p.zeichnungen.index(self.z), cur.nr)
        return None

    def _naechste_offene_naht(self, nach=None):
        """(Zeichnung, Naht) der nächsten offenen Naht nach der Position (Zeichnung, Nr) bzw. der gewählten Naht,
        sonst (am Ende angekommen) die erste offene."""
        if not self.p:
            return None
        alle = [(zi, n.nr, z, n) for zi, z in enumerate(self.p.zeichnungen) for n in z.naehte if n.aktiv and n.offen]
        if not alle:
            return None
        alle.sort(key=lambda t: (t[0], t[1]))
        cur = self._naht()
        nach = nach if nach is not None else self._position()
        if nach is not None:
            for zi, nr, z, n in alle:
                if (zi, nr) > nach:
                    return z, n
        for zi, nr, z, n in alle:
            if n is not cur:
                return z, n
        return alle[0][2], alle[0][3]

    def naechste_offene(self, nach=None):
        if not self.p:
            return
        ziel = self._naechste_offene_naht(nach)
        if ziel is None:
            self._status("Alle Nähte sind geprüft. Excel-Prüfplan kann erstellt werden.")
            messagebox.showinfo("Fertig geprüft", "Alle Nähte sind geprüft.\n\nJetzt kann der Excel-Prüfplan erstellt werden "
                                                  "(Datei > Excel-Prüfplan erstellen).", parent=self.root)
            return
        self.waehle(ziel[1].id, zeichnung=ziel[0], zentrieren=True)

    def neu_modus_umschalten(self):
        self.var_neu.set(not self.var_neu.get())
        self._neu_modus_geaendert()

    def _neu_modus_geaendert(self):
        self.canvas.config(cursor="crosshair" if self.var_neu.get() else "")
        if self.var_neu.get():
            self._status("Neue Naht: in die Zeichnung klicken oder einen Rahmen aufziehen. Esc bricht ab.")

    def neue_naht(self, x, y, box=None):
        if self.z is None:
            return None
        self._form_anwenden(False)
        n = P.neue_naht(self.z, x, y, box)
        self.var_neu.set(False)
        self._neu_modus_geaendert()
        self.sel = n.id
        self._form_fuellen(n)
        self._liste_fuellen()
        self._combo_aktualisieren()
        self._zeichne_overlay()
        self._sichern()
        self.c_art.focus_set()
        self._status("Neue Naht angelegt: Daten eintragen und mit Strg+Enter bestätigen.")
        return n

    # ------------------------------------------------------------------------------------------------ Zeichnen
    def _fenster_abgleichen(self):
        self.ansicht.setze_fenster(max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))

    def _groesse(self, e):
        self.ansicht.setze_fenster(e.width, e.height)
        if self._erst_fit and e.width > 100:
            self._erst_fit = False
            self.ansicht.einpassen()
        self._zeichnen_spaeter()

    def _zeichnen_spaeter(self, ms=60):
        if self._job is not None:
            self.root.after_cancel(self._job)
        self._job = self.root.after(ms, self._zeichnen_alles)

    def _zeichnen_alles(self):
        self._job = None
        c = self.canvas
        c.delete("all")
        self._fenster_abgleichen()
        w, h = self.ansicht.w, self.ansicht.h
        if self.busy and self.seite is not None:   # PDFium ist nicht thread-sicher: während der Erkennung nicht rendern
            c.create_text(w / 2, h / 2, text="Erkennung läuft ...\nDie Ansicht ist währenddessen pausiert.",
                          font=("TkDefaultFont", 14), fill="#555555", justify="center", tags="bg")
            return
        if self.seite is None:
            text = "PDF-Datei, Ordner oder Projektdatei (.wwp) hierher ziehen\noder oben auf 'Öffnen ...' klicken." \
                if self.z is None else "PDF kann nicht angezeigt werden."
            c.create_text(w / 2, h / 2, text=text, font=("TkDefaultFont", 14), fill="#555555", justify="center", tags="bg")
            return
        a = self.ansicht
        x0, y0, x1, y1 = a.sichtfeld()
        img, pos = self.seite.bereich(x0, y0, x1, y1, a.scale)
        if img is not None:
            self._img = ImageTk.PhotoImage(img)
            px, py = a.zu_px(*pos)
            c.create_image(px, py, anchor="nw", image=self._img, tags="bg")
        self._zeichne_overlay()

    def _zeichne_overlay(self):
        c = self.canvas
        c.delete("ov")
        if self.z is None or self.seite is None:
            return
        a = self.ansicht
        fx0, fy0, fx1, fy1 = a.sichtfeld()
        if self.z.ex:
            ex = self.z.ex
            px0, py0 = a.zu_px(ex[0], ex[1])
            px1, py1 = a.zu_px(ex[2], ex[3])
            c.create_rectangle(px0, py0, px1, py1, fill="#808080", stipple="gray25", outline="#555555", width=2, tags="ov")
            c.create_text(px0 + 6, py0 + 4, anchor="nw", text="ignoriert (allgemeine Angaben)", fill="#333333", tags="ov")
        gewaehlt = None
        for n in self._sichtbare_naehte():
            b = n.box
            if b[2] < fx0 or b[0] > fx1 or b[3] < fy0 or b[1] > fy1:
                continue
            if n.id == self.sel:
                gewaehlt = n
                continue
            self._box_zeichnen(n, farbe_naht(n), 2)
        if gewaehlt is not None:
            self._box_zeichnen(gewaehlt, FARBE_AUSWAHL, 4)

    def _box_zeichnen(self, n, farbe, breite):
        c, a = self.canvas, self.ansicht
        x0, y0 = a.zu_px(n.box[0], n.box[1])
        x1, y1 = a.zu_px(n.box[2], n.box[3])
        c.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline=farbe, width=breite, tags="ov",
                           dash=(4, 3) if not n.aktiv else None)
        label = str(n.nr) if n.nr else "x"
        t = c.create_text(x0 - 1, y0 - 5, anchor="sw", text=label, fill="white", font=self.f_fett, tags="ov")
        bb = c.bbox(t)
        r = c.create_rectangle(bb[0] - 2, bb[1] - 1, bb[2] + 2, bb[3] + 1, fill=farbe, outline=farbe, tags="ov")
        c.tag_lower(r, t)

    # ------------------------------------------------------------------------------------------------ Maus
    def _druck(self, e):
        self.canvas.focus_set()
        self._drag = dict(x=e.x, y=e.y, x0=e.x, y0=e.y, bewegt=False, pan=not self.var_neu.get(), rahmen=None)

    def _druck_pan(self, e):
        self.canvas.focus_set()
        self._drag = dict(x=e.x, y=e.y, x0=e.x, y0=e.y, bewegt=False, pan=True, rahmen=None)

    def _zug(self, e):
        d = self._drag
        if not d:
            return
        if abs(e.x - d["x0"]) + abs(e.y - d["y0"]) > 4:
            d["bewegt"] = True
        if not d["bewegt"]:
            return
        if d["pan"]:
            self.canvas.move("all", e.x - d["x"], e.y - d["y"])
            d["x"], d["y"] = e.x, e.y
        else:
            if d["rahmen"]:
                self.canvas.delete(d["rahmen"])
            d["rahmen"] = self.canvas.create_rectangle(d["x0"], d["y0"], e.x, e.y, outline=FARBE_AUSWAHL, dash=(4, 3), width=2)

    def _los(self, e):
        d, self._drag = self._drag, None
        if not d or self.seite is None:
            return
        if d["pan"] and d["bewegt"]:
            self.ansicht.verschieben(e.x - d["x0"], e.y - d["y0"])
            self._zeichnen_alles()
        elif not d["pan"]:
            if d["rahmen"]:
                self.canvas.delete(d["rahmen"])
            if d["bewegt"]:
                a = self.ansicht.zu_pt(d["x0"], d["y0"])
                b = self.ansicht.zu_pt(e.x, e.y)
                self.neue_naht(0, 0, box=(a[0], a[1], b[0], b[1]))
            else:
                x, y = self.ansicht.zu_pt(e.x, e.y)
                self.neue_naht(x, y)
        elif not d["bewegt"]:
            self._klick(e.x, e.y)

    def _klick(self, px, py):
        x, y = self.ansicht.zu_pt(px, py)
        rand = 4 / self.ansicht.scale
        treffer = [n for n in self._sichtbare_naehte()
                   if n.box[0] - rand <= x <= n.box[2] + rand and n.box[1] - rand <= y <= n.box[3] + rand]
        if treffer:
            n = min(treffer, key=lambda m: (m.box[2] - m.box[0]) * (m.box[3] - m.box[1]))
            self.waehle(n.id)
        elif self.sel:
            self._form_anwenden(False)
            self.sel = None
            self._form_fuellen(None)
            self._liste_fuellen()
            self._zeichne_overlay()

    def _rad(self, e):
        if self.seite is None:
            return
        auf = (e.num == 4) or (getattr(e, "delta", 0) > 0)
        self.ansicht.zoom(1.25 if auf else 1 / 1.25, e.x, e.y)
        self._zeichnen_spaeter(70)

    def zoom_schritt(self, f):
        if self.seite is None:
            return
        self.ansicht.zoom(f, self.ansicht.w / 2, self.ansicht.h / 2)
        self._zeichnen_alles()

    def ganze_seite(self):
        self._fenster_abgleichen()
        self.ansicht.einpassen()
        self._zeichnen_alles()

    # ------------------------------------------------------------------------------------------------ Dateien
    def _status(self, text):
        self.var_status.set(text)

    def _sichern(self, p=None):
        """Automatisches Sichern nach jeder Änderung: ins Projekt, sobald es einen Speicherort hat, vorher in eine Sicherungsdatei."""
        p = p or self.p
        if p is None:
            return
        try:
            if p.pfad:
                p.speichern()
            else:
                p.speichern(lauf.sicherung_pfad(p.basis), merke=False)
        except OSError as ex:
            self._status(f"Speichern der Projektdatei fehlgeschlagen: {ex}")

    def speichern(self):
        """Erstes Speichern: 'Speichern unter' (Ordner für alle Ausgaben). Danach wird die Projektdatei nur aktualisiert."""
        if self.p is None:
            return False
        self._form_anwenden(False)
        if not self.p.pfad:
            return self.speichern_unter()
        try:
            self.p.speichern()
            self._status(f"Gespeichert: {self.p.pfad}")
            return True
        except OSError as ex:
            messagebox.showerror("Speichern", f"Projektdatei konnte nicht gespeichert werden:\n{ex}", parent=self.root)
            return False

    def speichern_unter(self):
        if self.p is None:
            return False
        if self.busy:
            messagebox.showinfo("Bitte warten", "Es läuft gerade eine Erkennung.", parent=self.root)
            return False
        self._form_anwenden(False)
        p = self.p
        ziel = filedialog.asksaveasfilename(parent=self.root, title="Projekt speichern unter (in diesen Ordner kommen auch alle Ausgaben)",
                                            defaultextension=P.ENDUNG,
                                            initialdir=os.path.dirname(p.pfad) if p.pfad else lauf.ausgabe_ordner(),
                                            initialfile=os.path.basename(p.pfad) if p.pfad else p.basis + P.ENDUNG,
                                            filetypes=[("WeldWatch-Projekt", "*" + P.ENDUNG)])
        if not ziel:
            return False
        ordner = os.path.dirname(os.path.abspath(ziel))
        kopieren = p.pdfs_kopiert
        if not kopieren and p.zeichnungen:
            kopieren = messagebox.askyesno(
                "Zeichnungen mitspeichern?",
                "Sollen die Zeichnungs-PDFs mit ins Projekt gespeichert werden?\n\n"
                f"Ja = Kopie im Unterordner 'Zeichnungen' neben der Projektdatei. Das Projekt bleibt vollständig, "
                "auch wenn die Originale verschoben oder geändert werden.\n"
                "Nein = das Projekt verweist weiter auf die Originaldateien.\n\nDie Originale bleiben in jedem Fall unverändert.",
                parent=self.root)
        try:
            if kopieren:
                _kopiert, fehlt = P.pdfs_kopieren(p, ordner)
                if fehlt:
                    messagebox.showwarning("Zeichnungen nicht gefunden", "Diese PDFs konnten nicht kopiert werden:\n  " + "\n  ".join(fehlt),
                                           parent=self.root)
            p.speichern(ziel)
        except OSError as ex:
            messagebox.showerror("Speichern", f"Projekt konnte nicht gespeichert werden:\n{ex}", parent=self.root)
            return False
        try:   # Sicherungsdatei wird nicht mehr gebraucht
            os.remove(lauf.sicherung_pfad(p.basis))
        except OSError:
            pass
        lauf.merke_projekt(p.eingabe, ziel)
        self._seite_neu_oeffnen()
        self._titel()
        self._status(f"Gespeichert: {ziel}")
        return True

    def _seite_neu_oeffnen(self):
        """PDF der aktuellen Zeichnung neu öffnen (z. B. nach dem Kopieren ins Projekt), Ansicht und Auswahl bleiben."""
        if self.busy or self.z is None:
            return
        try:
            if self.seite is not None:
                self.seite.schliessen()
            self.seite = PdfSeite(self.z.pfad)
        except Exception as ex:
            self.seite = None
            self._status(f"PDF kann nicht angezeigt werden: {ex}")
        self._zeichnen_alles()

    def _ungespeichert_fragen(self):
        """True = weitermachen. Fragt bei einem noch nie gespeicherten Projekt, ob gespeichert werden soll."""
        if self.p is None or self.p.pfad or not self.p.zeichnungen:
            return True
        a = messagebox.askyesnocancel("Projekt speichern?", "Das aktuelle Projekt wurde noch nicht gespeichert.\n\nJetzt speichern?",
                                      parent=self.root)
        if a is None:
            return False
        return self.speichern() if a else True

    def dialog_oeffnen(self):
        if self.busy:
            return
        pfad = filedialog.askopenfilename(parent=self.root, title="PDF oder Projekt öffnen",
                                          filetypes=[("PDF oder Projekt", "*.pdf *.wwp"), ("PDF", "*.pdf"),
                                                     ("WeldWatch-Projekt", "*" + P.ENDUNG)])
        if pfad:
            self.pfad_oeffnen(pfad)

    def dialog_ordner(self):
        if self.busy:
            return
        pfad = filedialog.askdirectory(parent=self.root, title="Ordner mit Zeichnungen (PDF)")
        if pfad:
            self.pfad_oeffnen(pfad)

    def pfad_oeffnen(self, pfad):
        if self.busy:
            messagebox.showinfo("Bitte warten", "Es läuft gerade eine Erkennung.", parent=self.root)
            return
        pfad = pfad.strip().strip('"')
        if not (pfad.lower().endswith(P.ENDUNG) or os.path.isdir(pfad) or pfad.lower().endswith(".pdf")):
            messagebox.showinfo("Nicht unterstützt", "Bitte eine PDF-Datei, einen Ordner mit PDFs oder eine Projektdatei (.wwp) wählen.",
                                parent=self.root)
            return
        if not self._ungespeichert_fragen():
            return
        if pfad.lower().endswith(P.ENDUNG):
            self.projekt_oeffnen(pfad)
        elif os.path.isdir(pfad) or pfad.lower().endswith(".pdf"):
            self.neu_aus_pfad(pfad)
        else:
            messagebox.showinfo("Nicht unterstützt", "Bitte eine PDF-Datei, einen Ordner mit PDFs oder eine Projektdatei (.wwp) wählen.",
                                parent=self.root)

    @staticmethod
    def _laden(pfad):
        p = P.Projekt.laden(pfad)
        if os.path.basename(os.path.dirname(os.path.abspath(pfad))) == "_Sicherung":
            p.pfad = ""          # nur die automatische Sicherung: Speicherort wird beim Speichern abgefragt
        return p

    def projekt_oeffnen(self, pfad):
        try:
            p = self._laden(pfad)
        except Exception as ex:
            messagebox.showerror("Projekt öffnen", f"Projektdatei konnte nicht gelesen werden:\n{ex}", parent=self.root)
            return
        if self.p is not None:
            self._form_anwenden(False)
            self._sichern()
        self.projekt_setzen(p)

    def neu_aus_pfad(self, pfad):
        pdfs = lauf.pdfs_in(pfad)
        if not pdfs:
            messagebox.showinfo("Keine PDF", "Im Ordner liegen keine PDF-Dateien.", parent=self.root)
            return
        ziel = lauf.finde_projekt(pfad)
        if ziel:
            a = messagebox.askyesnocancel(
                "Projekt vorhanden",
                f"Für '{lauf.projektname(pfad)}' gibt es schon ein Projekt:\n{ziel}\n\n"
                "Ja = vorhandenes Projekt öffnen (kein neuer Lauf)\n"
                "Nein = Erkennung neu durchführen (geprüfte und von Hand gesetzte Nähte bleiben erhalten)\n"
                "Abbrechen = nichts tun", parent=self.root)
            if a is None:
                return
            if a:
                self.projekt_oeffnen(ziel)
                return
            try:
                p = self._laden(ziel)
            except Exception as ex:
                messagebox.showerror("Projekt öffnen", f"Vorhandenes Projekt nicht lesbar:\n{ex}", parent=self.root)
                return
            self._starte_lauf(pdfs, ziel_projekt=p)
        else:
            self._starte_lauf(pdfs, eingabe=pfad)

    def zeichnungen_hinzufuegen(self):
        if self.busy:
            return
        if self.p is None:
            return self.dialog_oeffnen()
        dateien = filedialog.askopenfilenames(parent=self.root, title="Zeichnungen hinzufügen", filetypes=[("PDF", "*.pdf")])
        if dateien:
            self._form_anwenden(False)
            self._starte_lauf(list(dateien), ziel_projekt=self.p)

    def erkennung_wiederholen(self):
        if self.busy or self.z is None:
            return
        self._form_anwenden(False)
        self._starte_lauf([self.z.pfad], ziel_projekt=self.p)

    # ------------------------------------------------------------------------------------------------ Hintergrundjobs
    def _starte_job(self, text, arbeit, danach, hinweis="", titel="Fehler"):
        """arbeit(fortschritt) läuft im Hintergrund (fortschritt(text) meldet den Stand), danach(ergebnis) im Hauptthread."""
        self.busy = True
        self._job_danach, self._job_hinweis, self._job_titel = danach, hinweis, titel
        self._lauf_t0 = time.time()
        self._lauf_text = text
        self.progress.start(12)
        self._zeichnen_alles()

        def thread():
            try:
                self.q.put(("fertig", arbeit(lambda t: self.q.put(("fortschritt", t)))))
            except BaseException:
                self.q.put(("fehler", traceback.format_exc()))

        threading.Thread(target=thread, daemon=True).start()
        self._poll()

    def _poll(self):
        fertig = None
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "fortschritt":
                    self._lauf_text = m[1]
                else:
                    fertig = m
        except queue.Empty:
            pass
        sek = int(time.time() - self._lauf_t0)
        self._status(f"{self._lauf_text}  {sek // 60}:{sek % 60:02d} min  {self._job_hinweis}")
        if fertig is None:
            self.root.after(300, self._poll)
        else:
            self._job_fertig(fertig)

    def _job_fertig(self, m):
        self.busy = False
        self.progress.stop()
        if m[0] == "fehler":
            self._status(f"{self._job_titel}.")
            messagebox.showerror(self._job_titel, m[1][-1500:], parent=self.root)
            self._zeichnen_alles()
            return
        self._job_danach(m[1])
        self._zeichnen_alles()

    # ------------------------------------------------------------------------------------------------ Erkennungslauf
    def _starte_lauf(self, pdfs, eingabe=None, ziel_projekt=None):
        self._lauf_ziel, self._lauf_eingabe = ziel_projekt, eingabe

        def arbeit(fort):
            return lauf.erkennen(pdfs, fortschritt=lambda i, n, f: fort(f"Erkenne {f} ({i + 1}/{n}) ..."))

        self._starte_job(f"Erkenne {len(pdfs)} Zeichnung(en) ...", arbeit, self._lauf_fertig,
                         hinweis="(A0-Scans brauchen mehrere Minuten)", titel="Erkennung fehlgeschlagen")

    def _lauf_fertig(self, res):
        meldungen = []
        if self._lauf_ziel is not None:
            p = self._lauf_ziel
            meldungen = lauf.einarbeiten(p, res)
        else:
            p = lauf.neues_projekt(self._lauf_eingabe, res)
        if p.pfad and p.pdfs_kopiert:     # neu aufgenommene Zeichnungen ebenfalls ins Projekt kopieren
            try:
                P.pdfs_kopieren(p, os.path.dirname(os.path.abspath(p.pfad)))
            except OSError as ex:
                meldungen.append(f"Zeichnung konnte nicht ins Projekt kopiert werden: {ex}")
        self._sichern(p)
        fehler = [z for z in res if z.status != "ok"]
        gesamt = sum(len(z.naehte) for z in res)
        self.projekt_setzen(p)
        ort = p.pfad or "noch nicht gespeichert (Strg+S = Speichern unter)"
        text = f"{len(res)} Zeichnung(en), {gesamt} Nähte erkannt.\nProjekt: {ort}\n\nAlle Vorschläge müssen geprüft werden."
        if meldungen:
            text += "\n\n" + "\n".join(meldungen)
        if fehler:
            text += "\n\nNicht auswertbar:\n" + "\n".join(f"  {z.datei}: {z.status}" for z in fehler)
        messagebox.showinfo("Erkennung abgeschlossen", text, parent=self.root)

    # ------------------------------------------------------------------------------------------------ Excel
    def excel_exportieren(self):
        if self.busy:
            return
        if self.p is None:
            messagebox.showinfo("Excel", "Es ist kein Projekt geöffnet.", parent=self.root)
            return
        self._form_anwenden(False)
        offen = self.p.anzahl_offen()
        if offen:
            messagebox.showwarning(
                "Noch nicht vollständig geprüft",
                f"Es sind noch {offen} Nähte offen (ungeprüft oder unvollständig).\n"
                "Die Excel-Liste gibt es erst nach vollständiger Prüfung.\n\nIch springe zur nächsten offenen Naht.",
                parent=self.root)
            self.naechste_offene()
            return
        vorlage = self.p.vorlage or lauf.default_vorlage()
        if not os.path.exists(vorlage):
            vorlage = filedialog.askopenfilename(parent=self.root, title="Excel-Vorlage Prüfplan wählen (Blatt SNP)",
                                                 filetypes=[("Excel", "*.xlsx")])
            if not vorlage:
                return
            self.p.vorlage = vorlage
            self._extras_aufbauen()
        if not self.p.pfad:     # Ausgaben liegen im Projektordner: erst Speicherort festlegen
            messagebox.showinfo("Projekt speichern", "Bitte zuerst den Speicherort des Projekts wählen.\n"
                                "Excel-Liste und Prüf-PDFs werden standardmäßig im selben Ordner abgelegt.", parent=self.root)
            if not self.speichern_unter():
                return
        ordner = os.path.dirname(os.path.abspath(self.p.pfad))
        ziel = filedialog.asksaveasfilename(parent=self.root, title="Excel-Prüfplan speichern", defaultextension=".xlsx",
                                            initialdir=ordner, initialfile=f"{self.p.basis}_Pruefplan.xlsx",
                                            filetypes=[("Excel", "*.xlsx")])
        if not ziel:
            return
        try:
            n = P.excel_schreiben(self.p, vorlage, ziel)
        except Exception as ex:
            messagebox.showerror("Excel", f"Excel-Datei konnte nicht erstellt werden (ist sie in Excel geöffnet?):\n{ex}", parent=self.root)
            return
        self._sichern()
        self._status(f"Excel erstellt: {ziel}")
        text = f"{n} Nähte aus {len(self.p.zeichnungen)} Zeichnung(en):\n{ziel}"
        pdf_ordner = os.path.splitext(ziel)[0] + "_Pruef-PDFs"
        if messagebox.askyesno("Excel erstellt", text + f"\n\nPrüf-PDFs (Zeichnungen mit nummerierten Markierungen der Nähte) mit exportieren?\n"
                               f"Sie kommen in den Unterordner:\n{pdf_ordner}", parent=self.root):
            self.pruef_pdfs_exportieren(pdf_ordner)

    def pruef_pdfs_exportieren(self, ordner):
        auftraege = P.pruef_auftraege(self.p)
        if not auftraege:
            messagebox.showinfo("Prüf-PDFs", "Keine Zeichnung mit Nähten vorhanden.", parent=self.root)
            return

        def arbeit(fort):
            return P.pruef_pdfs_schreiben(auftraege, ordner,
                                          fortschritt=lambda i, n, f: fort(f"Prüf-PDF {f} ({i + 1}/{n}) ..."))

        def danach(res):
            geschrieben, fehler = res
            text = f"{len(geschrieben)} Prüf-PDF(s) in:\n{ordner}"
            if fehler:
                text += "\n\nNicht erstellt:\n" + "\n".join("  " + e for e in fehler)
            self._status(f"Prüf-PDFs erstellt: {ordner}")
            (messagebox.showwarning if fehler else messagebox.showinfo)("Prüf-PDFs", text, parent=self.root)

        self._starte_job(f"Erstelle {len(auftraege)} Prüf-PDF(s) ...", arbeit, danach, titel="Prüf-PDFs fehlgeschlagen")

    # ------------------------------------------------------------------------------------------------ Ende
    def beenden(self):
        if self.busy and not messagebox.askyesno("Beenden", "Die Erkennung läuft noch. Wirklich beenden?", parent=self.root):
            return
        try:
            self._form_anwenden(False)
            if not self._ungespeichert_fragen():
                return
            self._sichern()
        except Exception:
            pass     # Beenden soll nie am Sichern scheitern
        if self.seite is not None:
            self.seite.schliessen()
        self.root.destroy()


# ---------------------------------------------------------------------------------------------------- Start
def _dpi_scharf():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _konsole_ausblenden():
    """Beim Doppelklick auf die exe das schwarze Konsolenfenster ausblenden (nur wenn es nur dieser Prozess nutzt)."""
    if os.name == "nt" and getattr(sys, "frozen", False):
        try:
            import ctypes
            k = ctypes.windll.kernel32
            hwnd = k.GetConsoleWindow()
            arr = (ctypes.c_uint * 4)()
            if hwnd and k.GetConsoleProcessList(arr, 4) <= 1:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


def neues_fenster():
    if TkinterDnD is not None:
        try:
            return TkinterDnD.Tk()
        except Exception:   # tkdnd nicht ladbar -> ohne Drag & Drop weiter
            pass
    return tk.Tk()


def _fehler_melden(root):
    """Unerwartete Fehler in Bedienaktionen: ins Protokoll schreiben und anzeigen, Fenster bleibt offen."""
    def melden(exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(os.path.join(lauf.ausgabe_ordner(), "weldwatch_fehler.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n")
        except OSError:
            pass
        try:
            messagebox.showerror("Unerwarteter Fehler",
                                 "Das hat nicht geklappt (die Arbeit ist in der Projektdatei gesichert):\n\n" + text[-1200:],
                                 parent=root)
        except Exception:
            pass
    root.report_callback_exception = melden


def start(pfad=None):
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    _dpi_scharf()
    root = neues_fenster()
    _fehler_melden(root)
    app = App(root)
    _konsole_ausblenden()
    if os.environ.get("WELDWATCH_SELBSTTEST"):    # CI: gebaute exe startet das Fenster und beendet sich wieder
        root.after(1500, app.beenden)
    elif pfad:
        root.after(300, lambda: app.pfad_oeffnen(pfad))
    root.mainloop()
