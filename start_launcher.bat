@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "PYTHON_VERSION=3.12"
set "PYTHON_FALLBACK_VERSION=3.11"
set "WINGET_PY_ID=Python.Python.3.12"
pushd "%ROOT%" >nul 2>&1
if errorlevel 1 (
	echo [ERROR] Could not switch to project directory: "%ROOT%"
	exit /b 1
)

set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "BOOTSTRAP_EXE="
set "BOOTSTRAP_ARGS="

if exist "%VENV_PY%" (
	"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,11)) else 1)" >nul 2>&1
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
	echo [INFO] Ensuring dependencies are installed...
	"%VENV_PY%" -m pip --disable-pip-version-check install -r "%ROOT%requirements.txt"
	if errorlevel 1 (
		echo [ERROR] Dependency installation failed.
		popd
		exit /b 1
	)
) else (
	echo [WARN] requirements.txt not found. Continuing without install.
)

"%VENV_PY%" "%ROOT%main.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:detect_python
set "BOOTSTRAP_EXE="
set "BOOTSTRAP_ARGS="

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
)

for %%P in (
	"%LocalAppData%\Programs\Python\Python312\python.exe"
	"%LocalAppData%\Programs\Python\Python311\python.exe"
	"%ProgramFiles%\Python312\python.exe"
	"%ProgramFiles%\Python311\python.exe"
) do (
	if exist "%%~P" (
		set "BOOTSTRAP_EXE=%%~P"
		goto :eof
	)
)

where python >nul 2>&1
if not errorlevel 1 (
	python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,11)) else 1)" >nul 2>&1
	if not errorlevel 1 (
		set "BOOTSTRAP_EXE=python"
		goto :eof
	)
)

goto :eof
