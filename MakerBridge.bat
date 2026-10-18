@echo off
rem ---------------------------------------------------------------------------
rem MakerBridge - RPG Maker 2000/2003 -> RPG Maker MZ
rem
rem   double-click                   opens the window
rem   MakerBridge.bat setup          checks and installs what is needed
rem   MakerBridge.bat convert ...    command line (see MakerBridge.bat --help)
rem
rem On the first start MakerBridge sets itself up: it looks for Python (or
rem installs it through winget), creates its own Python environment .venv in
rem this folder and installs Pillow there - the system's Python is left alone.
rem ffmpeg for the music is installed on request.  Deleting the folder removes
rem everything again (except Python and ffmpeg themselves).
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
    echo  All set. Start MakerBridge by double-clicking MakerBridge.bat.
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
    echo  MakerBridge - setup
    echo  ===================
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
        echo  MakerBridge needs Python 3.10 or newer. It is not installed yet.
        if not defined WINGET goto :python_manual
        echo.
        choice /c YN /m " Install Python automatically now"
        if errorlevel 2 goto :python_manual
        winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
        call :find_python
        if not defined PY (
            echo.
            echo  Python has been installed. Please start MakerBridge once more
            echo  so that Windows finds it.
            pause
            exit /b 1
        )
    )
    echo.
    echo  Setting up MakerBridge ^(its own Python environment in .venv^) ...
    "!PY!" -m venv "%VENV%"
    if not exist "%VPY%" (
        echo  The Python environment could not be created.
        pause
        exit /b 1
    )
)
if defined VERBOSE echo  [ok] Python environment: %VENV%

rem -- Tkinter (the window) --------------------------------------------------
"%VPY%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Your Python lacks Tkinter, which the window needs.
    echo  Reinstall Python from https://www.python.org/downloads/ with
    echo  "tcl/tk and IDLE" ticked, then delete the .venv folder.
    pause
    exit /b 1
)

rem -- Pillow, inside .venv ---------------------------------------------------
"%VPY%" -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo  Installing Pillow ^(image processing^) into the MakerBridge environment ...
    "%VPY%" -m pip install --disable-pip-version-check --quiet -r requirements.txt
    "%VPY%" -c "import PIL" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  Pillow could not be installed. Check your internet connection
        echo  and start MakerBridge again.
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
echo  ffmpeg is missing. Without it the game's music is not converted
echo  ^(step "Convert audio"^) - everything else still works.
if not defined WINGET (
    echo  Download: https://www.gyan.dev/ffmpeg/builds/
    exit /b 0
)
echo.
choice /c YN /m " Install ffmpeg automatically now"
if errorlevel 2 (
    echo no> "log\no-ffmpeg"
    echo  Ok - you can catch up on it later with "MakerBridge.bat setup".
    exit /b 0
)
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
if exist "log\no-ffmpeg" del "log\no-ffmpeg"
exit /b 0

:python_manual
echo.
echo  Please install Python from https://www.python.org/downloads/
echo  ^(tick "Add python.exe to PATH" during the installation^) and then
echo  start MakerBridge again.
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
