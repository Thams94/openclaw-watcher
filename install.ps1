param(
    [switch]$Uninstall,
    [switch]$NoStart
)
$ErrorActionPreference = "Stop"

$AppDir = $PSScriptRoot
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$Name = "OpenClawWatcher"

if ($Uninstall) {
    if (Get-ItemProperty -Path $RunKey -Name $Name -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $RunKey -Name $Name -Force
    }
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*openclaw-watcher*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Autostart removed; watcher stopped."
    return
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "python not found in PATH" }
$pythonw = Join-Path (Split-Path $py.Source -Parent) "pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found: $pythonw" }

$configPath = Join-Path $AppDir "config.json"
if (-not (Test-Path $configPath)) {
    Copy-Item (Join-Path $AppDir "config.example.json") $configPath
    Write-Host "Created config.json from config.example.json"
}

$main = Join-Path $AppDir "run.py"
$value = "`"$pythonw`" `"$main`""
Set-ItemProperty -Path $RunKey -Name $Name -Value $value
Write-Host "Autostart registered: $value"

if (-not $NoStart) {
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*openclaw-watcher*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Process -FilePath $pythonw -ArgumentList "`"$main`"" -WorkingDirectory $AppDir -WindowStyle Hidden
    Write-Host "Watcher started. Log: %APPDATA%\OpenClawWatcher\watcher.log"
}
