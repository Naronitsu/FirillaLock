@echo off
setlocal
cd /d "%~dp0"
echo ==============================================
echo   Firilla Voice Lock - setup
echo ==============================================

if exist ".venv\Scripts\python.exe" goto :have_venv

call :find_python
if defined PY goto :make_venv

echo Python 3.10 or newer is needed and wasn't found on this PC.
echo I can install Python 3.11 for you (just for your user account, no admin needed).
choice /c YN /m "Install Python now"
if errorlevel 2 goto :no_python
call :install_python
call :find_python
if defined PY goto :make_venv
echo.
echo Python was installed but I can't find it yet. Close this window and run Setup.bat again.
pause
exit /b 1

:no_python
echo.
echo OK. Install Python 3.10+ from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
echo and run Setup.bat again.
pause
exit /b 1

:make_venv
echo [1/4] Creating virtual environment using %PY% ...
"%PY%" -m venv .venv || goto :fail
goto :after_venv

:have_venv
echo [1/4] Virtual environment already exists.

:after_venv
if /i "%~1"=="--check-python" (
  echo PY=%PY%
  exit /b 0
)

echo [2/4] Installing packages ^(first time takes a few minutes^)...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip || goto :fail
".venv\Scripts\pip.exe" install -q torch --index-url https://download.pytorch.org/whl/cpu || goto :fail
".venv\Scripts\pip.exe" install -q -r requirements.txt || goto :fail
rem resemblyzer pins a package that needs a C++ compiler; webrtcvad-wheels replaces it
".venv\Scripts\pip.exe" install -q --no-deps resemblyzer || goto :fail

if exist "models\base.en\model.bin" (
  echo       Speech model already present in the models folder - no download needed.
) else (
  echo       Downloading the speech model ^(~140 MB, one time only^). Needs internet...
  ".venv\Scripts\python.exe" -c "import firilla; firilla.download_whisper()" || goto :fail
)

echo [3/4] Creating icon and desktop shortcut...
".venv\Scripts\python.exe" icon.py || goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -File make_shortcut.ps1 || goto :fail

echo [4/4] Done! Launching Firilla...
start "" ".venv\Scripts\pythonw.exe" app.py
echo.
echo Use the "Firilla Voice Lock" shortcut on your desktop from now on.
timeout /t 5 >nul
exit /b 0

:fail
echo.
echo Setup failed - see the message above.
pause
exit /b 1

rem ---- sets PY to the full path of a Python 3.10+ interpreter, or leaves it empty ----
:find_python
set "PY="
set "CHECK=import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)"
set "PRINT=import sys; print(sys.executable)"
rem the Python launcher and PATH first (the Microsoft Store stub fails the version check, so it's skipped)
for %%C in ("py -3" "python") do (
  if not defined PY (
    %%~C -c "%CHECK%" >nul 2>nul && for /f "delims=" %%P in ('%%~C -c "%PRINT%"') do set "PY=%%P"
  )
)
if defined PY exit /b 0
rem just-installed Pythons that this window's PATH doesn't know about yet
for %%V in (313 312 311 310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)
exit /b 0

rem ---- installs Python 3.11 for the current user: winget if present, else python.org ----
:install_python
where winget >nul 2>nul
if errorlevel 1 goto :install_python_direct
echo Installing Python with winget...
winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
exit /b 0

:install_python_direct
set "PYURL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PYEXE=%TEMP%\python-3.11.9-amd64.exe"
echo Downloading Python 3.11.9 from python.org ^(about 25 MB^)...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest '%PYURL%' -OutFile '%PYEXE%'" || exit /b 1
echo Installing Python ^(this takes a minute^)...
"%PYEXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0
del "%PYEXE%" >nul 2>nul
exit /b 0
