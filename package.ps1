param(
    [string]$Python = "python",
    [string]$Version = "0.1.0",
    [switch]$NoZip
)
$ErrorActionPreference = "Stop"
$AppDir = $PSScriptRoot
Push-Location $AppDir
try {
    Write-Host "== Building exe (PyInstaller) with $Python =="
    Remove-Item build, dist -Recurse -Force -ErrorAction SilentlyContinue
    & $Python -m PyInstaller --noconfirm --clean --windowed --name OpenClawWatcher `
        --add-data "watcher/remote_query.py;watcher" `
        --hidden-import pystray._win32 `
        --collect-submodules pystray `
        --distpath dist --workpath build run.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    Copy-Item config.example.json "dist\OpenClawWatcher\"
    Copy-Item README.md "dist\OpenClawWatcher\"
    Copy-Item setup.cmd "dist\OpenClawWatcher\"
    Copy-Item uninstall.cmd "dist\OpenClawWatcher\"
    Copy-Item stop.cmd "dist\OpenClawWatcher\"

    if (-not $NoZip) {
        $zip = "dist\OpenClawWatcher-$Version-win64.zip"
        Compress-Archive -Path "dist\OpenClawWatcher\*" -DestinationPath $zip -Force
        Write-Host "Package: $zip"
    }
    Write-Host "Output: $AppDir\dist\OpenClawWatcher"
} finally { Pop-Location }
