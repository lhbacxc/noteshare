@echo off
setlocal

cd /d "%~dp0"

set "PYTHONW_EXE="

if exist "D:\Software\Miniconda\envs\noteshare\pythonw.exe" set "PYTHONW_EXE=D:\Software\Miniconda\envs\noteshare\pythonw.exe"
if not defined PYTHONW_EXE if exist "%USERPROFILE%\miniconda3\envs\noteshare\pythonw.exe" set "PYTHONW_EXE=%USERPROFILE%\miniconda3\envs\noteshare\pythonw.exe"
if not defined PYTHONW_EXE if exist "%USERPROFILE%\anaconda3\envs\noteshare\pythonw.exe" set "PYTHONW_EXE=%USERPROFILE%\anaconda3\envs\noteshare\pythonw.exe"

if not defined PYTHONW_EXE (
  echo Could not find pythonw.exe for the conda environment "noteshare".
  echo Checked:
  echo   D:\Software\Miniconda\envs\noteshare\pythonw.exe
  echo   %%USERPROFILE%%\miniconda3\envs\noteshare\pythonw.exe
  echo   %%USERPROFILE%%\anaconda3\envs\noteshare\pythonw.exe
  echo.
  echo If needed, recreate the environment and install dependencies first.
  pause
  exit /b 1
)

if not exist "%~dp0app.py" (
  echo app.py was not found in the current folder.
  pause
  exit /b 1
)

start "" "%PYTHONW_EXE%" "%~dp0app.py"

endlocal
