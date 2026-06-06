@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "APP_NAME=NoteShareR2"
set "EXE_PATH=%~dp0dist\%APP_NAME%.exe"
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

for %%I in ("%PYTHON_EXE%") do set "ENV_DIR=%%~dpI"
if "%ENV_DIR:~-1%"=="\" set "ENV_DIR=%ENV_DIR:~0,-1%"

set "CONDA_PREFIX=%ENV_DIR%"
set "NOTESHARE_CONDA_ENV=%ENV_DIR%"
set "PATH=%ENV_DIR%;%ENV_DIR%\Library\bin;%ENV_DIR%\Scripts;%PATH%"

echo Using Python:
echo   %PYTHON_EXE%
echo.

for %%F in ("app.py" "NoteShareR2.spec" "cf_cloud.ico" "requirements.txt") do (
  if not exist "%~dp0%%~F" (
    echo Missing required file:
    echo   %%~F
    pause
    exit /b 1
  )
)

for %%D in ("libssl-3-x64.dll" "libcrypto-3-x64.dll" "libexpat.dll") do (
  if not exist "%ENV_DIR%\Library\bin\%%~D" (
    echo Missing required runtime DLL:
    echo   %ENV_DIR%\Library\bin\%%~D
    echo.
    echo Please check whether the conda environment is complete.
    pause
    exit /b 1
  )
)

echo Checking Python dependencies...
"%PYTHON_EXE%" -c "import PySide6, boto3, botocore, PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo Some dependencies are missing. Installing from requirements.txt...
  "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo.
    echo Dependency installation failed.
    echo Please run manually:
    echo   "%PYTHON_EXE%" -m pip install -r requirements.txt
    pause
    exit /b 1
  )

  "%PYTHON_EXE%" -c "import PySide6, boto3, botocore, PyInstaller" >nul 2>&1
  if errorlevel 1 (
    echo.
    echo Dependencies are still incomplete after installation.
    pause
    exit /b 1
  )
)

echo Cleaning old build outputs...
if exist "%~dp0build" rmdir /s /q "%~dp0build"
if not exist "%~dp0dist" mkdir "%~dp0dist"
if exist "%EXE_PATH%" (
  echo Checking whether old %APP_NAME%.exe is still running...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $target = (Resolve-Path -LiteralPath '%EXE_PATH%' -ErrorAction SilentlyContinue); if ($target) { $matches = @(Get-Process -Name '%APP_NAME%' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $target.Path }); foreach ($process in $matches) { Stop-Process -Id $process.Id -Force -ErrorAction Stop } }; exit 0"
  if errorlevel 1 (
    echo.
    echo Could not stop the running %APP_NAME%.exe process.
    echo Please close it manually, then run this script again.
    pause
    exit /b 1
  )

  powershell -NoProfile -ExecutionPolicy Bypass -Command "$path = '%EXE_PATH%'; for ($i = 0; $i -lt 5; $i++) { try { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction Stop }; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; Write-Error 'Could not remove old exe.'; exit 1"
  if errorlevel 1 (
    echo.
    echo Could not remove old exe:
    echo   %EXE_PATH%
    echo Please close %APP_NAME%.exe or any security software scan that is holding it, then try again.
    pause
    exit /b 1
  )
)
if exist "%~dp0__pycache__" rmdir /s /q "%~dp0__pycache__"
if exist "%~dp0%APP_NAME%.log" del /f /q "%~dp0%APP_NAME%.log"

echo.
echo Building %APP_NAME%.exe...
echo.

"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean "%~dp0NoteShareR2.spec"
if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)

if not exist "%EXE_PATH%" (
  echo.
  echo Build finished, but the exe was not found:
  echo   %EXE_PATH%
  pause
  exit /b 1
)

for %%I in ("%EXE_PATH%") do (
  set "EXE_SIZE=%%~zI"
  set "EXE_FULL_PATH=%%~fI"
)

echo.
echo Build succeeded.
echo Output:
echo   %EXE_FULL_PATH%
echo Size:
echo   %EXE_SIZE% bytes
echo.
pause

endlocal
