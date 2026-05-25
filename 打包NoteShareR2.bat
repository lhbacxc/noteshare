@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE="

if exist "D:\Software\Miniconda\envs\noteshare\python.exe" set "PYTHON_EXE=D:\Software\Miniconda\envs\noteshare\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\noteshare\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\noteshare\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\noteshare\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\noteshare\python.exe"

if not defined PYTHON_EXE (
  echo Could not find python.exe for the conda environment "noteshare".
  echo Checked:
  echo   D:\Software\Miniconda\envs\noteshare\python.exe
  echo   %%USERPROFILE%%\miniconda3\envs\noteshare\python.exe
  echo   %%USERPROFILE%%\anaconda3\envs\noteshare\python.exe
  echo.
  echo Please create the environment first, then try again.
  pause
  exit /b 1
)

if not exist "%~dp0NoteShareR2.spec" (
  echo NoteShareR2.spec was not found in the current folder.
  pause
  exit /b 1
)

for %%I in ("%PYTHON_EXE%") do set "ENV_DIR=%%~dpI"
set "PATH=%ENV_DIR%;%ENV_DIR%Library\bin;%ENV_DIR%Scripts;%PATH%"

echo Using Python:
echo   %PYTHON_EXE%
echo.
echo Building NoteShareR2.exe...
echo.

"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo PyInstaller is not installed in the "noteshare" environment.
  echo Please run:
  echo   "%PYTHON_EXE%" -m pip install pyinstaller
  pause
  exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean "NoteShareR2.spec"
if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo Build succeeded.
echo Output:
echo   dist\NoteShareR2.exe
pause

endlocal
