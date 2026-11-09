@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py
) else (
    python app.py
)
if errorlevel 1 (
    echo.
    echo Die App konnte nicht gestartet werden. Bitte zuerst INSTALLIEREN.bat ausfuehren.
    pause
)
