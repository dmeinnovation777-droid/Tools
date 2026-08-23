@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================================
echo   DME Innovation Tools - Installer Builder
echo ==========================================================
echo.

call build_exe.bat --no-pause
if errorlevel 1 (
    echo ERROR: the executables could not be built.
    pause
    exit /b 1
)

for /f "usebackq tokens=*" %%v in (`python -c "import dme_brand; print(dme_brand.VERSION)"`) do set APPVERSION=%%v
if "%APPVERSION%"=="" set APPVERSION=1.0.0
echo.
echo Version: %APPVERSION%

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC where ISCC.exe >nul 2>&1 && set "ISCC=ISCC.exe"

if not defined ISCC (
    echo.
    echo ERROR: Inno Setup 6 was not found.
    echo        Install it from https://jrsoftware.org/isdl.php
    echo        or run:  winget install JRSoftware.InnoSetup
    pause
    exit /b 1
)

echo Using: %ISCC%
echo.
echo Building the installer...
"%ISCC%" /DAppVersion=%APPVERSION% "installer\dme-innovation-tools.iss"
if errorlevel 1 (
    echo.
    echo INSTALLER BUILD FAILED - see the output above.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   SUCCESS
echo     dist\DME-Innovation-Tools-Setup-%APPVERSION%.exe
echo ==========================================================
explorer dist
pause
exit /b 0
