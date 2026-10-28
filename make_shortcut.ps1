$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Firilla Voice Lock.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = Join-Path $here '.venv\Scripts\pythonw.exe'
$s.Arguments = '"' + (Join-Path $here 'app.py') + '"'
$s.WorkingDirectory = $here
$s.IconLocation = (Join-Path $here 'icon.ico')
$s.Description = 'Voice lock: say "Firilla lock"'
$s.Save()
Write-Host "Shortcut created: $lnk"
