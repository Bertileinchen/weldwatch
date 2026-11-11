"""Ausgabe im Format der Firmenvorlage (Blatt SNP) plus Protokoll-Blatt."""
import copy, datetime, re
import openpyxl
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

FIRST = 7
from . import pruefklassen

def wps_spalte(ws):
    """Spaltennummer der Überschrift "WPS" in den Kopfzeilen der Vorlage (nächste zur Datenzeile); None wenn nicht gefunden."""
    for r in range(FIRST - 1, 0, -1):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str) and re.search(r"\bWPS\b", v, re.I):
                return c
    return None

# Spalten, die das Programm selbst aus der Erkennung füllt; alle übrigen Spalten (F, G, I-N) sind von Hand auszufüllen
ERKANNTE_SPALTEN = ("A", "B", "C", "D", "E", "H", "O")


def vorlage_spalten(template):
    """Kopfzeilen-Texte der Vorlage je Spalte (A-O) und die WPS-Spalte: (dict Buchstabe -> Text, WPS-Buchstabe oder None).
    Der Text stammt aus der Kopfzeile direkt über den Datenzeilen (verbundene Zellen werden berücksichtigt)."""
    from openpyxl.utils import get_column_letter
    wb = openpyxl.load_workbook(template)
    ws = wb["SNP"] if "SNP" in wb.sheetnames else wb.active
    merged = list(ws.merged_cells.ranges)
    labels = {}
    for c in range(1, 16):
        buchstabe = get_column_letter(c)
        text = ""
        for r in range(FIRST - 1, max(FIRST - 4, 0), -1):
            v = ws.cell(r, c).value
            if not (isinstance(v, str) and v.strip()):
                for m in merged:
                    if m.min_row <= r <= m.max_row and m.min_col <= c <= m.max_col:
                        v = ws.cell(m.min_row, m.min_col).value
                        break
            if isinstance(v, str) and v.strip():
                text = " ".join(v.split())
                break
        labels[buchstabe] = text or f"Spalte {buchstabe}"
    wc = wps_spalte(ws)
    return labels, (get_column_letter(wc) if wc else None)


def zusatz_spalten(labels, wps_buchstabe):
    """[(Buchstabe, Überschrift)] der Spalten, die von Hand ausgefüllt werden (ohne erkannte Spalten und ohne WPS-Spalte)."""
    return [(b, t) for b, t in labels.items() if b not in ERKANNTE_SPALTEN and b != wps_buchstabe]


