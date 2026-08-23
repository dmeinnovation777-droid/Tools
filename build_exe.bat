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
echo [1/3] Building the launcher...
pyinstaller --onefile --windowed --noconfirm --clean ^
    --name "DME Innovation Tools" --icon "assets\dme-icon.ico" dme_suite.py
if errorlevel 1 goto :failed

echo.
echo [2/3] Building AutoTuner Backup Tool...
pyinstaller --onefile --windowed --noconfirm --clean ^
    --name "AutoTuner Backup Tool" --icon "assets\dme-icon.ico" autotuner_tool.py
if errorlevel 1 goto :failed

echo.
echo [3/3] Building MHD Lock Tool...
pyinstaller --onefile --windowed --noconfirm --clean ^
    --name "MHD Lock Tool" --icon "assets\dme-icon.ico" mhd_lock_tool.py
if errorlevel 1 goto :failed

if not exist "dist\DME Innovation Tools.exe" goto :failed
if not exist "dist\AutoTuner Backup Tool.exe" goto :failed
if not exist "dist\MHD Lock Tool.exe" goto :failed

echo.
echo ==========================================================
echo   SUCCESS - executables are in the dist folder
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
