@echo off
rem ---------------------------------------------------------------------------
rem rm2k2mv - grafische Oberflaeche
rem
rem Doppelklick genuegt: Projektordner waehlen, Zielordner waehlen, los.
rem Fuer die Kommandozeile siehe run.bat.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist "log" mkdir "log"

rem pythonw startet ohne Konsolenfenster, python ist die Rueckfallebene.
where pythonw >NUL 2>&1
if %ERRORLEVEL%==0 (
    start "" pythonw -X utf8 -m rm2k2mv gui
) else (
    python -X utf8 -m rm2k2mv gui
)
