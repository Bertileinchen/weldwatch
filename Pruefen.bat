@echo off
rem Startet das Prüf-Fenster aus dem Quellcode (mit Python). PDF, Ordner oder Projektdatei (.wwp) kann im Fenster geöffnet oder hineingezogen werden.
setlocal
cd /d "%~dp0"
if exist python_pfad.txt (set /p PY=<python_pfad.txt) else (set PY=python)
"%PY%" weldwatch.py %*
