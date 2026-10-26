@echo off
taskkill /f /im OpenClawWatcher.exe >nul 2>&1
echo OpenClawWatcher stopped. Autostart unchanged (use uninstall.cmd to remove it).
pause
