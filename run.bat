@echo off
rem ---------------------------------------------------------------------------
rem rm2k2mv - RPG Maker 2000/2003 -> RPG Maker MV/MZ converter
rem
rem   run.bat                 inspect the RM2k project (default command)
rem   run.bat inspect         structural report + validation
rem   run.bat dump            decode everything to intermediate JSON in dump\
rem   run.bat convert         write the MV/MZ project
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

echo [rm2k2mv] running: %CMD%
%PY% -X utf8 -m rm2k2mv %CMD% %2 %3 %4 %5 %6 %7 %8 %9
set "RC=%ERRORLEVEL%"

echo.
echo [rm2k2mv] exit code %RC%
echo [rm2k2mv] logs in "%~dp0log"
exit /b %RC%
