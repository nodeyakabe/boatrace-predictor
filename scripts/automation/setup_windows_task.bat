@echo off
REM Windowsタスクスケジューラーに自動収集タスクを登録するバッチファイル
REM
REM 使い方:
REM 1. このファイルを右クリック → 「管理者として実行」
REM 2. 登録が完了すると、毎日自動的に以下のタスクが実行されます:
REM    - 8:00 オリジナル展示データ収集
REM    - 8:15 本日のオッズ収集
REM    - 8:30 予想生成
REM    - 5分ごと レース監視（直前情報取得・通知）

echo ============================================================
echo ボートレース自動化システム - Windowsタスク登録
echo ============================================================
echo.

REM プロジェクトルートのパスを取得
set "PROJECT_ROOT=%~dp0..\..\"
pushd %PROJECT_ROOT%
set "PROJECT_ROOT=%CD%"
popd

REM Pythonのパスを取得
for /f "delims=" %%i in ('where python') do set PYTHON_PATH=%%i

if not defined PYTHON_PATH (
    echo [ERROR] Pythonが見つかりません
    echo Pythonをインストールしてください
    pause
    exit /b 1
)

echo [OK] Python: %PYTHON_PATH%
echo [OK] プロジェクトルート: %PROJECT_ROOT%
echo.

REM 既存のタスクを削除（エラーは無視）
echo 既存のタスクを削除中...
schtasks /Delete /TN "BoatRace_AutomationSystem" /F >nul 2>&1
echo.

REM タスクを登録
echo タスクを登録中...
schtasks /Create ^
    /TN "BoatRace_AutomationSystem" ^
    /TR "\"%PYTHON_PATH%\" \"%PROJECT_ROOT%\scripts\automation\daily_scheduler.py\"" ^
    /SC ONSTART ^
    /RU "%USERNAME%" ^
    /RL HIGHEST ^
    /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo [OK] タスク登録完了
    echo ============================================================
    echo.
    echo タスク名: BoatRace_AutomationSystem
    echo 実行タイミング: システム起動時
    echo.
    echo スケジュール:
    echo   - 毎朝 8:00 - オリジナル展示データ収集
    echo   - 毎朝 8:15 - 本日のオッズ収集
    echo   - 毎朝 8:30 - 予想生成
    echo   - 5分ごと - レース監視（直前情報取得・通知）
    echo.
    echo 確認方法:
    echo   1. タスクスケジューラーを開く
    echo   2. 「BoatRace_AutomationSystem」を検索
    echo.
    echo 手動実行方法:
    echo   schtasks /Run /TN "BoatRace_AutomationSystem"
    echo.
    echo 削除方法:
    echo   schtasks /Delete /TN "BoatRace_AutomationSystem" /F
    echo.
    echo ============================================================
) else (
    echo.
    echo [ERROR] タスク登録失敗
    echo 管理者権限で実行してください
    echo.
)

pause
