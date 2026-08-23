@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================================
echo   DME Innovation - Tools .exe Builder
echo ==========================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install it from https://python.org
    echo        Make sure "tcl/tk and IDLE" is ticked during setup.
    pause
    exit /b 1
)

echo Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: PyInstaller could not be installed.
    pause
    exit /b 1
)

if not exist "assets\dme-icon.ico" (
    echo Icon missing - extracting it from dme_brand.py...
    python -c "import dme_brand; dme_brand.write_ico(r'assets\dme-icon.ico')"
)

echo.
echo [1/2] Building AutoTuner Backup Tool...
pyinstaller --onefile --windowed --noconfirm --clean ^
    --name "AutoTuner Backup Tool" ^
    --icon "assets\dme-icon.ico" ^
    autotuner_tool.py
if errorlevel 1 goto :failed

echo.
echo [2/2] Building MHD Lock Tool...
pyinstaller --onefile --windowed --noconfirm --clean ^
    --name "MHD Lock Tool" ^
    --icon "assets\dme-icon.ico" ^
    mhd_lock_tool.py
if errorlevel 1 goto :failed

echo.
if exist "dist\AutoTuner Backup Tool.exe" if exist "dist\MHD Lock Tool.exe" (
    echo ==========================================================
    echo   SUCCESS - both executables are in the dist folder:
    echo     dist\AutoTuner Backup Tool.exe
    echo     dist\MHD Lock Tool.exe
    echo ==========================================================
    explorer dist
    pause
    exit /b 0
)

:failed
echo.
echo BUILD FAILED - see the output above.
pause
exit /b 1