def write_excel(template, out_path, groups, nr_in_remark=True):
    """groups: Liste von dict(dn, title, source, entries, notes) - eine Zeichnung je Eintrag, alle Nähte in EINER Liste."""
    entries_all = [(g["dn"], e) for g in groups for e in g["entries"]]
    wb = openpyxl.load_workbook(template)
    ws = wb["SNP"] if "SNP" in wb.sheetnames else wb.active
    titles = []
    for g in groups:
        if g["title"] and g["title"] not in titles:
            titles.append(g["title"])
    dns = [g["dn"] for g in groups if g["dn"]]
    if len(groups) == 1:
        ws["C3"] = titles[0] if titles else ws["C3"].value
    else:
        ws["C3"] = f"Sammelliste ({len(groups)} Zeichnungen)"
    ws["C4"] = dns[0] if len(dns) == 1 else (", ".join(dns) if dns else None)
    ws["O4"] = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ws["O3"] = "Rev.00"
    # Stil der Musterzeile merken, Inhalt der Muster-/Leerzeilen löschen
    wps_col = wps_spalte(ws)
    labels, _w = vorlage_spalten(template)
    rolle = pruefklassen.rollen(labels)
    spalte_von = {r: b for b, r in rolle.items()}
    style = {c: copy.copy(ws.cell(FIRST, c)._style) for c in range(1, 16)}
    height = ws.row_dimensions[FIRST].height
    for r in range(FIRST, max(ws.max_row, FIRST + len(entries_all)) + 1):
        for c in range(1, 16):
            ws.cell(r, c).value = None
    for i, (dn, e) in enumerate(entries_all):
        r = FIRST + i
        for c in range(1, 16):
            ws.cell(r, c)._style = copy.copy(style[c])
        ws.row_dimensions[r].height = height
        ws.cell(r, 1).value = dn
        ws.cell(r, 2).value = f"{e.square}\n({e.nr})" if nr_in_remark else e.square
        ws.cell(r, 3).value = f"{e.art}\n{e.stoss}" if e.stoss else e.art
        ws.cell(r, 4).value = e.dicke or None
        ws.cell(r, 5).value = e.angabe
        for c in (2, 3, 5):   # Zeilenumbruch: Nr. unter Planquadrat, T-Stoß unter Nahtart, beidseitige Nähte untereinander
            al = copy.copy(ws.cell(r, c).alignment); al.wrap_text = True
            ws.cell(r, c).alignment = al
        ws.cell(r, 8).value = e.gruppe
        if wps_col and e.wps:
            ws.cell(r, wps_col).value = e.wps
        ws.cell(r, 15).value = ";\n".join(e.bemerkung) or None     # jeder Vermerk in eigener Zeile
        al = copy.copy(ws.cell(r, 15).alignment); al.wrap_text = True
        ws.cell(r, 15).alignment = al
        extra = dict(getattr(e, "extra", None) or {})
        if "cp" in spalte_von:
            extra[spalte_von["cp"]] = extra.get(spalte_von["cp"]) or pruefklassen.STANDARD_CP
        if "ct" in spalte_von:
            extra[spalte_von["ct"]] = extra.get(spalte_von["ct"]) or pruefklassen.STANDARD_CT
        ct = extra.get(spalte_von["ct"]) if "ct" in spalte_von else pruefklassen.STANDARD_CT
        for rl, wert in zip(("ut", "mt", "vt"), pruefklassen.umfang(ct)):   # Prüfumfang folgt aus der Prüfklasse
            if rl in spalte_von:
                extra[spalte_von[rl]] = wert
        for buchstabe, wert in extra.items():
            if wert and buchstabe not in ERKANNTE_SPALTEN and buchstabe != (get_column_letter(wps_col) if wps_col else None):
                zelle = ws[f"{buchstabe}{r}"]
                zelle.value = wert
                al = copy.copy(zelle.alignment); al.wrap_text = True
                zelle.alignment = al
    # Protokoll
    wp = wb.create_sheet("Protokoll")
    wp.append(["Zeichnungen", len(groups)]); wp.append(["Erkannte Nähte", len(entries_all)])
    wp.append(["davon zu prüfen", sum(1 for _, e in entries_all if not e.ok)])
    if wps_col is None and any(e.wps for _, e in entries_all):
        wp.append(["Hinweis", "Spalte \"WPS\" in der Vorlage nicht gefunden - Zusatzinfo steht nur in diesem Protokoll"])
    for g in groups:
        wp.append([])
        wp.append(["Datei", g["source"], "Zeichnungsnr.", g["dn"], "Nähte", len(g["entries"])])
        for n in g["notes"]:
            wp.append(["Hinweis", n])
    wp.append([])
    wp.append(["Zeichnung", "Nr.", "Planquadrat", "Nahtart", "Zeichnungsangabe", "Gruppe", "Quelle", "Status", "Bemerkung", "x (pt)", "y (pt)", "Zusatz Nahtart", "WPS-Zusatzinfo"])
    for c in wp[wp.max_row]:
        c.font = Font(bold=True)
    for dn, e in entries_all:
        wp.append([dn, e.nr, e.square, e.art, e.angabe.replace("\n", " / "), e.gruppe, e.quelle, "ok" if e.ok else "prüfen",
                   "; ".join(e.bemerkung), round(e.x, 1), round(e.y, 1), e.stoss, e.wps])
    wb.save(out_path)
