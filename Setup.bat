@echo off
setlocal
cd /d "%~dp0"
echo ==============================================
echo   Firilla Voice Lock - setup
echo ==============================================

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required. Install it from https://www.python.org/downloads/
  echo ^(tick "Add python.exe to PATH"^), then run Setup.bat again.
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment...
  python -m venv .venv || goto :fail
) else (
  echo [1/4] Virtual environment already exists.
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
