@echo off
REM 自動モニタリングのWindowsタスクスケジューラ設定スクリプト

setlocal enabledelayedexpansion

echo =========================================
echo 自動モニタリング タスクスケジューラ設定
echo =========================================
echo.

REM プロジェクトルート取得
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
cd /d "%PROJECT_ROOT%"

REM Pythonパス検出
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    where python3 >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python3
    ) else (
        echo ❌ Pythonが見つかりません
        pause
        exit /b 1
    )
)

echo Python: %PYTHON_CMD%
echo プロジェクトルート: %PROJECT_ROOT%
echo.

REM ログディレクトリ作成
if not exist "logs" mkdir logs

echo 以下のタスクを設定します:
echo.
echo 【週次モニタリング】毎週月曜日 9:00
echo   monitor_pattern_performance.py --days 7
echo.
echo 【月次パターン更新】毎月1日 1:00
echo   auto_pattern_update.py --days 30
echo.
echo 【自動監視】毎日 8:00
echo   automated_monitoring.py
echo.

set /p CONFIRM="タスクを追加しますか？ (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo キャンセルしました
    pause
    exit /b 1
)

REM タスク1: 週次モニタリング
echo.
echo タスク追加中: 週次モニタリング...
schtasks /Create /TN "BoatRace_WeeklyMonitoring" /TR "%PYTHON_CMD% %PROJECT_ROOT%\scripts\monitor_pattern_performance.py --days 7 >> %PROJECT_ROOT%\logs\monitoring_weekly.log 2>&1" /SC WEEKLY /D MON /ST 09:00 /F
if %errorlevel% equ 0 (
    echo ✓ 週次モニタリングタスク追加完了
) else (
    echo ⚠️ 週次モニタリングタスク追加失敗（管理者権限が必要な場合があります）
)

REM タスク2: 月次パターン更新
echo.
echo タスク追加中: 月次パターン更新...
schtasks /Create /TN "BoatRace_MonthlyPatternUpdate" /TR "%PYTHON_CMD% %PROJECT_ROOT%\scripts\auto_pattern_update.py --days 30 >> %PROJECT_ROOT%\logs\monitoring_monthly.log 2>&1" /SC MONTHLY /D 1 /ST 01:00 /F
if %errorlevel% equ 0 (
    echo ✓ 月次パターン更新タスク追加完了
) else (
    echo ⚠️ 月次パターン更新タスク追加失敗
)

REM タスク3: 自動監視
echo.
echo タスク追加中: 自動監視...
schtasks /Create /TN "BoatRace_AutomatedMonitoring" /TR "%PYTHON_CMD% %PROJECT_ROOT%\scripts\automated_monitoring.py >> %PROJECT_ROOT%\logs\monitoring_automated.log 2>&1" /SC DAILY /ST 08:00 /F
if %errorlevel% equ 0 (
    echo ✓ 自動監視タスク追加完了
) else (
    echo ⚠️ 自動監視タスク追加失敗
)

echo.
echo =========================================
echo ✅ タスクスケジューラ設定完了
echo =========================================
echo.
echo 設定されたタスクを確認:
echo   タスクスケジューラを開く: taskschd.msc
echo   または: schtasks /Query /TN "BoatRace_*"
echo.
echo ログ確認:
echo   type logs\monitoring_weekly.log
echo   type logs\monitoring_monthly.log
echo   type logs\monitoring_automated.log
echo =========================================

pause
