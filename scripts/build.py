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
        "--name=Q-Launcher",
        "--onefile",
        "--windowed",
        "--icon=icon.ico",
        "--add-data=icon.ico;.",
        "--add-data=LICENSE;.",
        "--add-data=README.md;.",
        "--hidden-import=PySimpleGUI",
        "--hidden-import=cryptography",
        "--hidden-import=wizwalker",
        "--hidden-import=psutil",
        "--hidden-import=requests",
        "--hidden-import=win32gui",
        "--hidden-import=win32con",
        "--hidden-import=win32api",
        "main.py"
    ]
    
    print("Building Q-Launcher executable...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n✓ Build successful!")
        print(f"Executable location: {Path('dist/Q-Launcher.exe').absolute()}")
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
