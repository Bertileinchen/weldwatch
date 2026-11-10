"""Ausgabe im Format der Firmenvorlage (Blatt SNP) plus Protokoll-Blatt."""
import copy, datetime
import openpyxl
from openpyxl.styles import Font, Alignment

FIRST = 7

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
        ws.cell(r, 3).value = e.art
        ws.cell(r, 4).value = e.dicke or None
        ws.cell(r, 5).value = e.angabe
        for c in (2, 5):   # Zeilenumbruch: Nr. unter Planquadrat, beidseitige Nähte untereinander
            al = copy.copy(ws.cell(r, c).alignment); al.wrap_text = True
            ws.cell(r, c).alignment = al
        ws.cell(r, 8).value = e.gruppe
        ws.cell(r, 15).value = "; ".join(e.bemerkung) or None
    # Protokoll
    wp = wb.create_sheet("Protokoll")
    wp.append(["Zeichnungen", len(groups)]); wp.append(["Erkannte Nähte", len(entries_all)])
    wp.append(["davon zu prüfen", sum(1 for _, e in entries_all if not e.ok)])
    for g in groups:
        wp.append([])
        wp.append(["Datei", g["source"], "Zeichnungsnr.", g["dn"], "Nähte", len(g["entries"])])
        for n in g["notes"]:
            wp.append(["Hinweis", n])
    wp.append([])
    wp.append(["Zeichnung", "Nr.", "Planquadrat", "Nahtart", "Zeichnungsangabe", "Gruppe", "Quelle", "Status", "Bemerkung", "x (pt)", "y (pt)"])
    for c in wp[wp.max_row]:
        c.font = Font(bold=True)
    for dn, e in entries_all:
        wp.append([dn, e.nr, e.square, e.art, e.angabe.replace("\n", " / "), e.gruppe, e.quelle, "ok" if e.ok else "prüfen",
                   "; ".join(e.bemerkung), round(e.x, 1), round(e.y, 1)])
    wb.save(out_path)
