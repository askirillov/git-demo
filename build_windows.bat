@echo off
setlocal enabledelayedexpansion

REM Builds Hidden File Finder as a Windows EXE and, when Inno Setup is installed,
REM also creates a Windows installer in dist\installer\HiddenFileFinderSetup.exe.

cd /d "%~dp0"

echo [1/4] Checking Python...
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 launcher was not found. Install Python 3 from https://www.python.org/downloads/windows/
    exit /b 1
)

echo [2/4] Installing build dependency PyInstaller...
py -3 -m pip install --upgrade pip
if errorlevel 1 exit /b 1
py -3 -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [3/4] Building dist\HiddenFileFinder.exe...
py -3 -m PyInstaller --clean --noconfirm hidden_file_finder.spec
if errorlevel 1 exit /b 1

if not exist "dist\HiddenFileFinder.exe" (
    echo Build finished but dist\HiddenFileFinder.exe was not found.
    exit /b 1
)

echo EXE ready: dist\HiddenFileFinder.exe

echo [4/4] Looking for Inno Setup to build installer...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php to build installer.
    echo Skipping installer. You can still distribute dist\HiddenFileFinder.exe.
    exit /b 0
)

"%ISCC%" installer\hidden_file_finder.iss
if errorlevel 1 exit /b 1

echo Installer ready: dist\installer\HiddenFileFinderSetup.exe
endlocal
