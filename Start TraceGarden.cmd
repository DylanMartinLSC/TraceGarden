@echo off
cd /d "%~dp0"
if exist "dist\TraceGarden\TraceGarden.exe" (
  "dist\TraceGarden\TraceGarden.exe"
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m tracegarden
) else (
  echo Please run Install TraceGarden.cmd first.
  pause
)
