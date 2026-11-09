"""Ausgabe im Format der Firmenvorlage (Blatt SNP) plus Protokoll-Blatt."""
import copy, datetime
import openpyxl
from openpyxl.styles import Font

FIRST = 7

def write_excel(template, out_path, entries, drawing_no, title, source_name, notes=(), nr_in_remark=True):
    wb = openpyxl.load_workbook(template)
    ws = wb["SNP"] if "SNP" in wb.sheetnames else wb.active
    ws["C3"] = title or ws["C3"].value
    ws["C4"] = drawing_no
    ws["O4"] = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ws["O3"] = "Rev.00"
    # Stil der Musterzeile merken, Inhalt der Muster-/Leerzeilen löschen
    style = {c: copy.copy(ws.cell(FIRST, c)._style) for c in range(1, 16)}
    height = ws.row_dimensions[FIRST].height
    for r in range(FIRST, max(ws.max_row, FIRST + len(entries)) + 1):
        for c in range(1, 16):
            ws.cell(r, c).value = None
    for i, e in enumerate(entries):
        r = FIRST + i
        for c in range(1, 16):
            ws.cell(r, c)._style = copy.copy(style[c])
        ws.row_dimensions[r].height = height
        ws.cell(r, 1).value = drawing_no
        ws.cell(r, 2).value = e.square
        ws.cell(r, 3).value = e.art
        ws.cell(r, 4).value = e.dicke or None
        ws.cell(r, 5).value = e.angabe
        ws.cell(r, 8).value = e.gruppe
        rem = ([f"Nr. {e.nr}"] if nr_in_remark else []) + e.bemerkung
        ws.cell(r, 15).value = "; ".join(rem) or None
    # Protokoll
    wp = wb.create_sheet("Protokoll")
    wp.append(["Datei", source_name]); wp.append(["Erkannte Nähte", len(entries)])
    wp.append(["davon zu prüfen", sum(1 for e in entries if not e.ok)])
    for n in notes:
        wp.append(["Hinweis", n])
    wp.append([])
    wp.append(["Nr.", "Planquadrat", "Nahtart", "Zeichnungsangabe", "Gruppe", "Quelle", "Status", "Bemerkung", "x (pt)", "y (pt)"])
    for c in wp[wp.max_row]:
        c.font = Font(bold=True)
    for e in entries:
        wp.append([e.nr, e.square, e.art, e.angabe, e.gruppe, e.quelle, "ok" if e.ok else "prüfen",
                   "; ".join(e.bemerkung), round(e.x, 1), round(e.y, 1)])
    wb.save(out_path)
