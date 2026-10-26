@echo off
setlocal
if exist "%~dp0OpenClawWatcher.exe" (
    "%~dp0OpenClawWatcher.exe" --setup
) else (
    python "%~dp0run.py" --setup
)
if errorlevel 1 pause
