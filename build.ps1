$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .venv\Scripts\python.exe -m ensurepip --upgrade
& .venv\Scripts\python.exe -m pip install pyinstaller
if ($LASTEXITCODE) { throw 'Build dependencies failed' }
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --name TraceGarden --collect-all tracegarden --collect-all vtracer --collect-all svglib --collect-all reportlab --hidden-import _rl_renderPM --hidden-import svgpathtools --collect-submodules uvicorn launcher.py
if ($LASTEXITCODE) { throw 'Packaging failed' }
& .venv\Scripts\python.exe scripts\notices.py
Copy-Item README.md,FEATURES.md,LICENSE,THIRD_PARTY_NOTICES.md,dependency-licenses.json -Destination dist\TraceGarden
Copy-Item third-party-licenses -Destination dist\TraceGarden -Recurse -Force
& .venv\Scripts\python.exe -c "import sys, shutil; from pathlib import Path; p=Path(sys.base_prefix)/'LICENSE.txt'; shutil.copy(p,'dist/TraceGarden/PYTHON-LICENSE.txt')"
Compress-Archive -Path dist\TraceGarden -DestinationPath dist\TraceGarden-Windows-x64.zip -Force

