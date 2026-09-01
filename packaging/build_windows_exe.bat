@echo off
setlocal

cd /d "%~dp0.."

echo ============================================================
echo  Lapus - Windows build
echo ============================================================
echo.
echo === Checking prerequisites ===

set "MISSING="

where git >nul 2>nul
if errorlevel 1 set "MISSING=%MISSING% Git"

rem npm ships with Node, so only look for it once Node itself is present -
rem otherwise a missing Node gets reported twice.
where node >nul 2>nul
if errorlevel 1 goto :no_node
where npm >nul 2>nul
if errorlevel 1 set "MISSING=%MISSING% npm"
goto :after_node
:no_node
set "MISSING=%MISSING% Node.js"
:after_node

rem Prefer the py launcher, fall back to python on PATH. Kept flat rather than
rem nested: setting a variable inside a parenthesised block needs delayed
rem expansion to read back correctly.
set "PYCMD="
where py >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto :have_python
where python >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
:have_python
if not defined PYCMD set "MISSING=%MISSING% Python"

if defined MISSING goto :missing

rem Python must be 3.11+; the backend uses syntax older versions reject, and
rem the failure otherwise surfaces much later as a confusing pip error.
%PYCMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :old_python

echo   Git      OK
echo   Versions found:
node --version
%PYCMD% --version
echo.

echo === Building the frontend - npm install + build ===
pushd frontend
call npm install
if errorlevel 1 goto :error_frontend
call npm run build
if errorlevel 1 goto :error_frontend
popd

echo.
echo === Setting up an isolated Python build environment ===

rem A virtualenv is not relocatable: the .exe shims in Scripts\ have the
rem absolute path of their own python.exe compiled into them. Move or rename
rem the repo folder and every shim still points at where the venv used to be,
rem failing with "Fatal error in launcher: Unable to create process". The path
rem the venv was built at is recorded so a moved folder is detected and the
rem venv rebuilt, rather than failing several minutes in.
set "VENV_STAMP=packaging\.build-venv\.built-at"
if not exist "packaging\.build-venv\Scripts\activate.bat" goto :make_venv
if not exist "%VENV_STAMP%" goto :stale_venv
set /p VENV_BUILT_AT=<"%VENV_STAMP%"
if /i "%VENV_BUILT_AT%"=="%CD%" goto :have_venv

:stale_venv
echo   The build environment was created at a different path.
echo   Rebuilding it - this is normal after renaming or moving the folder.
rmdir /s /q packaging\.build-venv

:make_venv
%PYCMD% -m venv packaging\.build-venv
if errorlevel 1 goto :error_venv
>"%VENV_STAMP%" echo %CD%

:have_venv

call packaging\.build-venv\Scripts\activate.bat
if errorlevel 1 goto :error_venv

python -m pip install --upgrade pip
python -m pip install -e "backend[build]"
if errorlevel 1 goto :error_deps

echo.
echo === Building Lapus.exe - this can take a few minutes ===
rem `python -m PyInstaller`, not the bare `pyinstaller` command: that resolves
rem to the Scripts\pyinstaller.exe shim, which carries a baked-in absolute path
rem to its python.exe and breaks if the folder ever moves. Going through the
rem interpreter sidesteps the shim entirely.
python -m PyInstaller --clean --noconfirm --distpath packaging\dist --workpath packaging\build packaging\lapus.spec
if errorlevel 1 goto :error_pyinstaller

echo.
echo ============================================================
echo  Done. The app is at: packaging\dist\Lapus\
echo.
echo  Double-click Lapus.exe inside that folder to run it.
echo  To share it, zip the whole Lapus folder - not just the exe -
echo  and have the recipient unzip it before running.
echo.
echo  Lapus looks for the parser's Spec_Stage.db in the folder you
echo  run it from, then in Desktop\Specs. To point it somewhere
echo  else, set LAPUS_DATABASE_URL before starting it.
echo ============================================================
goto :end

:missing
echo.
echo Missing prerequisite^(s^):%MISSING%
echo.
echo Install what's listed above, then open a NEW terminal and re-run this
echo script. A new terminal matters: an installer that adds itself to PATH
echo does not affect terminals that were already open.
echo.
echo   Git        https://git-scm.com/download/win
echo   Node.js    https://nodejs.org/           - LTS, includes npm
echo   Python     https://www.python.org/downloads/
echo              tick "Add python.exe to PATH" in the installer
echo.
exit /b 1

:old_python
echo.
%PYCMD% --version
echo ...but Python 3.11 or newer is required.
echo.
echo Install a newer Python from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during installation.
echo.
exit /b 1

:error_frontend
popd
echo.
echo Building the frontend failed.
echo.
echo Most common cause: no internet access, or a proxy blocking npm.
echo Check that "npm install" works on its own inside the frontend folder.
echo.
exit /b 1

:error_venv
echo.
echo Could not create the Python build environment at packaging\.build-venv
echo.
echo If that folder already exists from an earlier attempt, delete it and
echo re-run. Otherwise check that Python is installed correctly.
echo.
exit /b 1

:error_deps
echo.
echo Installing the Python dependencies failed.
echo Read the pip output above - the real cause is named in it.
echo Connection, SSL or timeout errors mean no internet access or a proxy
echo blocking pip.
echo.
exit /b 1

:error_pyinstaller
echo.
echo PyInstaller failed to build the app.
echo.
echo If this mentions a missing module, note the name and report it - it
echo likely needs adding to hiddenimports in packaging\lapus.spec.
echo.
exit /b 1

:end
endlocal
