@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "NOPAUSE="
if /i "%~1"=="--no-pause" set "NOPAUSE=1"

echo ==========================================================
echo   DME Innovation Tools - .exe Builder
echo ==========================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install it from https://python.org
    echo        Make sure "tcl/tk and IDLE" is ticked during setup.
    if not defined NOPAUSE pause
    exit /b 1
)

echo Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: PyInstaller could not be installed.
    if not defined NOPAUSE pause
    exit /b 1
)

if not exist "assets\dme-icon.ico" (
    echo Icon missing - extracting it from dme_brand.py...
    python -c "import dme_brand; dme_brand.write_ico(r'assets\dme-icon.ico')"
)

echo.
echo Building one executable that carries all three programs...
echo   (Python and tkinter go in once, not three times - the launcher starts
echo    itself again with --tool ^<key^> to open a tool.)
pyinstaller --onefile --windowed --noconfirm --clean ^
    --name "DME Innovation Tools" --icon "assets\dme-icon.ico" ^
    --hidden-import autotuner_tool --hidden-import mhd_lock_tool ^
    dme_suite.py
if errorlevel 1 goto :failed

if not exist "dist\DME Innovation Tools.exe" goto :failed

echo.
echo ==========================================================
echo   SUCCESS - the executable is in the dist folder
echo ==========================================================
if not defined NOPAUSE (
    explorer dist
    pause
)
exit /b 0

:failed
echo.
echo BUILD FAILED - see the output above.
if not defined NOPAUSE pause
exit /b 1
