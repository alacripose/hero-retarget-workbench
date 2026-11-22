@echo off
setlocal
title Deadlock VPK Tracker
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python was not found on PATH.
  echo Install Python 3, then run this launcher again.
  pause
  exit /b 1
)

%PY% tools\vpk_tracker.py serve --open --reuse
if errorlevel 1 (
  echo.
  echo The tracker did not start. The port may be held by another program.
  pause
)
endlocal
