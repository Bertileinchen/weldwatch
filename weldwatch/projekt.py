"""Projektdatei: erkannte und geprüfte Nähte speichern/laden (JSON, ohne Zeichnungen).

Ablauf: Erkennung -> Projekt (Status "erkannt" = offen) -> Prüfung in der GUI -> Excel erst, wenn nichts mehr offen ist.
Ein erneuter Erkennungslauf (merge) überschreibt nie, was eine Person geprüft oder geändert hat.
"""
import hashlib, json, os, re, uuid, datetime
from dataclasses import dataclass, field

VERSION = 1
ENDUNG = ".wwp"

# Status einer Naht
OFFEN = "erkannt"            # vom Programm vorgeschlagen, noch nicht geprüft
BESTAETIGT = "bestätigt"     # Person hat den Vorschlag so übernommen
GEAENDERT = "geändert"       # Person hat Daten korrigiert
MANUELL = "manuell"          # Person hat die Naht selbst angelegt
GELOESCHT = "gelöscht"       # Person hat die Naht verworfen (bleibt gespeichert, damit ein Neulauf sie nicht zurückbringt)
GEPRUEFT = (BESTAETIGT, GEAENDERT, MANUELL, GELOESCHT)
STATUS_ALLE = (OFFEN,) + GEPRUEFT

STANDARD_BOX = (70.0, 28.0)   # pt, Größe einer von Hand gesetzten Markierung
MATCH_ABSTAND = 18.0          # pt, so nah liegt dieselbe Naht in einem Neulauf


def _neue_id():
    return uuid.uuid4().hex[:10]


@dataclass
class Naht:
    square: str = "-"
    x: float = 0.0
    y: float = 0.0
    art: str = ""
    angabe: str = ""
    dicke: str = ""
    gruppe: str = "Gr.1"
    bemerkung: list = field(default_factory=list)
    ok: bool = True                      # Erkennungssicherheit des Programms (False = "zu prüfen")
    quelle: str = "ISO"
    box: tuple = (0.0, 0.0, 0.0, 0.0)    # x0, y0, x1, y1 in pt (Ursprung links oben)
    status: str = OFFEN
    nr: int = 0
    id: str = field(default_factory=_neue_id)

    @property
    def aktiv(self):
        return self.status != GELOESCHT

    @property
    def unvollstaendig(self):
        return self.aktiv and not (self.art.strip() and self.angabe.strip())

    @property
    def offen(self):
        """noch zu tun: nicht geprüft oder ohne Nahtart/Zeichnungsangabe (z. B. von Hand gesetzt, aber leer)"""
        return self.status == OFFEN or self.unvollstaendig

    def to_dict(self):
        d = dict(id=self.id, nr=self.nr, square=self.square, x=round(self.x, 2), y=round(self.y, 2), art=self.art,
                 angabe=self.angabe, dicke=self.dicke, gruppe=self.gruppe, bemerkung=list(self.bemerkung),
                 ok=self.ok, quelle=self.quelle, box=[round(v, 2) for v in self.box], status=self.status)
        return d

    @classmethod
    def from_dict(cls, d):
        n = cls(square=d.get("square", "-"), x=float(d.get("x", 0)), y=float(d.get("y", 0)), art=d.get("art", ""),
                angabe=d.get("angabe", ""), dicke=d.get("dicke", ""), gruppe=d.get("gruppe", "Gr.1"),
                bemerkung=list(d.get("bemerkung", [])), ok=bool(d.get("ok", True)), quelle=d.get("quelle", "ISO"),
                box=tuple(d.get("box", (0, 0, 0, 0))), status=d.get("status", OFFEN), nr=int(d.get("nr", 0)),
                id=d.get("id") or _neue_id())
        if n.status not in STATUS_ALLE:
            n.status = OFFEN
        return n

    @classmethod
    def aus_entry(cls, e):
        """auswertung.Entry -> Naht (Status offen)"""
        return cls(square=e.square, x=e.x, y=e.y, art=e.art, angabe=e.angabe, dicke=e.dicke, gruppe=e.gruppe,
                   bemerkung=list(e.bemerkung), ok=e.ok, quelle=e.quelle, box=tuple(e.box), nr=e.nr)

    def zu_entry(self):
        """für output.write_excel"""
        from .auswertung import Entry
        bem = list(self.bemerkung)
        if self.status == MANUELL and "manuell ergänzt" not in bem:
            bem.append("manuell ergänzt")
        return Entry(self.square, self.x, self.y, self.art, self.angabe, self.dicke, self.gruppe, bem, True,
                     self.quelle, tuple(self.box), self.nr)


