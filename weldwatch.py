import os, sys, traceback

def _basis():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

def _lauf():
    from weldwatch.main import main
    args = sys.argv[1:]
    interaktiv = not args
    if interaktiv:
        # Doppelklick: Pfad abfragen (PDF oder Ordner per Drag&Drop ins Fenster ziehen geht auch)
        print("WeldWatch - Schweißnähte aus Zeichnungen in den Prüfplan\n")
        pfad = input("PDF-Datei oder Ordner (hier hineinziehen oder Pfad einfügen, dann Enter): ").strip().strip('"')
        if not pfad:
            print("Kein Pfad angegeben."); return
        k = input("Kontroll-PDF mit markierten Funden erzeugen? (j/n): ").strip().lower()
        args = [pfad, "-o", os.path.join(_basis(), "ausgabe")] + (["--kontroll"] if k.startswith("j") else [])
    main(args)
    if interaktiv or not sys.stdin or True:
        print("\nFertig. Ergebnis im Ordner 'ausgabe' neben der exe.")

if __name__ == "__main__":
    try:
        _lauf()
    except SystemExit as e:
        if e.code not in (0, None):
            print("\nFehler beim Start (Code %s)." % e.code)
    except BaseException:
        print("\nFEHLER:\n"); traceback.print_exc()
    finally:
        try:
            input("\nEnter drücken zum Schließen ...")
        except Exception:
            pass
