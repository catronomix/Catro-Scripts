@echo off
setlocal disabledelayedexpansion

:: Force UTF-8 for the child Python process. Without this, piped or redirected
:: output falls back to the console code page (cp1252) and the table comes out
:: as mojibake or a UnicodeEncodeError.
set "PYTHONUTF8=1"

:: Define ANSI escape code for colors
for /F "tokens=1,2 delims=#" %%a in ('"prompt #$H#$E# & echo on & for %%b in (1) do rem"') do set "ESC=%%b"

set "C_RESET=%ESC%[0m"
set "C_HEADER=%ESC%[95m"
set "C_CYAN=%ESC%[96m"
set "C_YELLOW=%ESC%[93m"
set "C_GREEN=%ESC%[92m"
set "C_RED=%ESC%[91m"
set "C_BOLD=%ESC%[1m"

:: Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

:: Resolve the Python interpreter once instead of assuming "python" exists.
:: Prefer "python", then fall back to the "py" launcher. PY_CMD is reused for
:: every Python call below so both call sites stay in sync.
set "PY_CMD="
where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    echo %C_RED%Error: no Python interpreter found. Install Python 3.11+ and make sure either "python" or "py" is on your PATH.%C_RESET%
    exit /b 9009
)

:: Check if an argument was provided
if "%~1"=="" (
    echo %C_BOLD%%C_HEADER%============================================================%C_RESET%
    echo                %C_BOLD%CATRO SCRIPTS SETUP ^& USAGE%C_RESET%
    echo %C_BOLD%%C_HEADER%============================================================%C_RESET%
    echo %C_YELLOW%SETUP:%C_RESET%
    echo 1. Ensure this folder is in your Windows PATH variable.
    echo    %C_CYAN%Current Folder:%C_RESET% %SCRIPT_DIR%
    echo.
    echo %C_YELLOW%USAGE:%C_RESET%
    echo %C_BOLD%catro-scripts%C_RESET% [script_name] [arguments]
    echo.
    echo %C_YELLOW%EXAMPLES:%C_RESET%
    echo %C_GREEN%catro-scripts randomsorter 10 5 --ext .png%C_RESET%
    echo %C_GREEN%catro-scripts list%C_RESET%
    echo %C_BOLD%%C_HEADER%============================================================%C_RESET%
    
    :: Use the list utility if it exists to show available scripts
    if exist "%SCRIPT_DIR%list.py" (
        %PY_CMD% "%SCRIPT_DIR%list.py"
    ) else (
        echo %C_CYAN%Available scripts in folder:%C_RESET%
        dir /b "%SCRIPT_DIR%*.py"
    )
    exit /b 0
)

:: Check for action shorthand '.' to invoke the action script with a 'run' command.
if not "%~1"=="." goto :not_dot
set "MODE=action"
shift
goto :collect

:not_dot
set "MODE=script"
set "SCRIPT_NAME=%~1"
set "FULL_PATH=%SCRIPT_DIR%%SCRIPT_NAME%.py"

:: Check if the .py file exists
if not exist "%FULL_PATH%" (
    echo %C_RED%Error: Script "%SCRIPT_NAME%.py" not found in %SCRIPT_DIR%%C_RESET%
    exit /b 1
)

:: Shift off the script name so only the script's own arguments remain
shift


:: ---------------------------------------------------------------------------
:: Collect every remaining argument, re-quoting each token exactly once.
:: This survives more than 9 arguments and stops cmd metacharacters
:: (& | ( ) ) inside an argument from splitting the command.
::
:: Delayed expansion is deliberately left off, so the unquoted `set` form is
:: required here: wrapping the whole value in quotes (set "ARGS=%ARGS% "%~1"")
:: would close the quoting early once ARGS already holds a quoted metachar
:: argument, and the next token's & would split the line.
::
:: `if "%~1"==""` terminates the loop. An argument that is itself empty is
:: therefore not passed through; that is an accepted limitation.
:: ---------------------------------------------------------------------------
:collect
set ARGS=
:collect_loop
if "%~1"=="" goto :collected
set ARGS=%ARGS% "%~1"
shift
goto :collect_loop

:collected
if "%MODE%"=="action" goto :run_action

:: Run the python script with all remaining arguments
%PY_CMD% "%FULL_PATH%" %ARGS%
exit /b %errorlevel%

:run_action
%PY_CMD% "%SCRIPT_DIR%action.py" run %ARGS%
exit /b %errorlevel%