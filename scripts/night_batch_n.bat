@echo off
setlocal
chcp 65001 >nul

REM ----------------------------
REM Night batch - ASCII safe version
REM ----------------------------

REM Base directory (folder of this bat)
set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

REM Directories relative to package root
set "LOG_DIR=%BASE_DIR%\..\logs\night_batch"
set "OUTPUT_DIR=%BASE_DIR%\..\output"
set "DATA_DB=%BASE_DIR%\..\data\boatrace.db"

mkdir "%LOG_DIR%" >nul 2>&1
mkdir "%OUTPUT_DIR%" >nul 2>&1

REM Timestamp (zero-pad hour)
set "DATESTR=%date:~0,4%%date:~5,2%%date:~8,2%"
set "TIMESTR=%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTR=%TIMESTR: =0%"
set "TIMESTAMP=%DATESTR%_%TIMESTR%"
set "LOG_FILE=%LOG_DIR%\batch_%TIMESTAMP%.log"

echo ======================================== >> "%LOG_FILE%"
echo Night batch start %date% %time% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

echo Starting night batch...
echo Log file: %LOG_FILE%
echo.

REM Use venv python if exists, else system python
set "VENV_PY=%BASE_DIR%\..\venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    set "PYTHON=%VENV_PY%"
) else (
    set "PYTHON=python"
)

REM ----------------------------
REM Task 1: wait for 365 distinct race_date entries
REM ----------------------------
echo [1/7] Waiting for prediction data (365 days) >> "%LOG_FILE%"

set WAIT_COUNT=0
set MAX_WAIT=240

:WAIT_LOOP
if %WAIT_COUNT% GEQ %MAX_WAIT% goto WAIT_TIMEOUT

"%PYTHON%" -c "import sqlite3,sys; conn=sqlite3.connect(r'%DATA_DB%'); c=conn.cursor(); c.execute(\"SELECT COUNT(DISTINCT race_date) FROM race_predictions WHERE generated_at >= '2025-12-10'\"); r=c.fetchone(); print(r[0] if r and r[0] is not None else 0); conn.close()" > temp_count.txt 2>&1

if exist temp_count.txt (
    set /p COMPLETED=<temp_count.txt
    del temp_count.txt
) else (
    set COMPLETED=0
)

if "%COMPLETED%"=="" set COMPLETED=0

REM Numeric compare
if %COMPLETED% GEQ 365 (
    echo 365 days of data present >> "%LOG_FILE%"
    goto DATA_READY
)

echo Current %COMPLETED%/365 completed >> "%LOG_FILE%"
timeout /t 60 /nobreak >nul
set /a WAIT_COUNT=%WAIT_COUNT%+1
goto WAIT_LOOP

:WAIT_TIMEOUT
echo [ERROR] Data did not reach 365 days within wait limit (%WAIT_COUNT%/%MAX_WAIT%) >> "%LOG_FILE%"
goto END

:DATA_READY
echo. >> "%LOG_FILE%"

REM ----------------------------
REM Task 2
REM ----------------------------
echo [2/7] validate_confidence_b_trifecta >> "%LOG_FILE%"
"%PYTHON%" "%BASE_DIR%\validate_confidence_b_trifecta.py" --start 2025-01-01 --end 2025-12-31 >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Task 2 failed >> "%LOG_FILE%"
) else (
    echo [OK] Task 2 done >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

REM ----------------------------
REM Task 3
REM ----------------------------
echo [3/7] analyze_seasonal_trends (B) >> "%LOG_FILE%"
"%PYTHON%" "%BASE_DIR%\analyze_seasonal_trends.py" --confidence B >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Task 3 failed >> "%LOG_FILE%"
) else (
    echo [OK] Task 3 done >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

REM ----------------------------
REM Task 4
REM ----------------------------
echo [4/7] analyze_conditions (B) >> "%LOG_FILE%"
"%PYTHON%" "%BASE_DIR%\analyze_conditions.py" --confidence B >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Task 4 failed >> "%LOG_FILE%"
) else (
    echo [OK] Task 4 done >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

REM ----------------------------
REM Task 5
REM ----------------------------
echo [5/7] validate_confidence_b_split >> "%LOG_FILE%"
"%PYTHON%" "%BASE_DIR%\validate_confidence_b_split.py" --threshold 70 >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Task 5 failed >> "%LOG_FILE%"
) else (
    echo [OK] Task 5 done >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

REM ----------------------------
REM Task 6
REM ----------------------------
echo [6/7] analyze_comprehensive_accuracy >> "%LOG_FILE%"
"%PYTHON%" "%BASE_DIR%\analyze_comprehensive_accuracy.py" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Task 6 failed >> "%LOG_FILE%"
) else (
    echo [OK] Task 6 done >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

REM ----------------------------
REM Task 7
REM ----------------------------
echo [7/7] analyze_seasonal_trends (C) >> "%LOG_FILE%"
"%PYTHON%" "%BASE_DIR%\analyze_seasonal_trends.py" --confidence C >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Task 7 failed >> "%LOG_FILE%"
) else (
    echo [OK] Task 7 done >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

REM ----------------------------
REM Finish
REM ----------------------------
echo ======================================== >> "%LOG_FILE%"
echo Night batch end %date% %time% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

echo Generated files: >> "%LOG_FILE%"
dir /b "%OUTPUT_DIR%\*.csv" >> "%LOG_FILE%" 2>&1
dir /b "%OUTPUT_DIR%\*.png" >> "%LOG_FILE%" 2>&1
dir /b "%OUTPUT_DIR%\*.md" >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%"

echo.
echo Night batch completed.
echo Log file: %LOG_FILE%
echo Output directory: %OUTPUT_DIR%
echo.
echo Files:
dir /b "%OUTPUT_DIR%\*.csv" 2>nul
dir /b "%OUTPUT_DIR%\*.png" 2>nul
dir /b "%OUTPUT_DIR%\*.md" 2>nul
echo.

:END
pause