def grid_to_dict(g):
    if g is None:
        return None
    return dict(cols=[list(c) for c in g.cols], rows=[list(r) for r in g.rows], width=g.width, height=g.height,
                xb=list(g.xb), yb=list(g.yb))


def grid_from_dict(d):
    if not d:
        return None
    from .grid import Grid
    return Grid([tuple(c) for c in d["cols"]], [tuple(r) for r in d["rows"]], d["width"], d["height"],
                xb=list(d["xb"]), yb=list(d["yb"]))


def datei_pruefsumme(pfad):
    h = hashlib.sha1()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class Zeichnung:
    pfad: str                       # absoluter Pfad der PDF (kann nach dem Verschieben ungültig werden)
    datei: str                      # Dateiname
    dn: str = ""                    # Zeichnungsnummer (Spalte A)
    title: str = ""
    notes: list = field(default_factory=list)
    ex: tuple = None                # ignorierter Bereich (allgemeine Angaben) in pt
    seite: tuple = (0.0, 0.0)       # Seitengröße in pt
    grid: object = None             # grid.Grid oder None
    pruefsumme: str = ""
    naehte: list = field(default_factory=list)
    status: str = "ok"              # "ok" oder Fehlertext der Erkennung

    def aktive(self):
        return [n for n in self.naehte if n.aktiv]

    def offene(self):
        return [n for n in self.naehte if n.offen]

    def naht(self, nid):
        for n in self.naehte:
            if n.id == nid:
                return n
        return None

    def quadrat(self, x, y):
        return self.grid.square(x, y) if self.grid else "-"

    def pdf_geaendert(self):
        try:
            return bool(self.pruefsumme) and datei_pruefsumme(self.pfad) != self.pruefsumme
        except OSError:
            return False

    def to_dict(self, projektordner=None):
        rel = None
        if projektordner:
            try:
                rel = os.path.relpath(self.pfad, projektordner)
            except ValueError:   # anderes Laufwerk
                rel = None
        return dict(pfad=self.pfad, relpfad=rel, datei=self.datei, dn=self.dn, title=self.title, notes=list(self.notes),
                    ex=list(self.ex) if self.ex else None, seite=list(self.seite), grid=grid_to_dict(self.grid),
                    pruefsumme=self.pruefsumme, status=self.status, naehte=[n.to_dict() for n in self.naehte])

    @classmethod
    def from_dict(cls, d, projektordner=None):
        pfad = d.get("pfad", "")
        if not os.path.exists(pfad) and projektordner:
            for kand in ([os.path.normpath(os.path.join(projektordner, d["relpfad"]))] if d.get("relpfad") else []) + \
                        [os.path.join(projektordner, d.get("datei", ""))]:
                if os.path.exists(kand):
                    pfad = kand
                    break
        z = cls(pfad=pfad, datei=d.get("datei", os.path.basename(pfad)), dn=d.get("dn", ""), title=d.get("title", ""),
                notes=list(d.get("notes", [])), ex=tuple(d["ex"]) if d.get("ex") else None,
                seite=tuple(d.get("seite", (0, 0))), grid=grid_from_dict(d.get("grid")),
                pruefsumme=d.get("pruefsumme", ""), status=d.get("status", "ok"),
                naehte=[Naht.from_dict(n) for n in d.get("naehte", [])])
        return z

    @classmethod
    def aus_ergebnis(cls, r, pfad):
        """Ergebnis von main.process() -> Zeichnung"""
        z = cls(pfad=os.path.abspath(pfad), datei=os.path.basename(pfad), status=r.get("status", "ok"))
        try:
            z.pruefsumme = datei_pruefsumme(pfad)
        except OSError:
            pass
        if r.get("status") == "ok":
            z.dn, z.title, z.notes = r.get("dn", ""), r.get("title", ""), list(r.get("notes", []))
            z.ex, z.seite, z.grid = r.get("ex"), tuple(r.get("seite", (0, 0))), r.get("grid")
            z.naehte = [Naht.aus_entry(e) for e in r.get("entries", [])]
            neu_nummerieren(z)
        return z


