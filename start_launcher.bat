@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "LOG_DIR=%ROOT%logs"
set "BATCH_LOG=%LOG_DIR%\start_launcher.bat.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

if /I not "%START_LAUNCHER_LOGGING%"=="1" (
	echo [INFO] Batch logging enabled: "%BATCH_LOG%"
	>> "%BATCH_LOG%" echo ============================================================
	>> "%BATCH_LOG%" echo [%DATE% %TIME%] Starting start_launcher.bat
	set "START_LAUNCHER_LOGGING=1"
	call "%~f0" %* >> "%BATCH_LOG%" 2>&1
	set "SCRIPT_EXIT=%ERRORLEVEL%"
	>> "%BATCH_LOG%" echo [%DATE% %TIME%] start_launcher.bat finished with exit code %SCRIPT_EXIT%
	exit /b %SCRIPT_EXIT%
)

set "PYTHON_VERSION=3.12"
set "PYTHON_FALLBACK_VERSION=3.11"
set "PYTHON_SECOND_FALLBACK_VERSION=3.13"
set "WINGET_PY_ID=Python.Python.3.12"
set "REQUIRED_PY_EXPR=sys.version_info[:2] in ((3,12),(3,11),(3,13))"
set "DEPS_STAMP=%ROOT%.venv\.deps_ok"
pushd "%ROOT%" >nul 2>&1
if errorlevel 1 (
	echo [ERROR] Could not switch to project directory: "%ROOT%"
	exit /b 1
)

set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "BOOTSTRAP_EXE="
set "BOOTSTRAP_ARGS="

if exist "%VENV_PY%" (
	"%VENV_PY%" -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
	if errorlevel 1 (
		echo [WARN] Existing .venv uses unsupported Python version. Recreating .venv...
		rmdir /s /q "%ROOT%.venv" >nul 2>&1
	)
)

call :detect_python

if not defined BOOTSTRAP_EXE (
	echo [WARN] Python not found. Trying automatic install via winget ^(Python %PYTHON_VERSION%^)...
	where winget >nul 2>&1
	if errorlevel 1 (
		echo [ERROR] winget not found. Install Python manually and rerun.
		popd
		exit /b 1
	)

	winget install -e --id "%WINGET_PY_ID%" --silent --accept-package-agreements --accept-source-agreements
	if errorlevel 1 (
		echo [ERROR] Automatic Python install failed.
		echo Try manual install from https://www.python.org/downloads/
		popd
		exit /b 1
	)

	call :detect_python
)

if not defined BOOTSTRAP_EXE (
	echo [ERROR] No Python interpreter found.
	echo Reopen terminal and run again, or install Python manually.
	popd
	exit /b 1
)

if not exist "%VENV_PY%" (
	echo [INFO] Creating virtual environment...
	"%BOOTSTRAP_EXE%" %BOOTSTRAP_ARGS% -m venv "%ROOT%.venv"
	if errorlevel 1 (
		echo [ERROR] Failed to create .venv
		popd
		exit /b 1
	)
)

if not exist "%VENV_PY%" (
	echo [ERROR] Python inside .venv not found: "%VENV_PY%"
	popd
	exit /b 1
)

if exist "%ROOT%requirements.txt" (
	set "NEED_DEPS=1"
	if /I "%FORCE_REINSTALL_DEPS%"=="1" set "NEED_DEPS=1"

	if exist "%DEPS_STAMP%" if /I not "%FORCE_REINSTALL_DEPS%"=="1" (
		powershell -NoProfile -ExecutionPolicy Bypass -Command "$req=Get-Item -LiteralPath '%ROOT%requirements.txt';$stamp=Get-Item -LiteralPath '%DEPS_STAMP%'; if($stamp.LastWriteTimeUtc -ge $req.LastWriteTimeUtc){exit 0}else{exit 1}" >nul 2>&1
		if not errorlevel 1 set "NEED_DEPS=0"
	)

	if "%NEED_DEPS%"=="1" (
		echo [INFO] Ensuring dependencies are installed...
		"%VENV_PY%" -m pip --disable-pip-version-check install -r "%ROOT%requirements.txt"
		if errorlevel 1 (
			echo [ERROR] Dependency installation failed.
			popd
			exit /b 1
		)
		type nul > "%DEPS_STAMP%"
	) else (
		echo [INFO] Dependencies already up to date. Skipping install.
	)
) else (
	echo [WARN] requirements.txt not found. Continuing without install.
)

"%VENV_PY%" "%ROOT%main.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
	echo [ERROR] Launcher exited with code %EXIT_CODE%.
	echo [ERROR] Check logs in "%ROOT%logs" for details.
)
popd
exit /b %EXIT_CODE%

:detect_python
set "BOOTSTRAP_EXE="
set "BOOTSTRAP_ARGS="

if defined WIZ_PYTHON_EXE (
	if exist "%WIZ_PYTHON_EXE%" (
		"%WIZ_PYTHON_EXE%" -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
		if not errorlevel 1 (
			set "BOOTSTRAP_EXE=%WIZ_PYTHON_EXE%"
			goto :eof
		)
	)
)

if exist "%VENV_PY%" (
	set "BOOTSTRAP_EXE=%VENV_PY%"
	goto :eof
)

where py >nul 2>&1
if not errorlevel 1 (
	py -%PYTHON_VERSION% -c "import sys" >nul 2>&1
	if not errorlevel 1 (
		set "BOOTSTRAP_EXE=py"
		set "BOOTSTRAP_ARGS=-%PYTHON_VERSION%"
		goto :eof
	)

	py -%PYTHON_FALLBACK_VERSION% -c "import sys" >nul 2>&1
	if not errorlevel 1 (
		set "BOOTSTRAP_EXE=py"
		set "BOOTSTRAP_ARGS=-%PYTHON_FALLBACK_VERSION%"
		goto :eof
	)

	py -%PYTHON_SECOND_FALLBACK_VERSION% -c "import sys" >nul 2>&1
	if not errorlevel 1 (
		set "BOOTSTRAP_EXE=py"
		set "BOOTSTRAP_ARGS=-%PYTHON_SECOND_FALLBACK_VERSION%"
		goto :eof
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
		if not errorlevel 1 (
			set "BOOTSTRAP_EXE=%%~P"
			goto :eof
		)
	)
)

where python >nul 2>&1
if not errorlevel 1 (
	python -c "import sys; raise SystemExit(0 if %REQUIRED_PY_EXPR% else 1)" >nul 2>&1
	if not errorlevel 1 (
		set "BOOTSTRAP_EXE=python"
		goto :eof
	)
)

goto :eof



