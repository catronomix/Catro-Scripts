@echo off
setlocal enabledelayedexpansion

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
        python "%SCRIPT_DIR%list.py"
    ) else (
        echo %C_CYAN%Available scripts in folder:%C_RESET%
        dir /b "%SCRIPT_DIR%*.py"
    )
    exit /b 0
)

set "SCRIPT_NAME=%~1"
set "FULL_PATH=%SCRIPT_DIR%%SCRIPT_NAME%.py"

:: Check if the .py file exists
if not exist "%FULL_PATH%" (
    echo %C_RED%Error: Script "%SCRIPT_NAME%.py" not found in %SCRIPT_DIR%%C_RESET%
    exit /b 1
)

:: Shift the arguments so %1 through %9 work with remaining params
shift

:: Run the python script with all remaining arguments
python "%FULL_PATH%" %1 %2 %3 %4 %5 %6 %7 %8 %9