@echo off
rem Double-click: run the local simulation console (installs on first run).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_simulation.ps1"
pause
