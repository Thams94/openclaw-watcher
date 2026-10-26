@echo off
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v OpenClawWatcher /f >nul 2>&1
taskkill /f /im OpenClawWatcher.exe >nul 2>&1
echo OpenClawWatcher autostart removed and process stopped.
pause
