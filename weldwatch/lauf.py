"""Erkennungslauf für die GUI: PDF-Dateien -> Zeichnungen (ohne Excel). Nutzt dieselbe Erkennung wie die Kommandozeile."""
import glob, os, sys, types
from .projekt import Zeichnung, Projekt


def basis_ordner():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else \
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ausgabe_ordner():
    """Ordner 'ausgabe' neben dem Programm; ist er nicht beschreibbar, im Benutzerordner."""
    for ordner in (os.path.join(basis_ordner(), "ausgabe"), os.path.join(os.path.expanduser("~"), "WeldWatch", "ausgabe")):
        try:
            os.makedirs(ordner, exist_ok=True)
            test = os.path.join(ordner, ".schreibtest")
            with open(test, "w") as f:
                f.write("x")
            os.remove(test)
            return ordner
        except OSError:
            continue
    return os.getcwd()


def pdfs_in(eingabe):
    if os.path.isdir(eingabe):
        return sorted(glob.glob(os.path.join(eingabe, "*.pdf")) + glob.glob(os.path.join(eingabe, "*.PDF")))
    return [eingabe]


def projektname(eingabe):
    if os.path.isdir(eingabe):
        return os.path.basename(os.path.normpath(eingabe)) or "Projekt"
    return os.path.splitext(os.path.basename(eingabe))[0]


def standard_projektpfad(eingabe):
    return os.path.join(ausgabe_ordner(), projektname(eingabe) + ".wwp")


def default_vorlage():
    return os.path.join(basis_ordner(), "vorlage", "Vorlage_Schweissnahtpruefplan.xlsx")


def erkennen(pfade, fortschritt=None):
    """Liste von Zeichnungen (Status offen). fortschritt(i, n, dateiname) wird vor jeder Datei gerufen."""
    from . import config, main
    cfg = config.load(os.path.join(basis_ordner(), "weldwatch_config.json"))
    args = types.SimpleNamespace(kontroll=False, out=ausgabe_ordner(), kontroll_skala=1.5)
    out = []
    for i, f in enumerate(pfade):
        if fortschritt:
            fortschritt(i, len(pfade), os.path.basename(f))
        try:
            r = main.process(f, args, cfg)
        except Exception as ex:   # eine fehlerhafte Datei darf den Lauf nicht stoppen
            r = dict(name=os.path.basename(f), status=f"FEHLER: {ex}", n=0)
        out.append(Zeichnung.aus_ergebnis(r, f))
    return out


def neues_projekt(eingabe, zeichnungen, pfad=None):
    p = Projekt(basis=projektname(eingabe), zeichnungen=zeichnungen, vorlage="", pfad=pfad or standard_projektpfad(eingabe))
    return p


def einarbeiten(p, neue):
    """Neue Erkennungsergebnisse in ein bestehendes Projekt einarbeiten (geprüfte Nähte bleiben). Gibt Textzeilen zurück."""
    from .projekt import zusammenfuehren
    meldungen = []
    for z in neue:
        alt = p.zeichnung_zu_pfad(z.pfad)
        if alt is None:
            p.zeichnungen.append(z)
            meldungen.append(f"{z.datei}: neu aufgenommen, {len(z.naehte)} Nähte")
        elif z.status != "ok":
            meldungen.append(f"{z.datei}: Erkennung fehlgeschlagen ({z.status}) - bisherige Daten unverändert")
        else:
            hinzu, entfernt, behalten = zusammenfuehren(alt, z)
            meldungen.append(f"{z.datei}: {hinzu} neu, {entfernt} entfallen, {behalten} geprüfte/manuelle unverändert")
    return meldungen
