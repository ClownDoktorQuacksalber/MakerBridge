@echo off
rem ---------------------------------------------------------------------------
rem MakerBridge - RPG Maker 2000/2003 -> RPG Maker MZ
rem
rem   Doppelklick                    oeffnet das Fenster
rem   MakerBridge.bat setup          prueft und installiert, was gebraucht wird
rem   MakerBridge.bat convert ...    Kommandozeile (siehe MakerBridge.bat --help)
rem
rem Beim ersten Start richtet MakerBridge sich selbst ein: Es sucht Python
rem (oder installiert es ueber winget), legt im eigenen Ordner eine eigene
rem Python-Umgebung .venv an und installiert dort Pillow - am System-Python
rem wird nichts veraendert. ffmpeg fuer die Musik wird auf Wunsch installiert.
rem Den Ordner zu loeschen entfernt alles wieder (bis auf Python/ffmpeg selbst).
rem ---------------------------------------------------------------------------
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if not exist "log" mkdir "log"
set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "VPYW=%VENV%\Scripts\pythonw.exe"

set "VERBOSE="
if /i "%~1"=="setup" set "VERBOSE=1"
call :setup
if errorlevel 1 exit /b 1
if /i "%~1"=="setup" (
    echo.
    echo  Alles bereit. Starte MakerBridge mit einem Doppelklick auf MakerBridge.bat.
    echo.
    pause
    exit /b 0
)

if "%~1"=="" (
    rem pythonw opens the window without a console window.
    start "" "%VPYW%" -X utf8 -m makerbridge gui
    exit /b 0
)

echo [MakerBridge] %*
"%VPY%" -X utf8 -m makerbridge %*
set "RC=%ERRORLEVEL%"
echo.
echo [MakerBridge] exit code %RC%, logs in "%~dp0log"
exit /b %RC%


rem ===========================================================================
rem Setup: quiet when everything is in place, asks before installing.
rem ===========================================================================
:setup
set "WINGET="
where winget >nul 2>&1 && set "WINGET=1"
if defined VERBOSE (
    echo.
    echo  MakerBridge - Einrichtung
    echo  =========================
)

rem -- MakerBridge's own Python environment --------------------------------
if exist "%VPY%" (
    "%VPY%" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        rem Broken, e.g. the Python it was made from is gone: start over.
        rmdir /s /q "%VENV%"
    )
)
if not exist "%VPY%" (
    call :find_python
    if not defined PY (
        echo.
        echo  MakerBridge braucht Python 3.10 oder neuer. Es ist noch nicht installiert.
        if not defined WINGET goto :python_manual
        echo.
        choice /c JN /m " Python jetzt automatisch installieren"
        if errorlevel 2 goto :python_manual
        winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
        call :find_python
        if not defined PY (
            echo.
            echo  Python wurde installiert. Bitte MakerBridge noch einmal starten,
            echo  damit Windows es findet.
            pause
            exit /b 1
        )
    )
    echo.
    echo  Richte MakerBridge ein ^(eigene Python-Umgebung in .venv^) ...
    "!PY!" -m venv "%VENV%"
    if not exist "%VPY%" (
        echo  Die Python-Umgebung konnte nicht angelegt werden.
        pause
        exit /b 1
    )
)
if defined VERBOSE echo  [ok] Python-Umgebung: %VENV%

rem -- Tkinter (the window) --------------------------------------------------
"%VPY%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Deinem Python fehlt Tkinter, das fuer das Fenster gebraucht wird.
    echo  Installiere Python neu von https://www.python.org/downloads/ und lass
    echo  "tcl/tk and IDLE" angehakt. Danach den Ordner .venv loeschen.
    pause
    exit /b 1
)

rem -- Pillow, inside .venv ---------------------------------------------------
"%VPY%" -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo  Installiere Pillow ^(Bildbearbeitung^) in die MakerBridge-Umgebung ...
    "%VPY%" -m pip install --disable-pip-version-check --quiet -r requirements.txt
    "%VPY%" -c "import PIL" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  Pillow konnte nicht installiert werden. Pruefe die Internetverbindung
        echo  und starte MakerBridge noch einmal.
        pause
        exit /b 1
    )
)
if defined VERBOSE echo  [ok] Pillow

rem -- ffmpeg (optional) -------------------------------------------------------
"%VPY%" -X utf8 -c "import sys; from makerbridge.audio import find_ffmpeg; sys.exit(0 if find_ffmpeg() else 1)" >nul 2>&1
if not errorlevel 1 (
    if defined VERBOSE echo  [ok] ffmpeg
    exit /b 0
)
if exist "log\no-ffmpeg" if not defined VERBOSE exit /b 0
echo.
echo  ffmpeg fehlt. Ohne ffmpeg wird die Musik des Spiels nicht umgewandelt
echo  ^(Schritt "Audio umwandeln"^) - alles andere funktioniert trotzdem.
if not defined WINGET (
    echo  Download: https://www.gyan.dev/ffmpeg/builds/
    exit /b 0
)
echo.
choice /c JN /m " ffmpeg jetzt automatisch installieren"
if errorlevel 2 (
    echo nein> "log\no-ffmpeg"
    echo  Ok - mit "MakerBridge.bat setup" kannst du es spaeter nachholen.
    exit /b 0
)
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
if exist "log\no-ffmpeg" del "log\no-ffmpeg"
exit /b 0

:python_manual
echo.
echo  Bitte installiere Python von https://www.python.org/downloads/
echo  ^(bei der Installation "Add python.exe to PATH" anhaken^) und starte
echo  MakerBridge danach noch einmal.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

rem -- the first Python 3.10+ there is, as a full path -------------------------
:find_python
set "PY="
for %%C in ("py -3" "python" "python3") do (
    if not defined PY (
        for /f "delims=" %%I in ('%%~C -c "import sys; print(sys.executable) if sys.version_info >= (3, 10) else None" 2^>nul') do (
            if exist "%%I" set "PY=%%I"
        )
    )
)
rem Freshly installed by winget, before Windows knows the new PATH.
if not defined PY (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" (
            "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
            if not errorlevel 1 set "PY=%%D\python.exe"
        )
    )
)
exit /b 0
