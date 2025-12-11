@echo off
REM ================================================
REM 自動モニタリング実行スクリプト
REM Phase 2.5: タスクスケジューラから呼び出し用
REM ================================================

setlocal

set "PROJECT_ROOT=%~dp0.."
set "LOG_DIR=%PROJECT_ROOT%\logs\monitoring"
set "LOG_FILE=%LOG_DIR%\monitoring_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%.log"
set "LOG_FILE=%LOG_FILE: =0%"

cd /d "%PROJECT_ROOT%"

REM ログディレクトリ作成
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ================================================ >> "%LOG_FILE%"
echo 自動モニタリング実行 >> "%LOG_FILE%"
echo 実行日時: %date% %time% >> "%LOG_FILE%"
echo ================================================ >> "%LOG_FILE%"

REM モニタリング実行
python scripts\automated_monitoring.py --config config\monitoring_config.json >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo [ERROR] モニタリング実行に失敗しました >> "%LOG_FILE%"
    exit /b 1
) else (
    echo [OK] モニタリング完了 >> "%LOG_FILE%"
)

REM 古いログの削除（30日以上前）
forfiles /p "%LOG_DIR%" /s /m *.log /d -30 /c "cmd /c del @path" 2>nul

endlocal
