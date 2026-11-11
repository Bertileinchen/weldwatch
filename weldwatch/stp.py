"""STP-Datei (STEP AP214, z. B. aus Solid Edge) lesen: Teilekatalog mit Blechstärke je Teil.

Reiner Python-Parser ohne CAD-Bibliothek, bleibt offline. Liefert je Teil Name, Zeichnungsnummer, Position,
Benennung und eine aus der Geometrie berechnete Dicke (Vorschlag, von Hand prüfbar).

Dicke:
- Blech, Winkel, Formrohr, U-Profil: kleinster Abstand zweier paralleler Planflächen mit entgegengesetzter Normale,
  wobei nur große Flächen zählen (>= 25 % der größten Fläche). Gilt auch für gekantete Teile und Rechteckrohre.
- Rundrohr: Differenz der Radien koaxialer Zylinderflächen (Außen- minus Innenradius).
- Unplausible Werte (außerhalb 1,5-40 mm), massive Teile (Gewindebutzen, Schrauben ...) und Teile ohne Ergebnis
  werden als "unsicher" bzw. "fehlt" markiert.
"""
import collections, math, re

DICKE_MIN, DICKE_MAX = 1.5, 40.0
_MASSIV = re.compile(r"GEWINDE|SCHRAUBE|MUTTER|SCHEIBE|BUTZEN|KLOTZ|BOLZEN|STIFT|NIET|Kehlnaht", re.I)
_RUND = re.compile(r"(^|_)ROHR($|_)", re.I)          # Rundrohr (nicht FORMROHR)
_NAME = re.compile(r"^(?P<links>.*?)__(?P<ben>[^_].*)$")

OK, UNSICHER, FEHLT = "ok", "unsicher", "fehlt"


class Teil:
    """Ein Bauteil des STP. dicke in mm oder None."""
    __slots__ = ("name", "zeichnung", "pos", "teilenummer", "benennung", "dicke", "status", "hinweis")

    def __init__(self, name, zeichnung="", pos="", teilenummer="", benennung="", dicke=None, status=FEHLT, hinweis=""):
        self.name, self.zeichnung, self.pos, self.teilenummer = name, zeichnung, pos, teilenummer
        self.benennung, self.dicke, self.status, self.hinweis = benennung, dicke, status, hinweis

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d.get(k, "" if k not in ("dicke",) else None) for k in cls.__slots__})


def teilname_zerlegen(name):
    """'WN401-00001-2_20__BLECH' -> (zeichnung 'WN401-00001-2', pos '20', teilenummer 'WN401-00001-2.20', benennung 'BLECH').
    Namen ohne erkennbare Position (SAP-Nummern, Halbzeug wie 'WN-BL-265X80X3-01__BLECH') behalten sich selbst als Teilenummer."""
    m = _NAME.match(name)
    links, ben = (m.group("links"), m.group("ben")) if m else (name, "")
    teile = links.split("_")
    if len(teile) > 1 and all(re.fullmatch(r"\d+[A-Z]?", t) for t in teile[1:]):
        zng, pos = teile[0], ".".join(teile[1:])
        return zng, pos, f"{zng}.{pos}", ben
    return "", "", links, ben


def _wert_dicke(planes):
    """planes: Liste (normale, offset, flaeche); kleinster Abstand großer, gegenüberliegender Planflächen."""
    if not planes:
        return None
    amax = max(p[2] for p in planes)
    gross = [p for p in planes if p[2] >= 0.25 * amax]
    kand = []
    for i, (n, d, _a) in enumerate(gross):
        for (m, e, _b) in gross[i + 1:]:
            if n[0] * m[0] + n[1] * m[1] + n[2] * m[2] < -0.999:
                gap = abs(d - (-e))
                if gap > 0.05:
                    kand.append(gap)
    return round(min(kand), 2) if kand else None


def _wert_rohr(cyl):
    """cyl: Liste (ursprung, achse, radius). Außen- minus Innenradius koaxialer Zylinder."""
    gruppen = collections.defaultdict(set)
    for o, a, r in cyl:
        l = math.sqrt(sum(x * x for x in a)) or 1.0
        a = tuple(x / l for x in a)
        if a[0] < 0 or (a[0] == 0 and (a[1] < 0 or (a[1] == 0 and a[2] < 0))):
            a = tuple(-x for x in a)
        # Abstand der Achse vom Nullpunkt (Lotpunkt) als Schlüssel für "gleiche Achse"
        t = sum(o[i] * a[i] for i in range(3))
        fuss = tuple(round(o[i] - t * a[i], 1) for i in range(3))
        gruppen[(tuple(round(x, 4) for x in a), fuss)].add(round(r, 3))
    best = None
    for radien in gruppen.values():
        rs = sorted(radien, reverse=True)
        if len(rs) >= 2 and (best is None or rs[0] > best[0]):
            best = (rs[0], rs[1])
    return round(best[0] - best[1], 2) if best else None


def _bewerten(name, dicke):
    if _MASSIV.search(name):
        return dicke, UNSICHER, "massives Teil / Dicke nicht sinnvoll"
    if dicke is None:
        return None, FEHLT, "keine Dicke ermittelt"
    if not (DICKE_MIN <= dicke <= DICKE_MAX):
        return dicke, UNSICHER, "Wert unplausibel (gekantet/ausgeschnitten?)"
    return dicke, OK, ""