@dataclass
class Projekt:
    basis: str = "Projekt"                    # Name für die Excel-Datei (Ordnername bzw. PDF-Name)
    zeichnungen: list = field(default_factory=list)
    vorlage: str = ""
    erstellt: str = ""
    geaendert: str = ""
    pfad: str = ""                            # Ort der Projektdatei (nicht in der Datei selbst)

    def alle_naehte(self):
        return [(z, n) for z in self.zeichnungen for n in z.naehte]

    def anzahl_offen(self):
        return sum(len(z.offene()) for z in self.zeichnungen)

    def anzahl_aktiv(self):
        return sum(len(z.aktive()) for z in self.zeichnungen)

    def vollstaendig_geprueft(self):
        return self.anzahl_offen() == 0

    def zeichnung_zu_pfad(self, pfad):
        ap = os.path.normcase(os.path.abspath(pfad))
        for z in self.zeichnungen:
            if os.path.normcase(os.path.abspath(z.pfad)) == ap:
                return z
        return None

    def speichern(self, pfad=None):
        pfad = pfad or self.pfad
        if not pfad:
            raise ValueError("kein Pfad für die Projektdatei")
        ordner = os.path.dirname(os.path.abspath(pfad))
        jetzt = datetime.datetime.now().isoformat(timespec="seconds")
        self.erstellt = self.erstellt or jetzt
        self.geaendert = jetzt
        daten = dict(programm="WeldWatch", version=VERSION, basis=self.basis, vorlage=self.vorlage,
                     erstellt=self.erstellt, geaendert=self.geaendert,
                     zeichnungen=[z.to_dict(ordner) for z in self.zeichnungen])
        os.makedirs(ordner, exist_ok=True)
        tmp = pfad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=1)
        os.replace(tmp, pfad)       # nie eine halb geschriebene Projektdatei hinterlassen
        self.pfad = pfad

    @classmethod
    def laden(cls, pfad):
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("programm") != "WeldWatch":
            raise ValueError("Keine WeldWatch-Projektdatei.")
        if int(d.get("version", 0)) > VERSION:
            raise ValueError("Projektdatei stammt aus einer neueren WeldWatch-Version.")
        ordner = os.path.dirname(os.path.abspath(pfad))
        p = cls(basis=d.get("basis", "Projekt"), vorlage=d.get("vorlage", ""), erstellt=d.get("erstellt", ""),
                geaendert=d.get("geaendert", ""), pfad=pfad,
                zeichnungen=[Zeichnung.from_dict(z, ordner) for z in d.get("zeichnungen", [])])
        return p


# --- Bearbeiten -------------------------------------------------------------------------------------------------

def _sortschluessel(n):
    sq = n.square or "-"
    return (sq[:1], int(sq[1:]) if sq[1:].isdigit() else 0, n.y, n.x)


def neu_nummerieren(z):
    """Laufende Nummern je Zeichnung wie im Erkennungslauf (Planquadrat, dann y, x). Gelöschte bekommen 0."""
    akt = sorted(z.aktive(), key=_sortschluessel)
    for i, n in enumerate(akt, 1):
        n.nr = i
    for n in z.naehte:
        if not n.aktiv:
            n.nr = 0
    z.naehte.sort(key=lambda n: (not n.aktiv, n.nr))


def neue_naht(z, x, y, box=None):
    """Von Hand gesetzte Naht an Position (pt). Daten sind leer und müssen ergänzt werden."""
    if box is None:
        w, h = STANDARD_BOX
        box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    else:
        box = (min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3]))
        x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    n = Naht(square=z.quadrat(x, y), x=x, y=y, art="", angabe="", dicke="", gruppe="Gr.1", ok=True,
             quelle="manuell", box=tuple(box), status=MANUELL)
    z.naehte.append(n)
    neu_nummerieren(z)
    return n


_G = r"Gr\.(?:[1-9]|1[01]|21|2[456]|22/23)"
_GRUPPE_RE = re.compile(rf"^{_G}(?: \+ {_G})*$")


def gruppe_gueltig(text):
    """Gr.1-11, Gr.21-26, Gr.22/23, Mischverbindungen als 'Gr.1 + Gr.8'"""
    return bool(_GRUPPE_RE.match((text or "").strip()))


