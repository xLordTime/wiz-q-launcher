@echo off
:: start_launcher.bat  --  Wiz Q Launcher
:: Detects Python + Git, sets up venv, installs deps, then launches.
setlocal EnableExtensions

set "ROOT=%~dp0"
set "LOG_DIR=%ROOT%logs"
set "BATCH_LOG=%LOG_DIR%\start_launcher.bat.log"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "DEPS_STAMP=%ROOT%.venv\.deps_ok"
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
    echo [ERROR] No Python 3.11/3.12/3.13 found.
    echo         Install from https://www.python.org/ and retry.
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
call :ensure_deps
if errorlevel 1 (set "ERR=1" & goto :done)

:: -- 5. Launch
echo [INFO] Starting launcher...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Starting main.py
"%VENV_PY%" "%ROOT%main.py" %*
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
    echo [ERROR] Launcher exited with code %ERR%.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] Launcher exited with code %ERR%
) else (
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Launcher exited OK
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
:: 1 -- use existing venv python if compatible
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
    if not errorlevel 1 (set "BOOTSTRAP_EXE=%VENV_PY%"& goto :eof)
    echo [WARN] .venv Python is unsupported -- rebuilding venv...
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] Unsupported .venv Python, rebuilding
    rmdir /s /q "%ROOT%.venv" >nul 2>&1
)
:: 2 -- Windows py launcher
where py >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.12 3.11 3.13) do (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 (set "BOOTSTRAP_EXE=py"& set "BOOTSTRAP_ARGS=-%%V"& goto :eof)
    )
)
:: 3 -- known install paths
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
:: 4 -- PATH python
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
    if not errorlevel 1 (set "BOOTSTRAP_EXE=python"& goto :eof)
)
:: 5 -- auto-install via winget
echo [WARN] Python 3.11/3.12/3.13 not found. Trying winget...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] Python not found, trying winget
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERROR] winget not available. Install Python 3.12 from https://www.python.org/
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
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] Python still not found after winget install
goto :eof


:ensure_git
where git >nul 2>&1
if not errorlevel 1 goto :eof
echo [WARN] Git not found -- installing...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] Git not found, installing
:: try winget first
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
:: fallback: download from GitHub (architecture-aware)
call :detect_arch
echo [INFO] Downloading Git for Windows (%SYS_ARCH%) from GitHub...
>>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Downloading Git (%SYS_ARCH%) from GitHub
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a='%SYS_ARCH%'; $r=(Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest'); $v=$r.tag_name -replace '^v(\d+\.\d+\.\d+).*','$1'; if($a -eq 'arm64'){$f='Git-'+$v+'-arm64.exe'}else{$f='Git-'+$v+'-'+$a+'-bit.exe'}; $u='https://github.com/git-for-windows/git/releases/download/'+$r.tag_name+'/'+$f; $t=$env:TEMP+'\git-setup.exe'; Write-Host('[INFO] Downloading '+$f); Invoke-WebRequest $u -OutFile $t; Start-Process $t '/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS' -Wait; Remove-Item $t -Force"
where git >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Git installed successfully.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Git installed from GitHub
    goto :eof
)
echo [WARN] Git could not be installed. Some features may not work.
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


:ensure_deps
if not exist "%ROOT%requirements.txt" (
    echo [WARN] requirements.txt not found.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [WARN] requirements.txt missing
    exit /b 0
)
set "NEED_DEPS=1"
if exist "%DEPS_STAMP%" if not "%FORCE_REINSTALL_DEPS%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$r=(Get-Item '%ROOT%requirements.txt').LastWriteTimeUtc; $s=(Get-Item '%DEPS_STAMP%').LastWriteTimeUtc; exit [int]($s -lt $r)" >nul 2>&1
    if not errorlevel 1 set "NEED_DEPS=0"
)
if "%NEED_DEPS%"=="1" (
    echo [INFO] Installing dependencies...
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Installing deps
    "%VENV_PY%" -m pip --disable-pip-version-check install -r "%ROOT%requirements.txt"
    if errorlevel 1 (
        echo [ERROR] pip install failed.
        >>"%BATCH_LOG%" echo [%DATE% %TIME%] [ERROR] pip install failed
        exit /b 1
    )
    type nul > "%DEPS_STAMP%"
    echo [INFO] Dependencies installed.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Deps installed
) else (
    echo [INFO] Dependencies up to date.
    >>"%BATCH_LOG%" echo [%DATE% %TIME%] [INFO] Deps up to date
)
exit /b 0
