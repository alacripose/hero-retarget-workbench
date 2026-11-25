@echo off
rem Start the Scout Port application and open its surface. The shell's Start row runs this file.
setlocal
set "APP=%~dp0"
start "" /min cmd /c "python "%APP%server.py""
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8795/"
endlocal