def bestaetigen(n):
    if n.status in (OFFEN, GELOESCHT):
        n.status = BESTAETIGT


def aendern(z, n, **felder):
    """Felder setzen. Unterscheidet sich etwas, wird die Naht als "geändert" geführt (manuelle bleiben "manuell")."""
    geaendert = False
    for k, v in felder.items():
        if k == "bemerkung" and isinstance(v, str):
            v = [t.strip() for t in v.split(";") if t.strip()]
        if getattr(n, k) != v:
            setattr(n, k, v)
            geaendert = True
    if n.status in (OFFEN, BESTAETIGT):
        n.status = GEAENDERT if geaendert else BESTAETIGT
    if "square" in felder or geaendert:
        neu_nummerieren(z)
    return geaendert


def loeschen(z, n):
    """Erkannte Naht verwerfen (bleibt als gelöscht gespeichert). Von Hand gesetzte werden ganz entfernt."""
    if n.status == MANUELL:
        z.naehte.remove(n)
    else:
        n.status = GELOESCHT
    neu_nummerieren(z)


def wiederherstellen(z, n):
    if n.status == GELOESCHT:
        n.status = OFFEN
        neu_nummerieren(z)


def zusammenfuehren(alt, neu):
    """Ergebnis eines erneuten Erkennungslaufs (neu) in die vorhandene Zeichnung (alt) einarbeiten.
    Geprüfte/geänderte/gelöschte/manuelle Nähte bleiben unverändert. Offene Nähte werden durch die neue Erkennung
    ersetzt, neu gefundene als offen ergänzt. Gibt (neu_hinzu, entfernt, behalten) zurück."""
    frei = list(neu.naehte)
    behalten = hinzu = entfernt = 0
    ergebnis = []
    for n in alt.naehte:
        if n.status == MANUELL or n.status in GEPRUEFT:
            # passende neue Erkennung als "schon bekannt" markieren, damit sie nicht doppelt auftaucht
            best = min(frei, key=lambda m: (m.x - n.x) ** 2 + (m.y - n.y) ** 2, default=None)
            if best is not None and ((best.x - n.x) ** 2 + (best.y - n.y) ** 2) ** 0.5 <= MATCH_ABSTAND:
                frei.remove(best)
            ergebnis.append(n)
            behalten += 1
        else:
            best = min(frei, key=lambda m: (m.x - n.x) ** 2 + (m.y - n.y) ** 2, default=None)
            if best is not None and ((best.x - n.x) ** 2 + (best.y - n.y) ** 2) ** 0.5 <= MATCH_ABSTAND:
                frei.remove(best)
                best.id = n.id
                ergebnis.append(best)
            else:
                entfernt += 1
    for m in frei:
        ergebnis.append(m)
        hinzu += 1
    alt.naehte = ergebnis
    for feld in ("ex", "seite", "grid", "pruefsumme", "notes", "status"):
        setattr(alt, feld, getattr(neu, feld))
    if neu.dn and not alt.dn:
        alt.dn = neu.dn
    if neu.title and not alt.title:
        alt.title = neu.title
    neu_nummerieren(alt)
    return hinzu, entfernt, behalten


def zu_gruppen(p):
    """Projekt -> groups für output.write_excel (gelöschte Nähte entfallen)."""
    gruppen = []
    for z in p.zeichnungen:
        if z.status != "ok":
            continue
        entries = [n.zu_entry() for n in sorted(z.aktive(), key=lambda n: n.nr)]
        gruppen.append(dict(dn=z.dn or os.path.splitext(z.datei)[0], title=z.title, source=z.datei,
                            entries=entries, notes=list(z.notes)))
    return gruppen


def excel_schreiben(p, vorlage, ziel, nr_in_remark=True):
    """Excel erst nach vollständiger Prüfung. Wirft ValueError, solange Nähte offen sind."""
    offen = p.anzahl_offen()
    if offen:
        raise ValueError(f"Es sind noch {offen} Nähte ungeprüft.")
    gruppen = zu_gruppen(p)
    if not gruppen:
        raise ValueError("Keine Zeichnung mit Nähten im Projekt.")
    from . import output
    output.write_excel(vorlage, ziel, gruppen, nr_in_remark=nr_in_remark)
    return sum(len(g["entries"]) for g in gruppen)