class _Step:
    """Minimaler Leser der Datenzeilen eines STEP-Files."""

    def __init__(self, text):
        text = text[text.index("DATA;"):]
        self.ent = {}
        for m in re.finditer(r"#(\d+)\s*=\s*(.*?);\s*(?=\n#|\nENDSEC)", text, re.S):
            self.ent[int(m.group(1))] = m.group(2)
        self.nach_typ = collections.defaultdict(list)
        for k, s in self.ent.items():
            s2 = s.lstrip()
            t = "COMPLEX" if s2.startswith("(") else s2[:s2.index("(")].strip()
            self.nach_typ[t].append(k)
        self._ref = re.compile(r"#(\d+)")
        self._pt = {}

    def typ(self, e):
        s = self.ent[e].lstrip()
        return "COMPLEX" if s.startswith("(") else s[:s.index("(")].strip()

    def args(self, e):
        s = self.ent[e]
        return s[s.index("("):]

    def refs(self, e):
        return [int(x) for x in self._ref.findall(self.args(e))]

    def vec(self, e):
        if e not in self._pt:
            m = re.search(r"\(\s*'[^']*'\s*,\s*\(([^)]*)\)", self.args(e))
            self._pt[e] = tuple(float(x) for x in m.group(1).split(","))
        return self._pt[e]

    def achse(self, e):
        r = self.refs(e)
        return self.vec(r[0]), self.vec(r[1])


def _schleife_punkte(st, loop):
    pts = []
    for oe in st.refs(loop):
        r = st.refs(oe)
        ori = ".T." in st.args(oe).split(",")[-1]
        er = st.refs(r[0])
        v = er[0] if ori else er[1]
        pts.append(st.vec(st.refs(v)[0]))
    return pts


def _flaeche(pts, n):
    s = [0.0, 0.0, 0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        s[0] += a[1] * b[2] - a[2] * b[1]
        s[1] += a[2] * b[0] - a[0] * b[2]
        s[2] += a[0] * b[1] - a[1] * b[0]
    return abs(s[0] * n[0] + s[1] * n[1] + s[2] * n[2]) / 2


def _geometrie(st, solid):
    planes, cyl = [], []
    shell = st.refs(solid)[0]
    for f in st.refs(shell):
        a = st.args(f)
        r = st.refs(f)
        surf = r[-1]
        gleich = ".T." in a.split(",")[-1]
        t = st.typ(surf)
        if t == "PLANE":
            o, d = st.achse(st.refs(surf)[0])
            l = math.sqrt(sum(x * x for x in d))
            d = tuple(x / l for x in d)
            if not gleich:
                d = tuple(-x for x in d)
            bounds = r[:-1]
            aussen = [b for b in bounds if st.typ(b) == "FACE_OUTER_BOUND"] or bounds[:1]
            try:
                ar = _flaeche(_schleife_punkte(st, st.refs(aussen[0])[0]), d)
            except Exception:
                ar = 0.0
            planes.append((d, sum(d[i] * o[i] for i in range(3)), ar))
        elif t == "CYLINDRICAL_SURFACE":
            m = re.search(r",\s*([-0-9.eE+]+)\s*\)\s*$", st.args(surf).strip())
            o, d = st.achse(st.refs(surf)[0])
            cyl.append((o, d, float(m.group(1))))
    return planes, cyl


def lese_stp(pfad_oder_text):
    """STP-Datei (Pfad) oder Text lesen -> Liste Teil (je Produktname einmal, nur Produkte mit Festkörper)."""
    if "\n" in pfad_oder_text or pfad_oder_text.lstrip().startswith("ISO-10303"):
        text = pfad_oder_text
    else:
        with open(pfad_oder_text, "rb") as f:
            text = f.read().decode("latin-1")
    st = _Step(text)
    produkt = {}
    for k in st.nach_typ["PRODUCT"]:
        m = re.match(r"\(\s*'([^']*)'\s*,\s*'([^']*)'", st.args(k))
        if m:
            produkt[k] = m.group(2)
    formation = {k: st.refs(k)[-1] for t in ("PRODUCT_DEFINITION_FORMATION", "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE")
                 for k in st.nach_typ[t]}
    pdef = {k: st.refs(k)[0] for k in st.nach_typ["PRODUCT_DEFINITION"]}
    pds = {k: st.refs(k)[0] for k in st.nach_typ["PRODUCT_DEFINITION_SHAPE"]}
    rep_pd = {}
    for k in st.nach_typ["SHAPE_DEFINITION_REPRESENTATION"]:
        a, b = st.refs(k)
        if a in pds and pds[a] in pdef:
            rep_pd[b] = pds[a]
    rel = collections.defaultdict(list)
    for k in st.nach_typ["SHAPE_REPRESENTATION_RELATIONSHIP"]:
        a, b = st.refs(k)
        rel[a].append(b)
        rel[b].append(a)
    items = {k: st.refs(k) for t in ("ADVANCED_BREP_SHAPE_REPRESENTATION", "SHAPE_REPRESENTATION") for k in st.nach_typ[t]}
    solids = {}
    for rep, pd in rep_pd.items():
        try:
            name = produkt[formation[pdef[pd]]]
        except KeyError:
            continue
        for r2 in [rep] + rel.get(rep, []):
            for it in items.get(r2, []):
                if it in st.ent and st.typ(it) == "MANIFOLD_SOLID_BREP":
                    solids.setdefault(name, it)
    teile = []
    for name, sol in solids.items():
        zng, pos, tnr, ben = teilname_zerlegen(name)
        planes, cyl = _geometrie(st, sol)
        d = _wert_dicke(planes)
        if _RUND.search(ben or name) and not planes[2:]:
            d = _wert_rohr(cyl) or d
        elif d is None and cyl:
            d = _wert_rohr(cyl)
        d, status, hinweis = _bewerten(name, d)
        teile.append(Teil(name, zng, pos, tnr, ben, d, status, hinweis))
    teile.sort(key=lambda t: t.name)
    return teile
