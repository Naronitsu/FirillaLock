@echo off
cd /d "%~dp0"
set OUT=%USERPROFILE%\Desktop\Firilla-portable.zip
if exist "%OUT%" del "%OUT%"
echo Packing Firilla (app + speech model, no virtual environment, no voiceprint)...
if not exist "models\base.en\model.bin" echo NOTE: speech model not downloaded yet - the other PC will download it on first run.
powershell -NoProfile -Command "$f='app.py','firilla.py','icon.py','requirements.txt','Setup.bat','make_shortcut.ps1','README.md','.gitignore'; if (Test-Path models) { $f += 'models' }; Compress-Archive -Path $f -DestinationPath $env:OUT -Force"
echo.
echo Created: %OUT%
echo On the other PC: unzip anywhere, then double-click Setup.bat.
pause
