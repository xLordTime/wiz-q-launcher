@echo off
setlocal
set "ROOT=%~dp0"

if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo .venv not found. Create it and install requirements first.
    exit /b 1
)

"%ROOT%.venv\Scripts\python.exe" "%ROOT%build.py"
