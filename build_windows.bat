@echo off
setlocal enabledelayedexpansion

REM Builds Hidden File Finder as a Windows EXE, creates a portable release ZIP,
REM and, when Inno Setup is installed, also creates a Windows installer.

cd /d "%~dp0"

echo [1/5] Checking Python...
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 launcher was not found. Install Python 3 from https://www.python.org/downloads/windows/
    exit /b 1
)

echo [2/5] Installing build dependency PyInstaller...
py -3 -m pip install --upgrade pip
if errorlevel 1 exit /b 1
py -3 -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [3/5] Building dist\HiddenFileFinder.exe...
py -3 -m PyInstaller --clean --noconfirm hidden_file_finder.spec
if errorlevel 1 exit /b 1

if not exist "dist\HiddenFileFinder.exe" (
    echo Build finished but dist\HiddenFileFinder.exe was not found.
    exit /b 1
)

echo EXE ready: dist\HiddenFileFinder.exe

echo [4/5] Creating portable release ZIP...
py -3 create_release_zip.py --platform Windows --exe dist\HiddenFileFinder.exe --output dist\release\HiddenFileFinder-1.0.0-Windows-Portable.zip
if errorlevel 1 exit /b 1
echo Release ZIP ready: dist\release\HiddenFileFinder-1.0.0-Windows-Portable.zip

echo [5/5] Looking for Inno Setup to build installer...
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
