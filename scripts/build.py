"""Build the full Windows application; dependencies must already be installed."""

import shutil
import subprocess
import sys
from pathlib import Path

from wizq import __version__


def build_exe():
    if sys.platform != "win32":
        raise RuntimeError("Build the release EXE on Windows.")

    root = Path(__file__).resolve().parent.parent
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name=WizQLauncher",
        "--icon=icon.ico",
        "--add-data=icon.ico;.",
        "--add-data=LICENSE;.",
        "--add-data=LICENSE-MIT;.",
        "--add-data=THIRD_PARTY.md;.",
        "--add-data=LICENSE-GPL-3.0;.",
        "--add-data=native/PROVENANCE.md;native",
        "--add-data=documentation;documentation",
        "--hidden-import=wizq_native",
        "--hidden-import=pypresence",
        "--exclude-module=PyQt6",
        "--exclude-module=PySimpleGUI",
        "--exclude-module=PySide6.QtWebEngineCore",
        "main.py",
    ]
    subprocess.run(command, cwd=root, check=True)
    release = root / "release"
    release.mkdir(exist_ok=True)
    target = release / f"WizQLauncher-v{__version__}.exe"
    shutil.copy2(root / "dist/WizQLauncher.exe", target)
    print(f"Windows build: {target}")


if __name__ == "__main__":
    build_exe()
