@echo off
REM Build a Windows .exe distribution of the Audi EDC17 map editor.
REM Requires Python 3.10+ on PATH. Run from this folder:
REM     build_exe.bat
REM Output will be in:
REM     dist\audi-map-editor\audi-map-editor.exe

setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not on PATH. Install Python 3.10+ from https://www.python.org/downloads/
    exit /b 1
)

if not exist .venv (
    echo [1/3] Creating virtual environment...
    python -m venv .venv || exit /b 1
)

call .venv\Scripts\activate.bat

echo [2/3] Installing dependencies...
python -m pip install --upgrade pip wheel || exit /b 1
python -m pip install -r requirements.txt pyinstaller || exit /b 1

echo [3/3] Building executable (this takes a few minutes)...
rmdir /s /q build dist 2>nul
pyinstaller --noconfirm audi-map-editor.spec || exit /b 1

echo.
echo === Done ===
echo Run: dist\audi-map-editor\audi-map-editor.exe
endlocal
