@echo off
rem PDF-Datei oder Ordner auf diese Datei ziehen.  Ergebnis im Ordner "ausgabe" neben dieser Datei.
rem Python-Pfad (portables WinPython) einmalig in python_pfad.txt eintragen, z. B. C:\Tools\WinPython\python-3.12.x.amd64\python.exe
setlocal
cd /d "%~dp0"
if exist python_pfad.txt (set /p PY=<python_pfad.txt) else (set PY=python)
"%PY%" -m weldwatch.main "%~1" -o ausgabe
pause
