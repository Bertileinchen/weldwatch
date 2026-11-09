"""Kommandozeile:  python -m weldwatch.main <PDF oder Ordner> [-o Ausgabeordner] [--kontroll] [--vorlage Datei.xlsx]"""
import argparse, os, sys, glob
import pdfplumber
from . import config, vector, grid, titleblock, exclude, symbols, auswertung, output, kontroll, raster

def default_vorlage():
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.join(os.path.dirname(__file__), "..")
    return os.path.abspath(os.path.join(base, "vorlage", "Vorlage_Schweissnahtpruefplan.xlsx"))

def process_raster(pdf_path, name, cfg):
    """Rasterbild: Farbmaske -> Linien -> Symbole; Text per OCR (Tesseract)."""
    notes = ["Rasterbild: Erkennung weniger sicher als bei Vektor-PDF - Kontroll-PDF prüfen."]
    dpi = cfg["raster_dpi"]
    rgb = raster.render(pdf_path, dpi)
    mask = raster.annotation_mask(rgb, cfg)
    segs = raster.detect_segments(mask, dpi)
    tess = raster._find_tesseract()
    import cv2
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ocr_cols = raster.ocr_column_numbers(tess, gray, dpi) if tess else None
    g = grid.build_grid_raster(gray < 120, dpi, ocr_cols)
    if not g:
        notes.append("Planquadrat-Raster nicht erkannt, Planquadrat = '-'.")
    dn, title, ex = name, "", None
    if tess:
        pw = raster.ocr_page_words(tess, rgb, dpi)
        ex = exclude.find_exclusion(pw, cfg)
        if ex is None:
            notes.append("Block 'allgemeine Angaben' nicht gefunden (nichts ignoriert).")
        dn, title = titleblock.read_title(pw, cfg, name)
        provider = lambda f: raster.ocr_symbol_words(tess, mask, dpi, f, cfg)
    else:
        notes.append("Tesseract (OCR) nicht gefunden: Maße und Werkstoffgruppen werden NICHT gelesen, "
                     "Block 'allgemeine Angaben' wird nicht ignoriert. Siehe README.")
        provider = lambda f: []
    rcfg = dict(cfg, tol=cfg["raster_tol"], symbol_min_len=cfg["raster_symbol_min_len"], pattern_mode=True)
    found = symbols.find_symbols(segs, [], rcfg, word_provider=provider)
    return g, dn, title, ex, found, notes

def process(pdf_path, args, cfg):
    name = os.path.splitext(os.path.basename(pdf_path))[0]
    notes = []
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) > 1:
            notes.append(f"Datei hat {len(pdf.pages)} Seiten, ausgewertet wird nur Seite 1.")
        page = pdf.pages[0]
        kind = vector.page_kind(page)
        if kind == "leer":
            return dict(name=name, status="Seite leer / nicht lesbar", n=0)
        if kind == "raster":
            g, dn, title, ex, found, rnotes = process_raster(pdf_path, name, cfg)
            notes += rnotes
            words = []
        else:
            segs, words = vector.read_page(page, cfg)
            g = grid.build_grid(words, page.width, page.height)
            if not g:
                notes.append("Planquadrat-Raster nicht erkannt, Planquadrat = '-'.")
            dn, title = titleblock.read_title(words, cfg, name)
            ex = exclude.find_exclusion(words, cfg)
            if ex is None:
                notes.append("Block 'allgemeine Angaben' nicht gefunden (nichts ignoriert).")
            found = symbols.find_symbols(segs, words, cfg)
        taken = [(f.x0, f.y - 24, f.x1, f.y + 24) for f in found]
        pt = symbols.find_pt_labels(words, taken)
        entries = auswertung.build_entries(found, pt, g, ex, cfg)
    out_xlsx = os.path.join(args.out, f"{name}_Pruefplan.xlsx")
    output.write_excel(args.vorlage, out_xlsx, entries, dn, title, os.path.basename(pdf_path), notes,
                       nr_in_remark=not args.ohne_nr)
    if args.kontroll:
        items = [dict(nr=e.nr, box=e.box, ok=e.ok) for e in entries]
        img = kontroll.render_overlay(pdf_path, items, ex, scale=args.kontroll_skala)
        kontroll.save_pdf(img, os.path.join(args.out, f"{name}_Kontrolle.pdf"))
    return dict(name=name, status="ok", n=len(entries), pruefen=sum(1 for e in entries if not e.ok),
                ignoriert=ex is not None, notes=notes)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Schweißnähte aus Zeichnungen (Vektor-PDF) in den Prüfplan übernehmen")
    ap.add_argument("eingabe", help="PDF-Datei oder Ordner mit PDFs")
    ap.add_argument("-o", "--out", default="ausgabe", help="Ausgabeordner")
    ap.add_argument("--vorlage", default=default_vorlage(), help="Excel-Vorlage (Blatt SNP)")
    ap.add_argument("--kontroll", action="store_true", help="Kontroll-PDF mit markierten Funden erzeugen")
    ap.add_argument("--kontroll-skala", type=float, default=1.5)
    ap.add_argument("--ohne-nr", action="store_true", help="Laufende Nr. nicht in Bemerkung schreiben")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = config.load(args.config)
    os.makedirs(args.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(args.eingabe, "*.pdf"))) if os.path.isdir(args.eingabe) else [args.eingabe]
    lines = []
    for f in files:
        try:
            r = process(f, args, cfg)
        except Exception as ex:   # eine fehlerhafte Datei darf den Ordnerlauf nicht stoppen
            r = dict(name=os.path.basename(f), status=f"FEHLER: {ex}", n=0)
        msg = f"{r['name']}: {r['status']}" + (f" - {r['n']} Nähte, davon {r.get('pruefen', 0)} zu prüfen" if r["status"] == "ok" else "")
        print(msg); lines.append(msg)
        for n in r.get("notes", []):
            print("   Hinweis:", n); lines.append("   Hinweis: " + n)
    with open(os.path.join(args.out, "Zusammenfassung.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

if __name__ == "__main__":
    main()
