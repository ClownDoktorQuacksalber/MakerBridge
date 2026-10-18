@echo off
rem ---------------------------------------------------------------------------
rem MakerBridge - RPG Maker 2000/2003 -> RPG Maker MZ converter
rem
rem   run.bat                 inspect the RM2k project (default command)
rem   run.bat inspect         structural report + validation
rem   run.bat dump            decode everything to intermediate JSON in dump\
rem   run.bat convert         write the MZ project
rem   run.bat convert "<src>" "<dst>"
rem
rem Every run writes a timestamped log to log\.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist "log" mkdir "log"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=inspect"

where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")

echo [MakerBridge] running: %CMD%
%PY% -X utf8 -m makerbridge %CMD% %2 %3 %4 %5 %6 %7 %8 %9
set "RC=%ERRORLEVEL%"

echo.
echo [MakerBridge] exit code %RC%
echo [MakerBridge] logs in "%~dp0log"
exit /b %RC%
