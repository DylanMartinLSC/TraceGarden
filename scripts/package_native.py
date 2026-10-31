"""Build a self-contained desktop bundle on the current OS."""

import platform
import argparse
import subprocess
import sys
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=root / "dist")
    args = parser.parse_args()
    output = args.output.resolve()
    system = platform.system()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "TraceGarden",
        "--distpath",
        str(output),
        "--collect-all",
        "tracegarden",
        "--collect-all",
        "vtracer",
        "--collect-all",
        "resvg_py",
        "--collect-all",
        "reportlab",
        "--collect-all",
        "shapely",
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "skimage.morphology",
        "--collect-data",
        "skimage",
    ]
    if system in {"Windows", "Darwin"}:
        command.append("--windowed")
    command.append("launcher.py")
    subprocess.run(command, cwd=root, check=True)
    subprocess.run([sys.executable, "scripts/notices.py"], cwd=root, check=True)
    folder = output / "TraceGarden"
    if system == "Darwin":
        folder = output / "TraceGarden.app" / "Contents" / "Resources"
    for name in [
        "README.md",
        "FEATURES.md",
        "PARITY.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "dependency-licenses.json",
    ]:
        shutil.copy(root / name, folder / name)
    shutil.copytree(
        root / "third-party-licenses",
        folder / "third-party-licenses",
        dirs_exist_ok=True,
    )
    license_file = Path(sys.base_prefix) / "LICENSE.txt"
    if license_file.exists():
        shutil.copy(license_file, folder / "PYTHON-LICENSE.txt")
