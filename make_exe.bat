@echo off
:: make_exe.bat  --  Wiz Q Launcher build script
:: Detects Python + Git, sets up venv, installs deps, then builds the exe.
setlocal EnableExtensions

set "ROOT=%~dp0"
set "LOG_DIR=%ROOT%logs"
set "BATCH_LOG=%LOG_DIR%\make_exe.bat.log"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "REQUIRED_PY_EXPR=sys.version_info[:2] in ((3,12),(3,11),(3,13))"
set "WINGET_PY_ID=Python.Python.3.12"
set "ERR=0"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
>>"%BATCH_LOG%" echo ============================================================
>>"%BATCH_LOG%" echo [%DATE% %TIME%] === START ===

pushd "%ROOT%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot cd to "%ROOT%"
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] Cannot cd to ROOT
    set "ERR=1" & goto :done
)

:: -- 1. Python
set "BOOTSTRAP_EXE="
set "BOOTSTRAP_ARGS="
call :ensure_python
if not defined BOOTSTRAP_EXE (
    echo [ERROR] No Python 3.11/3.12/3.13 found. Install from https://www.python.org/
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] Python not found
    set "ERR=1" & goto :done
)
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Python: %BOOTSTRAP_EXE% %BOOTSTRAP_ARGS%

:: -- 2. Git
call :ensure_git

:: -- 3. Virtual environment
if not exist "%VENV_PY%" (
    echo [INFO] Creating virtual environment...
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Creating venv
    "%BOOTSTRAP_EXE%" %BOOTSTRAP_ARGS% -m venv "%ROOT%.venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv
        >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] venv creation failed
        set "ERR=1" & goto :done
    )
)

:: -- 4. Dependencies
if exist "%ROOT%requirements.txt" (
    echo [INFO] Installing dependencies...
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Installing deps
    "%VENV_PY%" -m pip --disable-pip-version-check install -r "%ROOT%requirements.txt"
    if errorlevel 1 (
        echo [ERROR] pip install failed.
        >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] pip install failed
        set "ERR=1" & goto :done
    )
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Deps installed
) else (
    echo [WARN] requirements.txt not found.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] requirements.txt missing
)

:: -- 5. Build
echo [INFO] Building executable...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Starting build.py
"%VENV_PY%" "%ROOT%build.py" %*
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
    echo [ERROR] Build failed with code %ERR%.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] Build failed with code %ERR%
) else (
    echo [INFO] Build finished successfully.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Build finished OK
)

:done
>>"%BATCH_LOG%" echo [%DATE% %TIME%] === EXIT %ERR% ===
popd >nul 2>&1
echo.
if not "%ERR%"=="0" echo [ERROR] Finished with errors.  Log: %BATCH_LOG%
echo.
pause
exit /b %ERR%


:: ======================================================================
::  Subroutines
:: ======================================================================

:ensure_python
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
    if not errorlevel 1 (set "BOOTSTRAP_EXE=%VENV_PY%"& goto :eof)
    echo [WARN] .venv Python is unsupported -- rebuilding venv...
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] Unsupported .venv Python, rebuilding
    rmdir /s /q "%ROOT%.venv" >nul 2>&1
)
where py >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.12 3.11 3.13) do (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 (set "BOOTSTRAP_EXE=py"& set "BOOTSTRAP_ARGS=-%%V"& goto :eof)
    )
)
for %%P in (
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%ProgramFiles%\Python313\python.exe"
) do (
    if exist "%%~P" (
        "%%~P" -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
        if not errorlevel 1 (set "BOOTSTRAP_EXE=%%~P"& goto :eof)
    )
)
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
    if not errorlevel 1 (set "BOOTSTRAP_EXE=python"& goto :eof)
)
echo [WARN] Python not found. Trying winget...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] Python not found, trying winget
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERROR] winget not available. Install Python 3.12 manually.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] winget not found
    goto :eof
)
winget install -e --id "%WINGET_PY_ID%" --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [ERROR] Python auto-install failed.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] winget Python install failed
    goto :eof
)
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Python installed via winget
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 (set "BOOTSTRAP_EXE=py"& set "BOOTSTRAP_ARGS=-3.12"& goto :eof)
)
echo [ERROR] Python not found after install. Reopen terminal and retry.
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] Python still not found after winget
goto :eof


:ensure_git
where git >nul 2>&1
if not errorlevel 1 goto :eof
echo [WARN] Git not found -- installing...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] Git not found, installing
where winget >nul 2>&1
if not errorlevel 1 (
    winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
    where git >nul 2>&1
    if not errorlevel 1 (
        echo [INFO] Git installed via winget.
        >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Git installed via winget
        goto :eof
    )
)
call :detect_arch
echo [INFO] Downloading Git for Windows (%SYS_ARCH%) from GitHub...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Downloading Git (%SYS_ARCH%) from GitHub
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a='%SYS_ARCH%'; $r=(Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest'); $v=$r.tag_name -replace '^v(\d+\.\d+\.\d+).*','$1'; if($a -eq 'arm64'){$f='Git-'+$v+'-arm64.exe'}else{$f='Git-'+$v+'-'+$a+'-bit.exe'}; $u='https://github.com/git-for-windows/git/releases/download/'+$r.tag_name+'/'+$f; $t=$env:TEMP+'\git-setup.exe'; Write-Host('[INFO] Downloading '+$f); Invoke-WebRequest $u -OutFile $t; Start-Process $t '/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS' -Wait; Remove-Item $t -Force"
where git >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Git installed.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Git installed from GitHub
    goto :eof
)
echo [WARN] Git installation failed.
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] Git installation failed
goto :eof


:detect_arch
set "SYS_ARCH=64"
if "%PROCESSOR_ARCHITECTURE%"=="ARM64" (set "SYS_ARCH=arm64"& goto :eof)
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" goto :eof
if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    if defined PROCESSOR_ARCHITEW6432 (
        if "%PROCESSOR_ARCHITEW6432%"=="AMD64" (set "SYS_ARCH=64"& goto :eof)
        if "%PROCESSOR_ARCHITEW6432%"=="ARM64" (set "SYS_ARCH=arm64"& goto :eof)
    )
    set "SYS_ARCH=32"
)
goto :eof
