@echo off
rem Wie Auswerten.bat, erzeugt zusätzlich je Zeichnung ein Kontroll-PDF (Funde markiert).
setlocal
cd /d "%~dp0"
if exist python_pfad.txt (set /p PY=<python_pfad.txt) else (set PY=python)
"%PY%" -m weldwatch.main "%~1" -o ausgabe --kontroll
pause
