#!/usr/bin/env python3
"""
Build script for creating Q-Launcher executable
"""

import subprocess
import sys
import os
from pathlib import Path

def build_exe():
    """Build the executable using PyInstaller"""
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Build command
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name=WizQLauncher",
        "--onefile",
        "--windowed",
        "--icon=icon.ico",
        "--add-data=icon.ico;.",
        "--add-data=LICENSE;.",
        "--add-data=README.md;.",
        "--hidden-import=PySimpleGUI",
        "--hidden-import=cryptography",
        "--hidden-import=cryptography.hazmat.primitives.kdf.scrypt",
        "--hidden-import=psutil",
        "--hidden-import=requests",
        "--hidden-import=packaging",
        "--hidden-import=packaging.version",
        "--hidden-import=pypresence",
        "--hidden-import=pystray",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=win32gui",
        "--hidden-import=win32con",
        "--hidden-import=win32api",
        "--hidden-import=winreg",
        "--hidden-import=wizwalker",
        "main.py"
    ]
    
    print("Building WizQLauncher executable...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n✓ Build successful!")
        print(f"Executable location: {Path('dist/WizQLauncher.exe').absolute()}")
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
