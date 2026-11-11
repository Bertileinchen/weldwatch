@echo off
rem Baut aus dem Programm eine eigenständige exe (ohne Python auf dem Zielrechner).
setlocal
cd /d "%~dp0"
if exist python_pfad.txt (set /p PY=<python_pfad.txt) else (set PY=python)
"%PY%" -m PyInstaller --noconfirm --onedir --noconsole --name WeldWatch --collect-all pypdfium2 --collect-all pdfplumber --collect-all pdfminer --collect-all cv2 --collect-all tkinterdnd2 weldwatch.py
xcopy /E /I /Y vorlage dist\WeldWatch\vorlage
copy /Y weldwatch_config.json dist\WeldWatch\
if exist tesseract xcopy /E /I /Y tesseract dist\WeldWatch\tesseract
echo.
echo Fertig: dist\WeldWatch\WeldWatch.exe   (ganzen Ordner WeldWatch weitergeben)
pause
