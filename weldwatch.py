import os, sys, traceback

# Die exe ist ohne Konsolenfenster gebaut: dann gibt es keine Standard-Ströme, Ausgaben gehen ins Leere.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")

def _basis():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

def _konsole_dialog():
    from weldwatch.main import main
    # Alte Texteingabe (Aufruf mit --konsole): Pfad abfragen, dann Auswertung ohne Prüf-Fenster
    print("WeldWatch - Schweißnähte aus Zeichnungen in den Prüfplan\n")
    pfad = input("PDF-Datei oder Ordner (hier hineinziehen oder Pfad einfügen, dann Enter): ").strip().strip('"')
    if not pfad:
        print("Kein Pfad angegeben."); return
    k = input("Kontroll-PDF mit markierten Funden erzeugen? (j/n): ").strip().lower()
    main([pfad, "-o", os.path.join(_basis(), "ausgabe")] + (["--kontroll"] if k.startswith("j") else []))
    print("\nFertig. Ergebnis im Ordner 'ausgabe' neben der exe.")

def _lauf():
    """True, wenn das Prüf-Fenster gelaufen ist (dann keine Konsolen-Abfrage am Ende)."""
    args = sys.argv[1:]
    # Doppelklick (ohne Argumente) oder Projektdatei (.wwp) -> Prüf-Fenster mit Erkennung, Bearbeitung, Projektdatei
    if not args or args == ["--gui"] or (len(args) == 1 and args[0].lower().endswith(".wwp")):
        from weldwatch.gui import start
        start(args[0] if args and args[0] != "--gui" else None)
        return True
    if args == ["--konsole"]:
        _konsole_dialog()
        return False
    # Kommandozeile / Auswerten.bat: wie bisher direkt Excel ohne Prüf-Fenster
    from weldwatch.main import main
    main(args)
    print("\nFertig. Ergebnis im Ordner 'ausgabe'.")
    return False

if __name__ == "__main__":
    gui_lauf, code = False, 0
    try:
        gui_lauf = _lauf()
    except SystemExit as e:
        if e.code not in (0, None):
            print("\nFehler beim Start (Code %s)." % e.code)
            code = 1
    except BaseException:
        print("\nFEHLER:\n"); traceback.print_exc(); code = 1
        if getattr(sys, "frozen", False):      # ohne Konsole sonst unsichtbar: Protokoll schreiben und melden
            try:
                pfad = os.path.join(_basis(), "weldwatch_start_fehler.log")
                with open(pfad, "w", encoding="utf-8") as lg:
                    traceback.print_exc(file=lg)
                if os.name == "nt":
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(0, "WeldWatch konnte nicht starten.\nDetails: " + pfad, "WeldWatch", 0x10)
            except Exception:
                pass
    if not gui_lauf:
        try:
            input("\nEnter drücken zum Schließen ...")
        except Exception:
            pass
    sys.exit(code)
