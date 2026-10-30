@echo off
cd /d "%~dp0"
echo Installing TraceGarden. Internet is needed only for this setup.
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install .
if errorlevel 1 goto failed
echo Ready! Double-click Start TraceGarden.cmd.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11 or newer from python.org, then retry.
echo Keep this window open if you need to report the error above.
pause
exit /b 1
